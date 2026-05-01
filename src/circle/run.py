"""Combined Telegram + Web entrypoint.

Runs the Telegram bot poller and the FastAPI web app in a single asyncio
event loop, sharing one BotContext. Both surfaces see the same state
files, the same per-participant locks, the same Anthropic client, the
same Whisper model.

    python -m circle.run --config config/session_config.yaml

Use `python -m circle.bot --config ...` if you want Telegram only;
`python -m circle.web --config ...` if you want web only. This module
is for the both-at-once case.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import uvicorn
from telegram.ext import ApplicationBuilder

from .anthropic_client import AnthropicClient
from .config import ConfigError, load_app_config
from .handlers import commands, consent, conversation, permissions
from .runtime import BotContext
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


async def _run_combined(args: argparse.Namespace, app_config) -> None:
    anthropic = AnthropicClient(
        api_key=app_config.secrets.anthropic_api_key,
        default_model=app_config.session.facilitator_model,
    )
    whisper = WhisperTranscriber(
        model_name=app_config.session.whisper.model,
        models_dir=app_config.session.whisper.models_dir,
    )
    context = BotContext(config=app_config, anthropic=anthropic, whisper=whisper)

    # Telegram polling client
    tg_app = (
        ApplicationBuilder()
        .token(app_config.secrets.telegram_bot_token)
        .build()
    )
    for handler in commands.build_handlers(context):
        tg_app.add_handler(handler)
    for handler in consent.build_handlers(context):
        tg_app.add_handler(handler)
    for handler in permissions.build_handlers(context):
        tg_app.add_handler(handler)
    for handler in conversation.build_handlers(context):
        tg_app.add_handler(handler)

    # FastAPI server
    fastapi_app = create_app(context)
    uv_config = uvicorn.Config(
        fastapi_app,
        host=args.host,
        port=args.port,
        log_level="info",
    )
    uv_server = uvicorn.Server(uv_config)

    # Boot Telegram polling in the background, run uvicorn in the foreground.
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling()

    logger.info(
        "tejido starting | session=%s | telegram=on | web=http://%s:%s/",
        app_config.session.session_id,
        args.host,
        args.port,
    )

    try:
        await uv_server.serve()
    finally:
        logger.info("shutting down...")
        try:
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()
        except Exception:
            logger.exception("error shutting down telegram client")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Tejido — Telegram bot and web UI in one process."
    )
    parser.add_argument(
        "--config",
        default="config/session_config.yaml",
        help="Path to the session config YAML.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface for the web server (default loopback only).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="TCP port for the web server.",
    )
    args = parser.parse_args()

    _configure_logging()

    try:
        app_config = load_app_config(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        asyncio.run(_run_combined(args, app_config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
