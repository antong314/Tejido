"""Telegram-only entrypoint.

The bot binds to a single session at startup, selected by id with
--telegram-session. Web sessions are served by `circle.web` or
`circle.run`; this entrypoint is the simplest option when you only
care about Telegram for one session.

Usage:
    python -m circle.bot --telegram-session bylaws_v2
"""

from __future__ import annotations

import argparse
import logging
import sys

from telegram.ext import Application, ApplicationBuilder

from .anthropic_client import AnthropicClient
from .config import ConfigError, load_app_config
from .handlers import commands, consent, conversation, permissions
from .runtime import BotContext
from .session import load_session
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


def build_application(session_id: str) -> Application:
    app_config = load_app_config()
    session = load_session(session_id, app_config.sessions_dir)

    anthropic = AnthropicClient(
        api_key=app_config.secrets.anthropic_api_key,
        default_model=session.common.facilitator_model,
    )
    whisper = WhisperTranscriber(
        model_name=session.whisper.model,
        models_dir=session.whisper.models_dir,
    )
    context = BotContext(
        session=session,
        app_config=app_config,
        anthropic=anthropic,
        whisper=whisper,
    )
    context.data_dir.mkdir(parents=True, exist_ok=True)

    application = (
        ApplicationBuilder()
        .token(app_config.secrets.telegram_bot_token)
        .build()
    )
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
    parser = argparse.ArgumentParser(
        description="Run the Tejido Telegram bot for a single session."
    )
    parser.add_argument(
        "--telegram-session",
        required=True,
        help="Session id the bot should bind to (looked up in config/sessions/).",
    )
    args = parser.parse_args()

    _configure_logging()

    try:
        application = build_application(args.telegram_session)
    except (ConfigError, Exception) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    logger.info(
        "circle bot starting; session=%s; polling for updates",
        args.telegram_session,
    )
    application.run_polling(allowed_updates=None)


if __name__ == "__main__":
    main()
