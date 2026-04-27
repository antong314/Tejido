"""Telegram bot entrypoint.

Usage:
    python -m circle.bot --config config/session_config.yaml

Wires the BotContext (config + Anthropic client + local Whisper transcriber)
into all handlers. Handler order matters: command handlers and callback
query handlers are registered before the catch-all text/voice handlers, and
they're grouped logically by component.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from telegram.ext import Application, ApplicationBuilder

from .anthropic_client import AnthropicClient
from .config import ConfigError, load_app_config
from .handlers import commands, consent, conversation, permissions
from .runtime import BotContext
from .whisper_client import WhisperTranscriber

logger = logging.getLogger("circle")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # httpx (used by python-telegram-bot under the hood) is very chatty.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def build_application(config_path: str | Path) -> Application:
    app_config = load_app_config(config_path)
    anthropic = AnthropicClient(
        api_key=app_config.secrets.anthropic_api_key,
        default_model=app_config.session.facilitator_model,
    )
    whisper = WhisperTranscriber(
        model_name=app_config.session.whisper.model,
        models_dir=app_config.session.whisper.models_dir,
    )
    context = BotContext(config=app_config, anthropic=anthropic, whisper=whisper)

    application = (
        ApplicationBuilder()
        .token(app_config.secrets.telegram_bot_token)
        .build()
    )

    # Command + callback handlers from each component, registered before the
    # catch-all message handlers so commands like /done and the inline-button
    # callbacks always win.
    for handler in commands.build_handlers(context):
        application.add_handler(handler)
    for handler in consent.build_handlers(context):
        application.add_handler(handler)
    for handler in permissions.build_handlers(context):
        application.add_handler(handler)
    for handler in conversation.build_handlers(context):
        application.add_handler(handler)

    return application


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Circle Telegram bot.")
    parser.add_argument(
        "--config",
        default="config/session_config.yaml",
        help="Path to the session config YAML.",
    )
    args = parser.parse_args()

    _configure_logging()

    try:
        application = build_application(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    logger.info("circle bot starting; polling for updates")
    application.run_polling(allowed_updates=None)


if __name__ == "__main__":
    main()
