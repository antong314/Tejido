"""App-level configuration — shared resources, secrets, on-disk locations.

Independent of any specific session. Per-session configuration lives in
`circle.session.Session` (loaded from `config/sessions/<id>.json`).

`AppConfig` is constructed once at startup; the SessionRegistry then uses
its paths and secrets to materialize session-specific BotContexts on
demand.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Secrets:
    anthropic_api_key: str
    telegram_bot_token: str


@dataclass(frozen=True)
class AppConfig:
    """Process-level configuration shared across all sessions."""

    secrets: Secrets
    sessions_dir: Path = field(default_factory=lambda: Path("config/sessions"))
    # Per-workflow-type admin overrides for task_framing, output_template,
    # and mechanics live as JSON files here. See circle.workflow_overrides.
    workflows_dir: Path = field(default_factory=lambda: Path("config/workflows"))
    # Reusable community-context blobs, referenced by sessions via
    # common.community_context_id. See circle.contexts.
    contexts_dir: Path = field(default_factory=lambda: Path("config/contexts"))
    data_dir_base: Path = field(default_factory=lambda: Path("data"))
    syntheses_dir: Path = field(default_factory=lambda: Path("syntheses"))
    proposals_dir: Path = field(default_factory=lambda: Path("proposals"))
    revisions_dir: Path = field(default_factory=lambda: Path("revisions"))

    def data_dir_for(self, session_id: str) -> Path:
        return self.data_dir_base / session_id


class ConfigError(Exception):
    pass


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def load_secrets() -> Secrets:
    # override=True so a real .env value beats an empty/stale shell var.
    load_dotenv(override=True)
    return Secrets(
        anthropic_api_key=_require_env("ANTHROPIC_API_KEY"),
        telegram_bot_token=_require_env("TELEGRAM_BOT_TOKEN"),
    )


def check_ffmpeg_available() -> None:
    """Voice transcription requires ffmpeg to convert audio to 16 kHz WAV."""
    if shutil.which("ffmpeg") is None:
        raise ConfigError(
            "ffmpeg is not on PATH. Install it (e.g. `brew install ffmpeg` on macOS, "
            "`apt install ffmpeg` on Debian/Ubuntu). Voice messages cannot be "
            "transcribed without it."
        )


def load_app_config(*, require_ffmpeg: bool = True) -> AppConfig:
    """Construct the AppConfig + ensure all on-disk dirs exist.

    Does NOT load any session — that's the SessionRegistry's job, on
    demand.
    """
    secrets = load_secrets()
    if require_ffmpeg:
        check_ffmpeg_available()

    config = AppConfig(secrets=secrets)
    config.sessions_dir.mkdir(parents=True, exist_ok=True)
    config.workflows_dir.mkdir(parents=True, exist_ok=True)
    config.contexts_dir.mkdir(parents=True, exist_ok=True)
    config.data_dir_base.mkdir(parents=True, exist_ok=True)
    config.syntheses_dir.mkdir(parents=True, exist_ok=True)
    config.proposals_dir.mkdir(parents=True, exist_ok=True)
    config.revisions_dir.mkdir(parents=True, exist_ok=True)

    return config
