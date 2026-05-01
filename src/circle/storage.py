"""Atomic per-participant JSON storage.

One file per participant per session, keyed by the canonical participant_id
(`str(telegram_user_id)` for Telegram joiners, a UUID for web joiners).
Atomic write via tmpfile + rename so that an unexpected crash never leaves
a half-written file on disk (PRD section 5.4: state must be persisted after
every message).

The session directory also contains a small `_index.json` cache of
`{participant_id: display_name}`. It's used by the web `/join` endpoint for
fast dupe-checking and by the dashboard to list joined participants. The
index is rebuildable from the per-participant JSONs at any time — it's a
cache, not the source of truth.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


_INDEX_FILENAME = "_index.json"


def participant_path(data_dir: Path, telegram_user_id: int | str) -> Path:
    return data_dir / f"{telegram_user_id}.json"


def load_participant(data_dir: Path, telegram_user_id: int | str) -> dict[str, Any] | None:
    path = participant_path(data_dir, telegram_user_id)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_participant(
    data_dir: Path, telegram_user_id: int | str, payload: dict[str, Any]
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    final_path = participant_path(data_dir, telegram_user_id)
    _atomic_write_json(final_path, payload, prefix=f".{telegram_user_id}.")


def list_participant_files(data_dir: Path) -> list[Path]:
    """Per-participant JSONs only.

    Hidden tmp files (`.<id>.json.tmp`) and underscore-prefixed bookkeeping
    files (`_index.json`) are excluded so callers like synthesis and the
    dashboard see only real participants.
    """
    if not data_dir.exists():
        return []
    return sorted(
        p
        for p in data_dir.glob("*.json")
        if not p.name.startswith(".") and not p.name.startswith("_")
    )


# ---------------------------------------------------------------------------
# Session index — name lookup for the web join endpoint and the dashboard.


def _index_path(data_dir: Path) -> Path:
    return data_dir / _INDEX_FILENAME


def read_index(data_dir: Path) -> dict[str, str]:
    """Return {participant_id: display_name} for this session, empty if none."""
    path = _index_path(data_dir)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def register_in_index(
    data_dir: Path, participant_id: str, display_name: str
) -> None:
    """Add (or update) one entry in the session's index file.

    Idempotent — re-registering the same participant_id with the same name
    is a no-op. Updating their name (rare, e.g. /rename in the future) just
    overwrites the value.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    index = read_index(data_dir)
    if index.get(participant_id) == display_name:
        return
    index[participant_id] = display_name
    _atomic_write_json(_index_path(data_dir), index, prefix="._index.")


# ---------------------------------------------------------------------------


def _atomic_write_json(final_path: Path, payload: Any, *, prefix: str) -> None:
    fd, tmp_name = tempfile.mkstemp(
        prefix=prefix,
        suffix=".json.tmp",
        dir=final_path.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, final_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
