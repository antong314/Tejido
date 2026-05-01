"""Shared identity helpers — name normalization and dupe detection.

Used by the web `/join` endpoint to enforce unique display names within a
session. Telegram doesn't need this (a user's `telegram_user_id` already
disambiguates them, and the rare case of two `first_name="Anton"`s shows
up as two "Anton"s in the synthesis — we accept that for the prototype).

The on-disk source of truth is `_index.json` in the session's data
directory, populated by `BotContext.load_or_create` whenever a new
participant joins. This module is the read-side: it never mutates the
index, only inspects it.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from ..storage import read_index


# A web display name must be at least one printable character and short
# enough to keep formatting predictable in synthesis output.
MAX_DISPLAY_NAME_LENGTH = 60


class NameTakenError(ValueError):
    """Raised when a candidate display name is already in use this session."""


class InvalidNameError(ValueError):
    """Raised for empty / overlong / unprintable names."""


def normalize_name(raw: str) -> str:
    """Return the comparison-form of a display name (case + whitespace insensitive)."""
    return " ".join(raw.split()).lower()


def validate_display_name(raw: str) -> str:
    """Return the trimmed-but-original-cased display name, or raise InvalidNameError.

    Doesn't check uniqueness — that's `is_name_taken`'s job. This is only
    syntactic validation: non-empty, not too long, no control characters.
    """
    if not isinstance(raw, str):
        raise InvalidNameError("Name must be a string")
    trimmed = " ".join(raw.split())
    if not trimmed:
        raise InvalidNameError("Name cannot be empty")
    if len(trimmed) > MAX_DISPLAY_NAME_LENGTH:
        raise InvalidNameError(
            f"Name must be {MAX_DISPLAY_NAME_LENGTH} characters or fewer"
        )
    if any(ord(c) < 32 for c in trimmed):
        raise InvalidNameError("Name contains control characters")
    return trimmed


def is_name_taken(
    data_dir: Path,
    candidate: str,
    *,
    except_participant_id: str | None = None,
) -> bool:
    """Has someone else in this session already claimed this normalized name?

    `except_participant_id` lets the same participant re-confirm their own
    name without a false positive (e.g. on a Telegram /restart followed by
    a /start, where their participant_id stays the same).
    """
    target = normalize_name(candidate)
    if not target:
        return False
    index = read_index(data_dir)
    for participant_id, name in index.items():
        if except_participant_id is not None and participant_id == except_participant_id:
            continue
        if normalize_name(name) == target:
            return True
    return False


def claim_name(data_dir: Path, raw_name: str) -> tuple[str, str]:
    """Validate, dupe-check, and allocate a fresh participant_id for a web joiner.

    Returns `(participant_id, display_name)`. The caller (the web `/join`
    handler) then constructs the `ParticipantState` via
    `BotContext.load_or_create`, which writes the index entry.

    Raises `InvalidNameError` if the name is malformed; raises
    `NameTakenError` if it conflicts with an existing participant.

    Note: this function does NOT itself write to `_index.json` — it just
    allocates a fresh UUID and validates the name. Persistence happens
    when the caller calls `load_or_create`. That keeps a single source of
    truth for "a participant exists" (their JSON file).
    """
    display_name = validate_display_name(raw_name)
    if is_name_taken(data_dir, display_name):
        raise NameTakenError(
            f"The name {display_name!r} is already in use in this session"
        )
    participant_id = uuid.uuid4().hex
    return participant_id, display_name


__all__ = [
    "InvalidNameError",
    "MAX_DISPLAY_NAME_LENGTH",
    "NameTakenError",
    "claim_name",
    "is_name_taken",
    "normalize_name",
    "validate_display_name",
]
