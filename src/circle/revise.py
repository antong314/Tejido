"""Revise mode — produce version 2 of an existing document from feedback.

The third post-processor, paired with the `document_revision` workflow.
Where synthesis describes ("what we said") and proposal prescribes
("what we should decide"), revise produces a curator-led draft of the
next version of the document, with explicit notes on what changed,
what was kept despite feedback, and what's been left open for the group.

Reuses the same loading + filtering pipeline as synthesis and proposal:

- `circle.synthesis.filter_for_synthesis` — drops private content,
  permission-tags ambiguous quotes
- `circle.synthesis.assemble_transcripts_block` — formats the prompt
  input with strictest-permission defaults
- `circle.synthesis.collect_completed` — loads completed participants

Usage:
    python -m circle.revise --session bylaws_v2
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
from .prompts import render_revise_prompt
from .session import Session, load_session
from .synthesis import assemble_transcripts_block, collect_completed
from .workflows import get_community_context, get_workflow

logger = logging.getLogger(__name__)


async def run_revise(session: Session, app_config: AppConfig) -> Path:
    if session.workflow_type != "document_revision":
        raise ValueError(
            f"Session {session.id!r} has workflow_type "
            f"{session.workflow_type!r}; revise mode only applies to "
            f"document_revision sessions."
        )

    document = str(session.workflow_data.get("reference_document", "")).strip()
    if not document:
        raise ValueError(
            "Session workflow_data has no reference_document to revise."
        )

    data_dir = app_config.data_dir_for(session.id)
    participants = collect_completed(data_dir)
    if not participants:
        raise RuntimeError(
            "No completed participants with shareable content found in "
            f"{data_dir}"
        )
    if len(participants) < 2:
        logger.warning(
            "only %s participant(s) have completed; revision will be thin",
            len(participants),
        )

    transcripts_block = assemble_transcripts_block(participants)
    prompt = render_revise_prompt(
        original_document=document,
        transcripts=transcripts_block,
        community_context=get_community_context(session),
    )

    anthropic = AnthropicClient(
        api_key=app_config.secrets.anthropic_api_key,
        default_model=session.common.synthesis_model,
    )

    logger.info("calling revise model=%s", session.common.synthesis_model)
    output = await anthropic.complete(
        system=prompt,
        messages=[
            ChatMessage(
                role="user",
                content=(
                    "Please produce the revised document draft, with the "
                    "change-notes and unresolved-tensions sections."
                ),
            )
        ],
        model=session.common.synthesis_model,
        temperature=PROPOSAL_TEMPERATURE,
        max_tokens=PROPOSAL_MAX_TOKENS,
    )

    today = datetime.now().strftime("%Y%m%d")
    out_path = app_config.revisions_dir / f"revision_{session.id}_{today}.md"
    counter = 1
    while out_path.exists():
        out_path = (
            app_config.revisions_dir
            / f"revision_{session.id}_{today}_{counter}.md"
        )
        counter += 1

    header = (
        f"# Document revision draft — {session.id}\n\n"
        f"**Title:** {session.title}\n\n"
        f"**Drafted from input by:** "
        f"{', '.join(p.name for p in participants)}\n\n"
        "**Note:** This is an AI-generated draft. The curator-led merge "
        "took a position on every change; the 'What I left for you' "
        "section flags real tensions the group should resolve before "
        "ratifying the new version.\n\n"
        "---\n\n"
    )
    out_path.write_text(header + output + "\n", encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a curator-led version 2 of a document from completed "
            "feedback. Requires a session with workflow_type=document_revision."
        )
    )
    parser.add_argument("--session", required=True, help="Session id to revise.")
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
        out_path = asyncio.run(run_revise(session, app_config))
    except Exception as exc:
        print(f"revise generation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"revision written to: {out_path}")


if __name__ == "__main__":
    main()
