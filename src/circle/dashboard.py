"""Facilitator dashboard.

Implements PRD section 4.6. Shows the table of {participant, phase,
duration_in_phase, total_time} for every participant in the session, refreshed
every 2 seconds. Reads JSON files only — never imports the bot or sees any
message content. Critically, no conversation text is ever rendered (PRD
section 5.1: "Participant conversations are never viewable by the facilitator
or anyone else during the session.").

Usage:
    python -m circle.dashboard --config config/session_config.yaml
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

from .config import ConfigError, load_session_config
from .state import Phase
from .storage import list_participant_files


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


def _load_state_summaries(data_dir: Path) -> list[dict]:
    summaries: list[dict] = []
    for path in list_participant_files(data_dir):
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        summaries.append(raw)
    return summaries


def _build_table(
    data_dir: Path,
    expected: list[tuple[str, str]],
) -> Table:
    """expected: list of (display_name, handle) from the session config."""
    table = Table(
        title=f"Circle session — data dir: {data_dir}",
        title_style="bold",
        show_lines=True,
    )
    table.add_column("Participant", style="bold")
    table.add_column("Handle")
    table.add_column("Phase")
    table.add_column("Duration in phase", justify="right")
    table.add_column("Total time", justify="right")

    summaries = _load_state_summaries(data_dir)
    by_name = {s.get("participant_name", ""): s for s in summaries}

    for display_name, handle in expected:
        state = by_name.get(display_name)
        if state is None:
            table.add_row(display_name, handle, "[dim]not started[/dim]", "—", "—")
            continue
        phase_value = state.get("phase", Phase.NOT_STARTED.value)
        try:
            phase = Phase(phase_value)
        except ValueError:
            phase = Phase.NOT_STARTED
        phase_label = PHASE_DISPLAY[phase]

        if phase == Phase.COMPLETE:
            phase_label = f"[green]{phase_label}[/green]"
            duration_in_phase: str = "—"
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

        table.add_row(display_name, handle, phase_label, duration_in_phase, total_str)

    return table


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Facilitator dashboard — shows phase + duration per participant."
    )
    parser.add_argument(
        "--config",
        default="config/session_config.yaml",
        help="Path to the session config YAML.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print the table once and exit (useful for scripting).",
    )
    args = parser.parse_args()

    try:
        session = load_session_config(args.config)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    data_dir = Path("data") / session.session_id
    expected = [(p.display_name, p.handle) for p in session.participants]
    console = Console()

    if args.once:
        console.print(_build_table(data_dir, expected))
        return

    try:
        with Live(_build_table(data_dir, expected), refresh_per_second=2, console=console) as live:
            while True:
                time.sleep(REFRESH_SECONDS)
                live.update(_build_table(data_dir, expected))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
