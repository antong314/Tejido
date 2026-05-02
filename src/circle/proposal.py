"""Standalone proposal-mode script — drafts concrete proposal language from
completed transcripts and predicts where each participant would land on it.

Where `circle.synthesis` produces a discussion synthesis (themes, divergences,
outliers — what the group said), `circle.proposal` produces a draft the group
can react to and vote on (what the rule should actually be), plus per-
participant vote signals inferred from the transcripts. See PRD section
follow-up notes — this implements the "proposal mode" called for by the call
feedback after the bylaws pilot.

Reuses the loading and filtering pipeline from `circle.synthesis`:
- `filter_for_synthesis` for per-participant filtering and permission tagging
- `assemble_transcripts_block` for prompt assembly with strictest-permission
  defaults
- `collect_completed` for loading every completed participant from disk

Usage:
    python -m circle.proposal --config config/session_config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from .anthropic_client import (
    PROPOSAL_MAX_TOKENS,
    PROPOSAL_TEMPERATURE,
    AnthropicClient,
    ChatMessage,
)
from .config import AppConfig, ConfigError, load_app_config
from .prompts import render_proposal_prompt
from .session import Session, load_session
from .synthesis import assemble_transcripts_block, collect_completed
from .workflows import get_community_context, get_synthesis_question

logger = logging.getLogger(__name__)


async def run_proposal(session: Session, app_config: AppConfig) -> Path:
    data_dir = app_config.data_dir_for(session.id)
    participants = collect_completed(data_dir)
    if not participants:
        raise RuntimeError(
            "No completed participants with shareable content found in "
            f"{data_dir}"
        )
    if len(participants) < 2:
        logger.warning(
            "only %s participant(s) have completed; proposal will be thin",
            len(participants),
        )

    transcripts_block = assemble_transcripts_block(participants)
    from .workflow_overrides import get_output_template

    template = get_output_template(
        session.workflow_type, app_config.workflows_dir
    )
    prompt = render_proposal_prompt(
        question=get_synthesis_question(session),
        transcripts=transcripts_block,
        community_context=get_community_context(session, app_config.contexts_dir),
        template=template,
    )

    anthropic = AnthropicClient(
        api_key=app_config.secrets.anthropic_api_key,
        default_model=session.common.synthesis_model,
    )

    logger.info("calling proposal model=%s", session.common.synthesis_model)
    output = await anthropic.complete(
        system=prompt,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "Please produce the proposal draft, rationale, vote "
                    "signals, outstanding tensions, and alternatives now."
                ),
            )
        ],
        model=session.common.synthesis_model,
        temperature=PROPOSAL_TEMPERATURE,
        max_tokens=PROPOSAL_MAX_TOKENS,
    )

    today = datetime.now().strftime("%Y%m%d")
    out_path = app_config.proposals_dir / f"proposal_{session.id}_{today}.md"
    # Same anti-clobber pattern as synthesis: append a counter on re-runs.
    counter = 1
    while out_path.exists():
        out_path = (
            app_config.proposals_dir
            / f"proposal_{session.id}_{today}_{counter}.md"
        )
        counter += 1

    header = (
        f"# Proposal Draft for {session.id}\n\n"
        f"**Title:** {session.title}\n\n"
        f"**Drafted from input by:** "
        f"{', '.join(p.name for p in participants)}\n\n"
        "**Note:** This is an AI-generated draft based on the participant "
        "transcripts. Vote signals are inferences, not actual votes — they "
        "indicate where each participant would *likely* land based on what "
        "they said in discovery, but the group should treat the draft as a "
        "starting point to react to, not as a binding consensus.\n\n"
        "---\n\n"
    )
    out_path.write_text(header + output + "\n", encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a draft proposal + predicted vote signals from "
            "completed transcripts. Run this AFTER discovery."
        )
    )
    parser.add_argument(
        "--session",
        required=True,
        help="Session id to draft a proposal for.",
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
        out_path = asyncio.run(run_proposal(session, app_config))
    except Exception as exc:
        print(f"proposal generation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"proposal written to: {out_path}")


if __name__ == "__main__":
    main()
