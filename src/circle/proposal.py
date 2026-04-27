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
from .synthesis import assemble_transcripts_block, collect_completed

logger = logging.getLogger(__name__)


async def run_proposal(app_config: AppConfig) -> Path:
    participants = collect_completed(app_config)
    if not participants:
        raise RuntimeError(
            "No completed participants with shareable content found in "
            f"{app_config.data_dir}"
        )
    if len(participants) < 2:
        logger.warning(
            "only %s participant(s) have completed; proposal will be thin",
            len(participants),
        )

    transcripts_block = assemble_transcripts_block(participants)
    prompt = render_proposal_prompt(
        question=app_config.session.question,
        transcripts=transcripts_block,
        community_context=app_config.session.community_context,
    )

    anthropic = AnthropicClient(
        api_key=app_config.secrets.anthropic_api_key,
        default_model=app_config.session.synthesis_model,
    )

    logger.info("calling proposal model=%s", app_config.session.synthesis_model)
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
        model=app_config.session.synthesis_model,
        temperature=PROPOSAL_TEMPERATURE,
        max_tokens=PROPOSAL_MAX_TOKENS,
    )

    today = datetime.now().strftime("%Y%m%d")
    out_path = app_config.proposals_dir / f"proposal_{today}.md"
    # Same anti-clobber pattern as synthesis: append a counter on re-runs.
    counter = 1
    while out_path.exists():
        out_path = (
            app_config.proposals_dir / f"proposal_{today}_{counter}.md"
        )
        counter += 1

    header = (
        f"# Proposal Draft for {app_config.session.session_id}\n\n"
        f"**Question:** {app_config.session.question}\n\n"
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
            "completed transcripts. Run this AFTER discovery (i.e. after "
            "running circle.synthesis or at least after enough participants "
            "have reached `complete`)."
        )
    )
    parser.add_argument(
        "--config",
        default="config/session_config.yaml",
        help="Path to the session config YAML.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        app_config = load_app_config(args.config, require_ffmpeg=False)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        out_path = asyncio.run(run_proposal(app_config))
    except Exception as exc:
        print(f"proposal generation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"proposal written to: {out_path}")


if __name__ == "__main__":
    main()
