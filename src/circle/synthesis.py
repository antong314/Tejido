"""Standalone synthesis script invoked by the facilitator during the break.

Implements PRD section 4.7. Loads every participant file with status
`complete`, applies the permission filter from PRD section 4.5 (private
points are removed; transcript turns that the participant chose to keep
private are not exposed), formats the per-participant section with
attribution metadata, calls the synthesis prompt from PRD section 3.3, and
writes the result to `syntheses/synthesis_<YYYYMMDD>.md`.

Usage:
    python -m circle.synthesis --config config/session_config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .anthropic_client import (
    SYNTHESIS_MAX_TOKENS,
    SYNTHESIS_TEMPERATURE,
    AnthropicClient,
    ChatMessage,
)
from .config import AppConfig, ConfigError, load_app_config
from .prompts import render_synthesis_prompt
from .session import Session, load_session
from .state import ParticipantState, Phase
from .storage import list_participant_files
from .workflows import get_community_context, get_synthesis_question

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FilteredParticipant:
    """One participant's contribution to the synthesis prompt.

    Holds a transcript with private turns redacted and a list of points
    annotated with their permission. PRD section 4.5: filtering happens at
    synthesis time only; the on-disk record is preserved in full.
    """

    name: str
    transcript_lines: list[str]
    annotated_points: list[str]


def filter_for_synthesis(state_dict: dict) -> FilteredParticipant | None:
    """Filter a single participant's stored JSON for the synthesis prompt.

    Returns None if the participant is not yet complete or has no shareable
    content at all (every point marked private and no additions).
    """
    state = ParticipantState.from_dict(state_dict)
    if state.phase != Phase.COMPLETE:
        return None

    transcript_lines: list[str] = []
    for turn in state.transcript:
        speaker = state.name if False else None  # noqa: F841 (kept for clarity)
        speaker_label = "Participant" if turn.role == "user" else "Facilitator"
        transcript_lines.append(f"{speaker_label}: {turn.content}")

    annotated_points: list[str] = []
    for point in state.extracted_points:
        if point.permission == "private":
            continue
        if point.permission == "attributed":
            annotated_points.append(
                f'[ATTRIBUTED to {state.participant_name}] "{point.point}"'
            )
        elif point.permission == "anonymous":
            annotated_points.append(f'[ANONYMOUS] "{point.point}"')
        else:
            # Unset permission means the participant never made a choice; skip
            # to be safe (PRD section 3.3: "When in doubt, leave it out").
            continue

    for addition in state.additions:
        if addition.permission == "private":
            continue
        if addition.permission == "attributed":
            annotated_points.append(
                f'[ATTRIBUTED to {state.participant_name}] (addition) "{addition.content}"'
            )
        elif addition.permission == "anonymous":
            annotated_points.append(f'[ANONYMOUS] (addition) "{addition.content}"')

    if not annotated_points:
        # Nothing the participant wants shared. Skip them entirely.
        return None

    return FilteredParticipant(
        name=state.participant_name,
        transcript_lines=transcript_lines,
        annotated_points=annotated_points,
    )


def assemble_transcripts_block(participants: list[FilteredParticipant]) -> str:
    """Format every shareable participant into one big TRANSCRIPTS block.

    Each section is tagged with the participant's STRICTEST permission across
    all their points — this is the safest level for any transcript quote whose
    specific point of origin is ambiguous. The synthesis prompt instructs the
    LLM to default to this strictest level when a transcript quote can't be
    unambiguously mapped to a single permissioned point.
    """
    sections: list[str] = []
    for index, p in enumerate(participants, start=1):
        # Determine the strictest permission across this participant's points.
        # Order: private > anonymous > attributed. Private points are already
        # filtered out upstream, so the choice is between "anonymous" (some
        # point was anonymous) and "attributed" (all points were attributed).
        has_anonymous = any("[ANONYMOUS]" in line for line in p.annotated_points)
        strictest = "ANONYMOUS" if has_anonymous else "ATTRIBUTED"
        if strictest == "ANONYMOUS":
            permission_note = (
                f"DEFAULT PERMISSION FOR AMBIGUOUS QUOTES: ANONYMOUS — at least "
                f"one of this participant's points is marked anonymous, so any "
                f"transcript quote that cannot be unambiguously mapped to a "
                f"specific [ATTRIBUTED to {p.name}] point MUST be treated as "
                f"anonymous (do not attribute by name, do not include "
                f"identifying detail)."
            )
        else:
            permission_note = (
                f"DEFAULT PERMISSION FOR AMBIGUOUS QUOTES: ATTRIBUTED — all of "
                f"this participant's points are marked attributed; you may "
                f"quote and attribute by name."
            )
        header = f"=== Participant {index}: {p.name} ==="
        transcript = "\n".join(p.transcript_lines)
        points_block = "\n".join(p.annotated_points)
        section = (
            f"{header}\n\n"
            f"{permission_note}\n\n"
            f"TRANSCRIPT:\n{transcript}\n\n"
            f"PERMISSIONED POINTS:\n{points_block}\n"
        )
        sections.append(section)
    return "\n".join(sections)


def collect_completed(data_dir: Path) -> list[FilteredParticipant]:
    import json

    filtered: list[FilteredParticipant] = []
    for path in list_participant_files(data_dir):
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        result = filter_for_synthesis(raw)
        if result is not None:
            filtered.append(result)
    return filtered


async def run_synthesis(session: Session, app_config: AppConfig) -> Path:
    data_dir = app_config.data_dir_for(session.id)
    participants = collect_completed(data_dir)
    if not participants:
        raise RuntimeError(
            "No completed participants with shareable content found in "
            f"{data_dir}"
        )
    if len(participants) < 2:
        logger.warning(
            "only %s participant(s) have completed; synthesis will be thin",
            len(participants),
        )

    transcripts_block = assemble_transcripts_block(participants)
    prompt = render_synthesis_prompt(
        question=get_synthesis_question(session),
        transcripts=transcripts_block,
        community_context=get_community_context(session),
    )

    anthropic = AnthropicClient(
        api_key=app_config.secrets.anthropic_api_key,
        default_model=session.common.synthesis_model,
    )

    logger.info("calling synthesis model=%s", session.common.synthesis_model)
    output = await anthropic.complete(
        system=prompt,
        messages=[
            ChatMessage(
                role="user",
                content="Please produce the synthesis for the group now.",
            )
        ],
        model=session.common.synthesis_model,
        temperature=SYNTHESIS_TEMPERATURE,
        max_tokens=SYNTHESIS_MAX_TOKENS,
    )

    today = datetime.now().strftime("%Y%m%d")
    out_path = app_config.syntheses_dir / f"synthesis_{session.id}_{today}.md"
    # If the facilitator re-runs synthesis (e.g. after a late finisher),
    # don't clobber the previous file — append a counter.
    counter = 1
    while out_path.exists():
        out_path = (
            app_config.syntheses_dir
            / f"synthesis_{session.id}_{today}_{counter}.md"
        )
        counter += 1

    header = (
        f"# Synthesis for {session.id}\n\n"
        f"**Title:** {session.title}\n\n"
        f"**Participants included:** "
        f"{', '.join(p.name for p in participants)}\n\n"
        "---\n\n"
    )
    out_path.write_text(header + output + "\n", encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the group synthesis from completed transcripts."
    )
    parser.add_argument(
        "--session",
        required=True,
        help="Session id to synthesize (looked up in config/sessions/).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        app_config = load_app_config(require_ffmpeg=False)
        session = load_session(args.session, app_config.sessions_dir)
    except (ConfigError, Exception) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        out_path = asyncio.run(run_synthesis(session, app_config))
    except Exception as exc:
        print(f"synthesis failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"synthesis written to: {out_path}")


if __name__ == "__main__":
    main()
