"""Personas — reusable AI facilitator voices, managed independently of sessions.

A `Persona` is a named, free-form prompt fragment that gets dropped into the
{PERSONA} slot of the facilitator system prompt. Personas live as JSON files
under `config/personas/<id>.json` so they can be hand-edited in git just like
sessions.

A session references a persona by id via `common.ai_persona_id`. Empty id
means "fall back to the workflow type's `default_persona`" (the same
behavior we had before personas existed as first-class objects). This keeps
brand-new sessions working with zero persona configuration.

We seed three defaults on startup — one per workflow type — so the picker
in the admin UI always has something to show. Admins are free to delete or
edit them; nothing in the runtime requires that the seeded set be present.
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


# Slugs for personas live in URLs and on the filesystem. Same constraints as
# session ids; we intentionally don't share the regex object so changes here
# can't accidentally affect session validation.
_PERSONA_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class PersonaError(Exception):
    """Base class for persona-validation problems."""


class InvalidPersonaIdError(PersonaError):
    pass


class PersonaFileError(PersonaError):
    pass


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    prompt: str
    description: str = ""

    def __post_init__(self) -> None:
        if not _PERSONA_ID_PATTERN.match(self.id):
            raise InvalidPersonaIdError(
                f"Invalid persona id {self.id!r}: must match "
                f"{_PERSONA_ID_PATTERN.pattern}"
            )
        if not self.name.strip():
            raise PersonaError("Persona name cannot be empty.")
        if not self.prompt.strip():
            raise PersonaError("Persona prompt cannot be empty.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Persona":
        try:
            return cls(
                id=str(raw["id"]),
                name=str(raw["name"]),
                prompt=str(raw["prompt"]),
                description=str(raw.get("description", "")),
            )
        except KeyError as exc:
            raise PersonaError(
                f"Persona JSON missing required field: {exc.args[0]}"
            ) from exc


# ---------------------------------------------------------------------------
# JSON persistence — same atomic-write pattern as sessions.


def persona_path(personas_dir: Path, persona_id: str) -> Path:
    return personas_dir / f"{persona_id}.json"


def load_persona_from_path(path: Path) -> Persona:
    if not path.exists():
        raise PersonaFileError(f"Persona file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as h:
            raw = json.load(h)
    except json.JSONDecodeError as exc:
        raise PersonaFileError(f"Could not parse {path}: {exc}") from exc
    return Persona.from_dict(raw)


def load_persona(persona_id: str, personas_dir: Path) -> Persona:
    return load_persona_from_path(persona_path(personas_dir, persona_id))


def save_persona(persona: Persona, personas_dir: Path) -> Path:
    personas_dir.mkdir(parents=True, exist_ok=True)
    final_path = persona_path(personas_dir, persona.id)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{persona.id}.", suffix=".json.tmp", dir=personas_dir
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            json.dump(persona.to_dict(), h, ensure_ascii=False, indent=2)
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


def list_persona_ids(personas_dir: Path) -> list[str]:
    if not personas_dir.exists():
        return []
    ids: list[str] = []
    for p in sorted(personas_dir.glob("*.json")):
        if p.name.startswith(".") or p.name.startswith("_"):
            continue
        ids.append(p.stem)
    return ids


def list_personas(personas_dir: Path) -> list[Persona]:
    """All personas on disk in id order. Skips ones that fail to parse."""
    out: list[Persona] = []
    for pid in list_persona_ids(personas_dir):
        try:
            out.append(load_persona(pid, personas_dir))
        except PersonaError as exc:
            logger.warning("skipping invalid persona %s: %s", pid, exc)
            continue
    return out


def delete_persona(persona_id: str, personas_dir: Path) -> bool:
    path = persona_path(personas_dir, persona_id)
    if not path.exists():
        return False
    path.unlink()
    return True


# ---------------------------------------------------------------------------
# Seeding — write the three workflow-default personas if the dir is empty.
# Idempotent: re-running does nothing when files already exist.


def seed_default_personas(personas_dir: Path) -> list[Persona]:
    """Make sure the three baseline personas exist on disk.

    Pulls the per-workflow `default_persona` text from `circle.workflows`
    so the seeded personas track any future edits to the defaults.
    Existing files (matching ids) are NOT overwritten — admins may have
    edited them.
    """
    # Local import: workflows imports nothing from personas, but personas
    # only needs WORKFLOW_TYPES at seed time, not at module import.
    from .workflows import WORKFLOW_TYPES

    personas_dir.mkdir(parents=True, exist_ok=True)
    seeded: list[Persona] = []
    for wf_type, schema in WORKFLOW_TYPES.items():
        pid = f"{wf_type}__default"
        if persona_path(personas_dir, pid).exists():
            continue
        persona = Persona(
            id=pid,
            name=f"{schema.label} — default",
            description=(
                f"Default facilitator voice for {schema.label.lower()} "
                f"workflows. Edit freely or duplicate to make a variant."
            ),
            prompt=schema.default_persona,
        )
        save_persona(persona, personas_dir)
        seeded.append(persona)
        logger.info("seeded default persona id=%s", pid)
    return seeded


def resolve_persona_text(
    persona_id: str | None,
    personas_dir: Path,
    *,
    fallback: str,
) -> str:
    """Look up a persona's prompt by id; fall back when missing or empty.

    Used by the runtime to assemble the facilitator system prompt. The
    fallback is typically the workflow type's `default_persona` so a
    session whose persona was deleted out from under it still produces a
    sensible prompt instead of crashing.
    """
    pid = (persona_id or "").strip()
    if not pid:
        return fallback
    try:
        return load_persona(pid, personas_dir).prompt
    except PersonaError as exc:
        logger.warning(
            "persona id=%s referenced but not loadable (%s); using fallback",
            pid,
            exc,
        )
        return fallback


__all__ = [
    "InvalidPersonaIdError",
    "Persona",
    "PersonaError",
    "PersonaFileError",
    "delete_persona",
    "list_persona_ids",
    "list_personas",
    "load_persona",
    "load_persona_from_path",
    "persona_path",
    "resolve_persona_text",
    "save_persona",
    "seed_default_personas",
]
