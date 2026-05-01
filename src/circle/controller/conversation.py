"""Conversation phase — text + voice messages during in_conversation.

Implements PRD section 4.4 message handling. On each user message:
  1. Append to transcript with timestamp + via.
  2. Persist to disk before calling Anthropic (so a crash doesn't lose words).
  3. Call Anthropic with the facilitator system prompt + history.
  4. Detect the [READY_FOR_PERMISSIONS] token; strip it before replying.
  5. Save the assistant turn, then transition to permissions if signaled.

Also routes incoming text/voice when the participant is in
awaiting_addition: that input is the addition itself, handed to the
permissions controller for the per-addition permission walk-through.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Literal

from ..anthropic_client import (
    FACILITATOR_MAX_TOKENS,
    FACILITATOR_TEMPERATURE,
    ChatMessage,
)
from ..prompts import READY_TOKEN, render_facilitator_prompt
from ..runtime import BotContext
from ..state import Phase, TranscriptTurn
from ..transport import OutboundAction, SendText, TypingIndicator
from . import permissions as permissions_controller

logger = logging.getLogger(__name__)


WRONG_PHASE_MESSAGE = (
    "We're in the {phase} phase right now — let's finish that before continuing."
)

API_FAILURE_MESSAGE = (
    "I'm having a technical issue on my end. The facilitator can help — please "
    "let them know, and we'll pick this back up."
)

NOT_STARTED_NUDGE = "Send /start when you're ready to begin."
AWAITING_CONSENT_NUDGE = "Tap the button above when you're ready, and we'll begin."

PAUSE_FALLBACK_MESSAGE = "Let's pause here for a moment."

# PRD section 4.4 step 7: "transition to permissions phase after a short delay"
READY_TRANSITION_DELAY_SECONDS = 2.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_ready_token(text: str) -> tuple[str, bool]:
    if READY_TOKEN not in text:
        return text, False
    cleaned_lines = [line for line in text.splitlines() if line.strip() != READY_TOKEN]
    return "\n".join(cleaned_lines).strip(), True


async def handle_message(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
    text: str,
    via: Literal["text", "voice"] = "text",
    detected_language: str | None = None,
) -> AsyncIterator[OutboundAction]:
    """Route a text-or-voice message based on the participant's current phase."""
    # Peek at phase to decide route.
    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        current_phase = state.phase

    if current_phase == Phase.NOT_STARTED:
        yield SendText(NOT_STARTED_NUDGE)
        return
    if current_phase == Phase.AWAITING_CONSENT:
        yield SendText(AWAITING_CONSENT_NUDGE)
        return
    if current_phase == Phase.AWAITING_ADDITION:
        async for action in permissions_controller.handle_addition_text(
            participant_id=participant_id,
            display_name=display_name,
            session=session,
            text=text,
        ):
            yield action
        return
    if current_phase != Phase.IN_CONVERSATION:
        # Permissions / in_addition_permissions / complete are handled by
        # their own callback handlers; a stray text message here gets a polite nudge.
        phase_label = current_phase.value.replace("_", " ")
        yield SendText(WRONG_PHASE_MESSAGE.format(phase=phase_label))
        return

    yield TypingIndicator()

    reply_text: str | None = None
    ready = False
    failed = False
    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        if state.phase != Phase.IN_CONVERSATION:
            # Phase changed between peek and lock acquisition; bail.
            return

        state.transcript.append(
            TranscriptTurn(
                role="user",
                content=text,
                timestamp=_now_iso(),
                via=via,
                detected_language=detected_language,
            )
        )
        session.save(state)

        history = [
            ChatMessage(role=turn.role, content=turn.content) for turn in state.transcript
        ]
        try:
            reply = await session.anthropic.complete(
                system=render_facilitator_prompt(
                    question=session.config.session.question,
                    context=session.config.session.context,
                ),
                messages=history,
                model=session.config.session.facilitator_model,
                temperature=FACILITATOR_TEMPERATURE,
                max_tokens=FACILITATOR_MAX_TOKENS,
            )
        except Exception:
            logger.exception("facilitator completion failed")
            failed = True
        else:
            cleaned, ready = _strip_ready_token(reply)
            if not cleaned:
                cleaned = PAUSE_FALLBACK_MESSAGE
            state.transcript.append(
                TranscriptTurn(role="assistant", content=cleaned, timestamp=_now_iso())
            )
            session.save(state)
            reply_text = cleaned

    if failed:
        yield SendText(API_FAILURE_MESSAGE)
        return

    assert reply_text is not None
    yield SendText(reply_text)

    if ready:
        await asyncio.sleep(READY_TRANSITION_DELAY_SECONDS)
        async for action in permissions_controller.begin_permissions_phase(
            participant_id=participant_id,
            display_name=display_name,
            session=session,
        ):
            yield action
