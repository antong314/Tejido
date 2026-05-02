"""Combined Telegram + Web entrypoint.

Runs the FastAPI web server (multi-session) and a TelegramManager that
optionally binds the Telegram bot to one of those sessions. The binding
is admin-controlled at runtime via /api/admin/telegram and persisted to
`config/telegram.json` so it survives restarts.

There used to be a `--telegram-session <id>` CLI flag that locked the
binding for the lifetime of the process. It's gone — the admin UI is
now the source of truth. To start the server with no Telegram, just
make sure no binding is persisted (or unbind via the admin UI once and
it stays unbound).

Usage:
    python -m circle.run                  # web + admin-controlled telegram
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import uvicorn

from .config import ConfigError, load_app_config
from .registry import SessionRegistry
from .telegram_manager import TelegramManager
from .web.app import create_app
from .whisper_client import WhisperTranscriber

logger = logging.getLogger("circle")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def _run_combined(args: argparse.Namespace) -> None:
    app_config = load_app_config()
    whisper = WhisperTranscriber(
        model_name="medium",
        models_dir="models/",
    )
    registry = SessionRegistry(app_config=app_config, whisper=whisper)

    # The TelegramManager owns the python-telegram-bot Application
    # lifecycle. We hand it to create_app so the admin REST endpoints
    # can bind/unbind through it. Auto-resume reads the persisted
    # binding (config/telegram.json) and starts polling if one exists.
    telegram = TelegramManager(
        registry=registry,
        bot_token=app_config.secrets.telegram_bot_token,
        state_path=app_config.sessions_dir.parent / "telegram.json",
    )
    await telegram.resume_persisted()

    fastapi_app = create_app(registry=registry, telegram=telegram)
    uv_config = uvicorn.Config(
        fastapi_app, host=args.host, port=args.port, log_level="info"
    )
    uv_server = uvicorn.Server(uv_config)

    logger.info(
        "tejido starting | sessions=%s | telegram=%s | web=http://%s:%s/",
        registry.list_session_ids(),
        telegram.bound_session_id or "off",
        args.host,
        args.port,
    )

    try:
        await uv_server.serve()
    finally:
        logger.info("shutting down...")
        await telegram.stop()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run Tejido — multi-session web UI plus an admin-controlled "
            "Telegram binding."
        )
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    _configure_logging()

    try:
        # Validate config + ffmpeg early before booting asyncio.
        load_app_config()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        asyncio.run(_run_combined(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
