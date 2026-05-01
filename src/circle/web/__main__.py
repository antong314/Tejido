"""Standalone web entry point — runs FastAPI alone for development.

The combined Telegram + web entry point lands in a later commit. For now,
this lets us smoke-test the join / state endpoints in isolation:

    python -m circle.web --config config/session_smoke.yaml --port 8000
"""

from __future__ import annotations

import argparse
import logging
import sys

import uvicorn

from ..anthropic_client import AnthropicClient
from ..config import ConfigError, load_app_config
from ..runtime import BotContext
from ..whisper_client import WhisperTranscriber
from .app import create_app

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Tejido web adapter (FastAPI) standalone."
    )
    parser.add_argument(
        "--config",
        default="config/session_config.yaml",
        help="Path to the session config YAML.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind (default loopback only).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="TCP port to listen on.",
    )
    parser.add_argument(
        "--no-ffmpeg-check",
        action="store_true",
        help="Skip the ffmpeg-on-PATH validation (web-only sessions don't need it).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        app_config = load_app_config(args.config, require_ffmpeg=not args.no_ffmpeg_check)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    anthropic = AnthropicClient(
        api_key=app_config.secrets.anthropic_api_key,
        default_model=app_config.session.facilitator_model,
    )
    whisper = WhisperTranscriber(
        model_name=app_config.session.whisper.model,
        models_dir=app_config.session.whisper.models_dir,
    )
    context = BotContext(config=app_config, anthropic=anthropic, whisper=whisper)
    app = create_app(context)

    logger.info(
        "tejido web starting host=%s port=%s session=%s",
        args.host,
        args.port,
        app_config.session.session_id,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
