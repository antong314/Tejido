"""Standalone web entrypoint — multi-session FastAPI, no Telegram.

Loads the SessionRegistry over `config/sessions/` so all sessions are
available immediately. Use `circle.run` if you want Telegram alongside.

Usage:
    python -m circle.web --port 8000
    python -m circle.web --no-ffmpeg-check --port 8000
"""

from __future__ import annotations

import argparse
import logging
import sys

import uvicorn

from ..config import ConfigError, load_app_config
from ..registry import SessionRegistry
from ..whisper_client import WhisperTranscriber
from .app import create_app

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Tejido web adapter (multi-session, no Telegram)."
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host interface to bind."
    )
    parser.add_argument("--port", type=int, default=8000, help="TCP port.")
    parser.add_argument(
        "--no-ffmpeg-check",
        action="store_true",
        help="Skip the ffmpeg check (web-only sessions don't need it).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        app_config = load_app_config(require_ffmpeg=not args.no_ffmpeg_check)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    # Whisper is shared across every session in this process. It's loaded
    # eagerly so first-audio-request latency is just the transcription
    # itself, not the model load. Reasonable for the prototype; could
    # become lazy if startup time matters more than first-call latency.
    whisper = WhisperTranscriber(
        model_name="medium",
        models_dir=app_config.models_dir,
    )
    registry = SessionRegistry(app_config=app_config, whisper=whisper)
    app = create_app(registry=registry)

    logger.info(
        "tejido web starting host=%s port=%s sessions=%s",
        args.host,
        args.port,
        registry.list_session_ids(),
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
