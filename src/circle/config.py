"""Session and environment configuration loading.

Implements PRD section 7 (per-session config) and validates the environment
the bot needs to run. The session config matches the example in PRD section 10
plus a `whisper` block for the local pywhispercpp model selection.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class Participant:
    handle: str
    display_name: str


@dataclass(frozen=True)
class WhisperConfig:
    model: str = "medium"
    models_dir: str = "models/"


@dataclass(frozen=True)
class SessionConfig:
    session_id: str
    question: str
    context: str
    community_context: str
    participants: list[Participant]
    language: str
    facilitator_model: str
    synthesis_model: str
    whisper: WhisperConfig
    config_path: Path


@dataclass(frozen=True)
class Secrets:
    anthropic_api_key: str
    telegram_bot_token: str


@dataclass(frozen=True)
class AppConfig:
    session: SessionConfig
    secrets: Secrets
    data_dir: Path = field(default_factory=lambda: Path("data"))
    syntheses_dir: Path = field(default_factory=lambda: Path("syntheses"))
    proposals_dir: Path = field(default_factory=lambda: Path("proposals"))


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


def load_session_config(path: str | Path) -> SessionConfig:
    config_path = Path(path).resolve()
    if not config_path.exists():
        raise ConfigError(f"Session config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ConfigError(f"Session config must be a YAML mapping: {config_path}")

    required_keys = ("session_id", "question", "participants")
    missing = [key for key in required_keys if key not in raw]
    if missing:
        raise ConfigError(f"Session config missing required keys: {missing}")

    raw_participants = raw.get("participants") or []
    if not isinstance(raw_participants, list):
        raise ConfigError("`participants` must be a list")

    participants: list[Participant] = []
    for index, entry in enumerate(raw_participants):
        if not isinstance(entry, dict):
            raise ConfigError(f"participants[{index}] must be a mapping")
        handle = (entry.get("handle") or "").strip()
        display_name = (entry.get("display_name") or "").strip()
        if not handle or not display_name:
            raise ConfigError(
                f"participants[{index}] must have non-empty `handle` and `display_name`"
            )
        participants.append(Participant(handle=handle, display_name=display_name))

    # PRD section 1.3: prototype is for a 6-person group. Warn rather than fail
    # so the facilitator can rehearse with fewer participants.
    if len(participants) != 6:
        print(
            f"warning: expected 6 participants, found {len(participants)}",
            file=sys.stderr,
        )

    whisper_raw = raw.get("whisper") or {}
    if not isinstance(whisper_raw, dict):
        raise ConfigError("`whisper` must be a mapping if provided")
    whisper = WhisperConfig(
        model=str(whisper_raw.get("model", "medium")),
        models_dir=str(whisper_raw.get("models_dir", "models/")),
    )

    return SessionConfig(
        session_id=str(raw["session_id"]).strip(),
        question=str(raw["question"]).strip(),
        context=str(raw.get("context", "")).strip(),
        community_context=str(raw.get("community_context", "")).strip(),
        participants=participants,
        language=str(raw.get("language", "auto")).strip() or "auto",
        facilitator_model=str(raw.get("facilitator_model", "claude-sonnet-4-5")),
        synthesis_model=str(raw.get("synthesis_model", "claude-sonnet-4-5")),
        whisper=whisper,
        config_path=config_path,
    )


def load_secrets() -> Secrets:
    load_dotenv(override=False)
    return Secrets(
        anthropic_api_key=_require_env("ANTHROPIC_API_KEY"),
        telegram_bot_token=_require_env("TELEGRAM_BOT_TOKEN"),
    )


def check_ffmpeg_available() -> None:
    """Voice transcription requires ffmpeg to convert .ogg/Opus -> 16 kHz WAV."""
    if shutil.which("ffmpeg") is None:
        raise ConfigError(
            "ffmpeg is not on PATH. Install it (e.g. `brew install ffmpeg` on macOS, "
            "`apt install ffmpeg` on Debian/Ubuntu). Voice messages cannot be "
            "transcribed without it."
        )


def load_app_config(
    session_config_path: str | Path, *, require_ffmpeg: bool = True
) -> AppConfig:
    session = load_session_config(session_config_path)
    secrets = load_secrets()
    if require_ffmpeg:
        check_ffmpeg_available()

    data_dir = Path("data") / session.session_id
    data_dir.mkdir(parents=True, exist_ok=True)

    syntheses_dir = Path("syntheses")
    syntheses_dir.mkdir(parents=True, exist_ok=True)

    proposals_dir = Path("proposals")
    proposals_dir.mkdir(parents=True, exist_ok=True)

    if require_ffmpeg:
        Path(session.whisper.models_dir).mkdir(parents=True, exist_ok=True)

    return AppConfig(
        session=session,
        secrets=secrets,
        data_dir=data_dir,
        syntheses_dir=syntheses_dir,
        proposals_dir=proposals_dir,
    )
