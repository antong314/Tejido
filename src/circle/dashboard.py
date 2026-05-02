"""Facilitator dashboard.

Shows the table of {participant, phase, duration_in_phase, total_time}
for every participant who has joined the session, refreshed every 2
seconds. Reads JSON files only — never imports the bot or sees any
message content. No conversation text is rendered (PRD section 5.1).

The participant list per session comes from `_index.json` (cache of
{participant_id: display_name} updated whenever someone joins),
falling back to scanning the per-participant JSONs.

Usage:
    python -m circle.dashboard --session bylaws_v2
    python -m circle.dashboard                    # list all sessions
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.table import Table

from .config import ConfigError, load_app_config
from .session import list_session_ids, load_session
from .state import Phase
from .storage import list_participant_files, read_index


REFRESH_SECONDS = 2.0


PHASE_DISPLAY: dict[Phase, str] = {
    Phase.NOT_STARTED: "not started",
    Phase.AWAITING_CONSENT: "awaiting consent",
    Phase.IN_CONVERSATION: "in conversation",
    Phase.IN_PERMISSIONS: "in permissions",
    Phase.AWAITING_ADDITION: "awaiting addition",
    Phase.IN_ADDITION_PERMISSIONS: "addition permissions",
    Phase.COMPLETE: "complete",
}


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    minutes = int(seconds // 60)
    if minutes < 1:
        return "<1 min"
    return f"{minutes} min"


def _seconds_since(iso_timestamp: str | None) -> float | None:
    if not iso_timestamp:
        return None
    try:
        ts = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    return max(0.0, (now - ts).total_seconds())


def _duration_between(start_iso: str | None, end_iso: str | None) -> float | None:
    if not start_iso or not end_iso:
        return None
    try:
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)
    except ValueError:
        return None
    return max(0.0, (end - start).total_seconds())


def _load_state_summaries(data_dir: Path) -> dict[str, dict]:
    """Return {participant_id: state_dict}."""
    summaries: dict[str, dict] = {}
    for path in list_participant_files(data_dir):
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        pid = str(raw.get("participant_id") or path.stem)
        summaries[pid] = raw
    return summaries


def _build_session_table(data_dir: Path, title: str) -> Table:
    table = Table(
        title=title,
        title_style="bold",
        show_lines=True,
    )
    table.add_column("Participant", style="bold")
    table.add_column("Phase")
    table.add_column("Duration in phase", justify="right")
    table.add_column("Total time", justify="right")

    summaries = _load_state_summaries(data_dir)
    if not summaries:
        table.add_row("[dim]nobody has joined yet[/dim]", "—", "—", "—")
        return table

    index = read_index(data_dir)
    ordered_pids: list[str] = []
    for pid in index:
        if pid in summaries:
            ordered_pids.append(pid)
    for pid in summaries:
        if pid not in ordered_pids:
            ordered_pids.append(pid)

    for pid in ordered_pids:
        state = summaries[pid]
        display_name = state.get("participant_name") or index.get(pid) or pid
        phase_value = state.get("phase", Phase.NOT_STARTED.value)
        try:
            phase = Phase(phase_value)
        except ValueError:
            phase = Phase.NOT_STARTED
        phase_label = PHASE_DISPLAY[phase]

        if phase == Phase.COMPLETE:
            phase_label = f"[green]{phase_label}[/green]"
            duration_in_phase = "—"
        else:
            duration_in_phase = _format_duration(
                _seconds_since(state.get("phase_entered_at"))
            )

        if phase == Phase.COMPLETE:
            total_str = _format_duration(
                _duration_between(state.get("started_at"), state.get("completed_at"))
            )
        else:
            total_str = _format_duration(_seconds_since(state.get("started_at")))

        table.add_row(display_name, phase_label, duration_in_phase, total_str)

    return table


def _build_sessions_overview(app_config) -> Table:
    """No --session given → list every session and how many joined."""
    table = Table(
        title="Tejido — all sessions",
        title_style="bold",
        show_lines=True,
    )
    table.add_column("Session id", style="bold")
    table.add_column("Title")
    table.add_column("Workflow")
    table.add_column("Joined", justify="right")

    ids = list_session_ids(app_config.sessions_dir)
    if not ids:
        table.add_row("[dim]no sessions configured[/dim]", "—", "—", "—")
        return table
    for sid in ids:
        try:
            s = load_session(sid, app_config.sessions_dir)
        except Exception:
            table.add_row(sid, "[red]invalid config[/red]", "—", "—")
            continue
        idx = read_index(app_config.data_dir_for(sid))
        table.add_row(sid, s.title, s.workflow_type, str(len(idx)))
    return table


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Facilitator dashboard — phase + duration per participant."
    )
    parser.add_argument(
        "--session",
        help="Session id to monitor. If omitted, lists every session.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print the table once and exit (useful for scripting).",
    )
    args = parser.parse_args()

    try:
        app_config = load_app_config(require_ffmpeg=False)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    console = Console()

    if args.session:
        try:
            session = load_session(args.session, app_config.sessions_dir)
        except Exception as exc:
            print(f"could not load session {args.session!r}: {exc}", file=sys.stderr)
            sys.exit(2)
        data_dir = app_config.data_dir_for(session.id)
        title = f"Tejido — {session.title} ({session.id}) — {session.workflow_type}"
        if args.once:
            console.print(_build_session_table(data_dir, title))
            return
        try:
            with Live(
                _build_session_table(data_dir, title),
                refresh_per_second=2,
                console=console,
            ) as live:
                while True:
                    time.sleep(REFRESH_SECONDS)
                    live.update(_build_session_table(data_dir, title))
        except KeyboardInterrupt:
            pass
    else:
        if args.once:
            console.print(_build_sessions_overview(app_config))
            return
        try:
            with Live(
                _build_sessions_overview(app_config),
                refresh_per_second=2,
                console=console,
            ) as live:
                while True:
                    time.sleep(REFRESH_SECONDS)
                    live.update(_build_sessions_overview(app_config))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
