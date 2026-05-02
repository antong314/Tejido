"""Session — the durable, admin-managed unit of configuration.

Replaces the old YAML-per-session model. Each Session lives as a JSON file
at `config/sessions/<id>.json` and represents one "workspace" the
facilitator can run conversations against.

A session's shape is workflow-typed:
  * `common` holds settings that apply to every workflow (model choices,
    language, expected duration, optional persona override).
  * `workflow_data` is a dict whose shape is defined by the workflow type's
    schema (see `circle.workflows`). Validated on load and on save.

The web URL `/s/<session_id>` is `/s/<session.id>`. Per-participant data
files still live at `data/<session.id>/<participant_id>.json`.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .workflows import WorkflowDataError, get_workflow, validate_workflow_data


# IDs go in URLs and on the filesystem. Keep them safe and predictable.
_SESSION_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class SessionError(Exception):
    """Base class for session-validation problems."""


class InvalidSessionIdError(SessionError):
    pass


class SessionFileError(SessionError):
    pass


@dataclass(frozen=True)
class WhisperSettings:
    model: str = "medium"
    models_dir: str = "models/"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "WhisperSettings":
        raw = raw or {}
        return cls(
            model=str(raw.get("model", "medium")),
            models_dir=str(raw.get("models_dir", "models/")),
        )


FacilitationDepth = str  # one of: "minimal" | "medium" | "deep"
_VALID_DEPTHS = frozenset({"minimal", "medium", "deep"})


@dataclass(frozen=True)
class CommonSettings:
    facilitator_model: str = "claude-sonnet-4-6"
    synthesis_model: str = "claude-opus-4-6"
    language: str = "auto"
    # Target conversation length. Drives a pacing block injected into the
    # facilitator's system prompt; not a hard cap. See
    # `circle.prompts.DEPTH_BLOCKS` for the exact text per setting.
    facilitation_depth: FacilitationDepth = "medium"
    # Slug reference into `config/personas/<id>.json`. Empty = fall back
    # to the workflow type's `default_persona` (see `circle.workflows`).
    ai_persona_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "CommonSettings":
        raw = raw or {}
        depth = str(raw.get("facilitation_depth", "medium")) or "medium"
        if depth not in _VALID_DEPTHS:
            depth = "medium"
        # Backward compat: pre-personas configs stored a free-text
        # `ai_persona` field. We don't try to migrate the text into a
        # persona (that's an admin decision); we just drop it. New configs
        # use `ai_persona_id`.
        ai_persona_id = str(raw.get("ai_persona_id", "")).strip()
        return cls(
            facilitator_model=str(raw.get("facilitator_model", "claude-sonnet-4-6")),
            synthesis_model=str(raw.get("synthesis_model", "claude-opus-4-6")),
            language=str(raw.get("language", "auto")) or "auto",
            facilitation_depth=depth,
            ai_persona_id=ai_persona_id,
        )


@dataclass
class Session:
    id: str
    title: str
    workflow_type: str
    created_at: str  # ISO-8601 UTC
    common: CommonSettings = field(default_factory=CommonSettings)
    whisper: WhisperSettings = field(default_factory=WhisperSettings)
    workflow_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _SESSION_ID_PATTERN.match(self.id):
            raise InvalidSessionIdError(
                f"Invalid session id {self.id!r}: must match {_SESSION_ID_PATTERN.pattern}"
            )
        # Reject unknown workflow_type and bad workflow_data shape.
        get_workflow(self.workflow_type)
        validate_workflow_data(self.workflow_type, self.workflow_data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "workflow_type": self.workflow_type,
            "created_at": self.created_at,
            "common": self.common.to_dict(),
            "whisper": self.whisper.to_dict(),
            "workflow_data": dict(self.workflow_data),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Session":
        try:
            return cls(
                id=str(raw["id"]),
                title=str(raw.get("title", raw["id"])),
                workflow_type=str(raw["workflow_type"]),
                created_at=str(raw.get("created_at", _now_iso())),
                common=CommonSettings.from_dict(raw.get("common")),
                whisper=WhisperSettings.from_dict(raw.get("whisper")),
                workflow_data=dict(raw.get("workflow_data") or {}),
            )
        except KeyError as exc:
            raise SessionError(f"Session JSON missing required field: {exc.args[0]}") from exc


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_session(
    *,
    id: str,
    title: str,
    workflow_type: str,
    common: CommonSettings | None = None,
    whisper: WhisperSettings | None = None,
    workflow_data: dict[str, Any] | None = None,
) -> Session:
    """Construct a session with a fresh `created_at` timestamp."""
    return Session(
        id=id,
        title=title,
        workflow_type=workflow_type,
        created_at=_now_iso(),
        common=common or CommonSettings(),
        whisper=whisper or WhisperSettings(),
        workflow_data=dict(workflow_data or {}),
    )


# ---------------------------------------------------------------------------
# JSON persistence — atomic write via tmpfile + rename, same pattern as
# circle.storage. Sessions are committed to git, so durability matters but
# the volume is small.


def session_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.json"


def load_session_from_path(path: Path) -> Session:
    if not path.exists():
        raise SessionFileError(f"Session file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as h:
            raw = json.load(h)
    except json.JSONDecodeError as exc:
        raise SessionFileError(f"Could not parse {path}: {exc}") from exc
    return Session.from_dict(raw)


def load_session(session_id: str, sessions_dir: Path) -> Session:
    return load_session_from_path(session_path(sessions_dir, session_id))


def save_session(session: Session, sessions_dir: Path) -> Path:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    final_path = session_path(sessions_dir, session.id)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{session.id}.", suffix=".json.tmp", dir=sessions_dir
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            json.dump(session.to_dict(), h, ensure_ascii=False, indent=2)
            h.flush()
            os.fsync(h.fileno())
        os.replace(tmp_name, final_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return final_path


def list_session_ids(sessions_dir: Path) -> list[str]:
    if not sessions_dir.exists():
        return []
    ids: list[str] = []
    for p in sorted(sessions_dir.glob("*.json")):
        # Skip hidden / underscore-prefixed bookkeeping files.
        if p.name.startswith(".") or p.name.startswith("_"):
            continue
        ids.append(p.stem)
    return ids


def delete_session(session_id: str, sessions_dir: Path) -> bool:
    """Delete the JSON config. Returns True if it existed.

    Per-participant data under `data/<session_id>/` is NOT touched.
    """
    path = session_path(sessions_dir, session_id)
    if not path.exists():
        return False
    path.unlink()
    return True


__all__ = [
    "CommonSettings",
    "InvalidSessionIdError",
    "Session",
    "SessionError",
    "SessionFileError",
    "WhisperSettings",
    "WorkflowDataError",
    "delete_session",
    "list_session_ids",
    "load_session",
    "load_session_from_path",
    "new_session",
    "save_session",
    "session_path",
]
