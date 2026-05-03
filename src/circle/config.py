"""App-level configuration — shared resources, secrets, on-disk locations.

Independent of any specific session. Per-session configuration lives in
`circle.session.Session` (loaded from `config/sessions/<id>.json`).

`AppConfig` is constructed once at startup; the SessionRegistry then uses
its paths and secrets to materialize session-specific BotContexts on
demand.

Local vs deployed paths
-----------------------
By default the on-disk locations are repo-relative (`config/sessions`,
`data/`, etc.) — the way the project runs on a developer laptop with
git as the source of truth.

For a deployment that needs durable storage on a separate volume
(Railway, Fly, Docker on a VPS, etc.), set the env var
`TEJIDO_DATA_ROOT=/some/mount`. All seven on-disk locations then hang
off that root:

    $TEJIDO_DATA_ROOT/
        config/sessions/        — admin-managed session JSONs
        config/contexts/        — admin-managed Context Library entries
        config/workflows/       — admin-edited workflow prompt overrides
        data/<session_id>/...   — per-participant transcripts & state
        syntheses/              — synthesis output markdown files
        proposals/              — proposal output markdown files
        revisions/              — revise output markdown files
        models/                 — Whisper model cache (lazy-downloaded)

A first-run seeding step copies the bundled defaults from the image's
config/ directory into the volume's config/ subdirs only if they're
missing — admin edits made via the UI are never overwritten on redeploy.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


# Subdirectory layout used both for local-relative paths and (under
# TEJIDO_DATA_ROOT) for deployment paths. Keep these names in sync with
# the AppConfig dataclass field defaults below.
_SESSIONS_SUBDIR = Path("config/sessions")
_WORKFLOWS_SUBDIR = Path("config/workflows")
_CONTEXTS_SUBDIR = Path("config/contexts")
_DATA_SUBDIR = Path("data")
_SYNTHESES_SUBDIR = Path("syntheses")
_PROPOSALS_SUBDIR = Path("proposals")
_REVISIONS_SUBDIR = Path("revisions")
_MODELS_SUBDIR = Path("models")


def _resolve_dir(subdir: Path) -> Path:
    """Pick the on-disk location for `subdir`.

    With TEJIDO_DATA_ROOT set: $TEJIDO_DATA_ROOT/<subdir>.
    Without: just <subdir> (repo-relative — the laptop case).
    """
    root = os.environ.get("TEJIDO_DATA_ROOT", "").strip()
    if root:
        return Path(root) / subdir
    return subdir


@dataclass(frozen=True)
class Secrets:
    anthropic_api_key: str
    telegram_bot_token: str


@dataclass(frozen=True)
class AppConfig:
    """Process-level configuration shared across all sessions."""

    secrets: Secrets
    sessions_dir: Path = field(default_factory=lambda: _resolve_dir(_SESSIONS_SUBDIR))
    # Per-workflow-type admin overrides for task_framing, output_template,
    # and mechanics live as JSON files here. See circle.workflow_overrides.
    workflows_dir: Path = field(default_factory=lambda: _resolve_dir(_WORKFLOWS_SUBDIR))
    # Reusable community-context blobs, referenced by sessions via
    # common.community_context_id. See circle.contexts.
    contexts_dir: Path = field(default_factory=lambda: _resolve_dir(_CONTEXTS_SUBDIR))
    data_dir_base: Path = field(default_factory=lambda: _resolve_dir(_DATA_SUBDIR))
    syntheses_dir: Path = field(default_factory=lambda: _resolve_dir(_SYNTHESES_SUBDIR))
    proposals_dir: Path = field(default_factory=lambda: _resolve_dir(_PROPOSALS_SUBDIR))
    revisions_dir: Path = field(default_factory=lambda: _resolve_dir(_REVISIONS_SUBDIR))
    models_dir: Path = field(default_factory=lambda: _resolve_dir(_MODELS_SUBDIR))

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


def _seed_volume_from_repo_defaults(config: AppConfig) -> None:
    """First-run: copy bundled config defaults into the volume if missing.

    Only runs when `TEJIDO_DATA_ROOT` is set (so we know we're in a
    deployment scenario where the volume is separate from the image).
    Each subdir is seeded INDEPENDENTLY and ONLY when missing — never
    overwrites an admin-edited file.

    The source of truth for the seed is `<repo_root>/config/{sessions,
    contexts, workflows}/`, which lives inside the image. Output dirs
    (`syntheses/`, `proposals/`, `revisions/`, `data/`, `models/`)
    aren't seeded — they start empty by design.
    """
    if not os.environ.get("TEJIDO_DATA_ROOT", "").strip():
        return

    # Find the repo's config/ directory inside the image. config.py lives
    # at <repo>/src/circle/config.py — three parents up.
    repo_config_dir = Path(__file__).resolve().parents[2] / "config"
    if not repo_config_dir.exists():
        logger.warning(
            "data root seeding requested but image's repo config/ dir not "
            "found at %s — skipping",
            repo_config_dir,
        )
        return

    seedable: list[tuple[Path, Path]] = [
        (repo_config_dir / "sessions", config.sessions_dir),
        (repo_config_dir / "contexts", config.contexts_dir),
        (repo_config_dir / "workflows", config.workflows_dir),
    ]
    for src, dst in seedable:
        if not src.exists():
            continue
        # Seed only if the destination is empty (or missing). An admin
        # who deleted everything via the UI gets a re-seed on next boot,
        # which we accept — better than letting the picker be empty.
        if dst.exists() and any(dst.iterdir()):
            continue
        dst.mkdir(parents=True, exist_ok=True)
        copied = 0
        for entry in src.iterdir():
            if entry.is_file() and entry.suffix == ".json":
                shutil.copy2(entry, dst / entry.name)
                copied += 1
        if copied:
            logger.info(
                "seeded %d file(s) from %s → %s", copied, src, dst
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
    config.models_dir.mkdir(parents=True, exist_ok=True)

    _seed_volume_from_repo_defaults(config)

    return config
