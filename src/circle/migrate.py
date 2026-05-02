"""One-shot migration: convert YAML session configs to JSON sessions.

Reads each `config/session_*.yaml` (excluding the example template),
writes the corresponding `config/sessions/<id>.json` in the new
workflow-typed format, and (with --delete) removes the old YAML files.

The old YAMLs are flat single-question configs; they all become
`workflow_type: open_discussion` in the new format. Other workflow
types are created via the admin UI going forward.

Usage:
    python -m circle.migrate              # dry-run preview
    python -m circle.migrate --apply      # write the JSON files
    python -m circle.migrate --apply --delete   # also delete the YAMLs
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .session import (
    CommonSettings,
    Session,
    WhisperSettings,
    save_session,
)


CONFIG_DIR = Path("config")
SESSIONS_DIR = CONFIG_DIR / "sessions"


def _to_session(yaml_path: Path) -> Session:
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}

    session_id = str(raw.get("session_id") or yaml_path.stem.replace("session_", ""))
    title = session_id.replace("_", " ").replace("-", " ").title()
    created_at = datetime.fromtimestamp(
        yaml_path.stat().st_mtime, tz=timezone.utc
    ).isoformat()

    common = CommonSettings(
        facilitator_model=str(raw.get("facilitator_model", "claude-sonnet-4-5")),
        synthesis_model=str(raw.get("synthesis_model", "claude-opus-4-7")),
        language=str(raw.get("language", "auto")) or "auto",
        expected_duration_minutes=10,
        ai_persona="",  # use the workflow default
    )

    whisper_raw = raw.get("whisper") or {}
    whisper = WhisperSettings(
        model=str(whisper_raw.get("model", "medium")),
        models_dir=str(whisper_raw.get("models_dir", "models/")),
    )

    workflow_data: dict = {
        "question": str(raw.get("question", "")).strip(),
    }
    context = str(raw.get("context", "")).strip()
    if context:
        workflow_data["context"] = context
    community = str(raw.get("community_context", "")).strip()
    if community:
        workflow_data["community_context"] = community

    return Session(
        id=session_id,
        title=title,
        workflow_type="open_discussion",
        created_at=created_at,
        common=common,
        whisper=whisper,
        workflow_data=workflow_data,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert legacy YAML session configs to JSON sessions."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the JSON files (default is dry-run preview).",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete the old YAML files after conversion. Implies --apply.",
    )
    args = parser.parse_args()

    apply = args.apply or args.delete
    delete = args.delete

    yaml_paths = sorted(
        p for p in CONFIG_DIR.glob("session_*.yaml")
        if p.name != "session_config.example.yaml"
    )
    if not yaml_paths:
        print("no YAML session configs found")
        return

    for path in yaml_paths:
        try:
            session = _to_session(path)
        except Exception as exc:
            print(f"  SKIP {path.name}: {exc}", file=sys.stderr)
            continue
        target = SESSIONS_DIR / f"{session.id}.json"
        verb = "would write" if not apply else ("WROTE" if apply else "?")
        print(f"  {path.name} -> {target}  [{session.workflow_type}]")
        if apply:
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            save_session(session, SESSIONS_DIR)
            if delete:
                path.unlink()
                print(f"    deleted {path.name}")

    if not apply:
        print()
        print("(dry run — pass --apply to write JSON files, --delete to also remove YAMLs)")


if __name__ == "__main__":
    main()
