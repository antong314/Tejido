"""Combined Telegram + Web entrypoint.

Runs the FastAPI web server (multi-session) and optionally the Telegram
poller (single-session, bound to whichever session you pass via
--telegram-session) in a single asyncio event loop. Both share one
SessionRegistry — same BotContexts, same per-session locks, same data
files. A participant could in principle have one tab open via web and
another via Telegram talking to the same session — they'd just be
treated as two different participants (different identity resolution).

Usage:
    python -m circle.run                                   # web only
    python -m circle.run --telegram-session bylaws_v2     # web + Telegram on bylaws_v2
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import uvicorn
from telegram.ext import ApplicationBuilder

from .config import ConfigError, load_app_config
from .handlers import commands, consent, conversation, permissions
from .registry import SessionRegistry
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

    fastapi_app = create_app(registry=registry)
    uv_config = uvicorn.Config(
        fastapi_app, host=args.host, port=args.port, log_level="info"
    )
    uv_server = uvicorn.Server(uv_config)

    tg_app = None
    if args.telegram_session:
        tg_context = await registry.get(args.telegram_session)
        if tg_context is None:
            print(
                f"--telegram-session {args.telegram_session!r} not found in "
                f"{app_config.sessions_dir}",
                file=sys.stderr,
            )
            sys.exit(2)
        tg_app = (
            ApplicationBuilder()
            .token(app_config.secrets.telegram_bot_token)
            .build()
        )
        for handler in commands.build_handlers(tg_context):
            tg_app.add_handler(handler)
        for handler in consent.build_handlers(tg_context):
            tg_app.add_handler(handler)
        for handler in permissions.build_handlers(tg_context):
            tg_app.add_handler(handler)
        for handler in conversation.build_handlers(tg_context):
            tg_app.add_handler(handler)
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling()

    logger.info(
        "tejido starting | sessions=%s | telegram=%s | web=http://%s:%s/",
        registry.list_session_ids(),
        args.telegram_session or "off",
        args.host,
        args.port,
    )

    try:
        await uv_server.serve()
    finally:
        logger.info("shutting down...")
        if tg_app is not None:
            try:
                await tg_app.updater.stop()
                await tg_app.stop()
                await tg_app.shutdown()
            except Exception:
                logger.exception("error shutting down telegram client")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run Tejido — multi-session web UI plus, optionally, the "
            "Telegram bot bound to a single session."
        )
    )
    parser.add_argument(
        "--telegram-session",
        default=None,
        help=(
            "Session id to bind the Telegram bot to. Omit to run web-only."
        ),
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
