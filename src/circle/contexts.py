"""Context Library — reusable community-context blobs referenced by sessions.

Community context (shared values, prior decisions, named principles, etc.)
is about WHO the community is, not about WHAT kind of conversation we're
having — so it's orthogonal to workflow type. The same context is
naturally reused across many sessions for the same community. That makes
it a first-class reusable object: managed at /admin/contexts, referenced
from a session via `common.community_context_id`.

Storage: one JSON file per context at `config/contexts/<id>.json`. Same
atomic-write tmpfile-then-rename pattern as sessions/personas/workflows.

Empty `community_context_id` on a session means no community context —
the synthesis/proposal/revise prompts handle this with their existing
"if empty, ignore" instructions.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_CONTEXT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class ContextError(Exception):
    """Base class for context-validation problems."""


class InvalidContextIdError(ContextError):
    pass


class ContextFileError(ContextError):
    pass


@dataclass(frozen=True)
class Context:
    """Reusable community-context blob.

    Just three fields — id (slug, used in URLs and filenames; immutable
    after creation), name (human-readable, shown in dropdowns), and text
    (the actual context content embedded into output prompts). The id
    is typically derived client-side by slugifying the name on create.
    """

    id: str
    name: str
    text: str

    def __post_init__(self) -> None:
        if not _CONTEXT_ID_PATTERN.match(self.id):
            raise InvalidContextIdError(
                f"Invalid context id {self.id!r}: must match "
                f"{_CONTEXT_ID_PATTERN.pattern}"
            )
        if not self.name.strip():
            raise ContextError("Context name cannot be empty.")
        if not self.text.strip():
            raise ContextError("Context text cannot be empty.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Context":
        try:
            return cls(
                id=str(raw["id"]),
                name=str(raw["name"]),
                text=str(raw["text"]),
            )
        except KeyError as exc:
            raise ContextError(
                f"Context JSON missing required field: {exc.args[0]}"
            ) from exc


# ---------------------------------------------------------------------------
# JSON persistence


def context_path(contexts_dir: Path, context_id: str) -> Path:
    return contexts_dir / f"{context_id}.json"


def load_context_from_path(path: Path) -> Context:
    if not path.exists():
        raise ContextFileError(f"Context file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as h:
            raw = json.load(h)
    except json.JSONDecodeError as exc:
        raise ContextFileError(f"Could not parse {path}: {exc}") from exc
    return Context.from_dict(raw)


def load_context(context_id: str, contexts_dir: Path) -> Context:
    return load_context_from_path(context_path(contexts_dir, context_id))


def save_context(context: Context, contexts_dir: Path) -> Path:
    contexts_dir.mkdir(parents=True, exist_ok=True)
    final_path = context_path(contexts_dir, context.id)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{context.id}.", suffix=".json.tmp", dir=contexts_dir
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            json.dump(context.to_dict(), h, ensure_ascii=False, indent=2)
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


def list_context_ids(contexts_dir: Path) -> list[str]:
    if not contexts_dir.exists():
        return []
    ids: list[str] = []
    for p in sorted(contexts_dir.glob("*.json")):
        if p.name.startswith(".") or p.name.startswith("_"):
            continue
        ids.append(p.stem)
    return ids


def list_contexts(contexts_dir: Path) -> list[Context]:
    """All contexts on disk in id order. Skips ones that fail to parse."""
    out: list[Context] = []
    for cid in list_context_ids(contexts_dir):
        try:
            out.append(load_context(cid, contexts_dir))
        except ContextError as exc:
            logger.warning("skipping invalid context %s: %s", cid, exc)
            continue
    return out


def delete_context(context_id: str, contexts_dir: Path) -> bool:
    path = context_path(contexts_dir, context_id)
    if not path.exists():
        return False
    path.unlink()
    return True


# ---------------------------------------------------------------------------
# Resolver — what the runtime calls to get the effective context text.


def resolve_text(
    context_id: str | None,
    contexts_dir: Path,
) -> str:
    """Resolve a context id to its text. Returns "" for empty/missing ids.

    Used by the synthesis/proposal/revise processors via
    `circle.workflows.get_community_context`. A missing context (deleted
    out from under a session that still references it) silently falls back
    to empty — the output processors handle empty community context fine.
    """
    cid = (context_id or "").strip()
    if not cid:
        return ""
    try:
        return load_context(cid, contexts_dir).text
    except ContextError as exc:
        logger.warning(
            "context id=%s referenced but not loadable (%s); using empty",
            cid,
            exc,
        )
        return ""


__all__ = [
    "Context",
    "ContextError",
    "ContextFileError",
    "InvalidContextIdError",
    "context_path",
    "delete_context",
    "list_context_ids",
    "list_contexts",
    "load_context",
    "load_context_from_path",
    "resolve_text",
    "save_context",
]
