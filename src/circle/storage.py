"""Atomic per-participant JSON storage.

One file per participant per session, keyed by Telegram user id. Atomic write
via tmpfile + rename so that an unexpected crash never leaves a half-written
file on disk (PRD section 5.4: state must be persisted after every message).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


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
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{telegram_user_id}.",
        suffix=".json.tmp",
        dir=data_dir,
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


def list_participant_files(data_dir: Path) -> list[Path]:
    if not data_dir.exists():
        return []
    return sorted(p for p in data_dir.glob("*.json") if not p.name.startswith("."))
