"""Consent + opening turn — handles /start and the awaiting_consent → in_conversation transition.

PRD section 4.3 specifies the awaiting_consent phase: after /start the bot
sends a welcome message explaining what's about to happen and waits for the
participant to confirm they're ready before any AI conversation begins.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from ..anthropic_client import (
    FACILITATOR_MAX_TOKENS,
    FACILITATOR_TEMPERATURE,
    ChatMessage,
)
from ..prompts import READY_TOKEN, render_facilitator_prompt
from ..runtime import BotContext
from ..state import Phase, TranscriptTurn
from ..transport import (
    Choice,
    OutboundAction,
    ResolveChoice,
    SendChoicePrompt,
    SendText,
    TypingIndicator,
)

logger = logging.getLogger(__name__)


CONSENT_CALLBACK_DATA = "consent:ready"


WELCOME_TEMPLATE = (
    "Welcome, {name}.\n\n"
    "We're going to spend the next 10 minutes or so thinking together about a "
    "question your group is exploring. This is a private conversation — only "
    "you will see what we say here, and nothing leaves this chat without your "
    "explicit permission at the end.\n\n"
    "The question is:\n\n"
    "<b>{question}</b>\n\n"
    "You can type, or send voice messages — whichever feels easier. There's no "
    "right answer and nothing to prepare. When you're ready, tap below and "
    "we'll begin."
)


READY_BUTTON_LABEL = "I'm ready, let's begin"


# Surfaced for the adapter to send directly when an unknown user runs /start.
NOT_REGISTERED_MESSAGE = (
    "Hi — this bot is set up for a specific group session, and your Telegram "
    "handle isn't on the participant list. If you think that's a mistake, "
    "please reach out to the facilitator."
)


ALREADY_BEGUN_MESSAGE = (
    "You've already begun. Just keep going — send me a message and we'll pick "
    "up where we left off.\n\n"
    "If you'd like to start over from scratch (this will erase everything you "
    "said so far), type /restart."
)


API_FAILURE_MESSAGE = (
    "I'm having a technical issue on my end. The facilitator can help — please "
    "let them know, and we'll pick this back up."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_ready_token(text: str) -> tuple[str, bool]:
    if READY_TOKEN not in text:
        return text, False
    cleaned_lines = [line for line in text.splitlines() if line.strip() != READY_TOKEN]
    return "\n".join(cleaned_lines).strip(), True


async def handle_start(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
) -> AsyncIterator[OutboundAction]:
    """Handle /start for a registered participant.

    The adapter is responsible for checking registration first; unknown
    users should be sent NOT_REGISTERED_MESSAGE without invoking this.
    """
    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        already_begun = state.phase != Phase.NOT_STARTED
        if not already_begun:
            state.transition_to(Phase.AWAITING_CONSENT)
            session.save(state)
        question = session.config.session.question
        name = state.participant_name

    if already_begun:
        # PRD section 4.8: /start twice → gentle acknowledgement.
        yield SendText(ALREADY_BEGUN_MESSAGE)
        return

    yield SendChoicePrompt(
        text=WELCOME_TEMPLATE.format(name=name, question=question),
        parse_mode="html",
        choices=(
            Choice(label=READY_BUTTON_LABEL, callback_data=CONSENT_CALLBACK_DATA),
        ),
    )


async def handle_consent_callback(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
) -> AsyncIterator[OutboundAction]:
    """Handle the 'I'm ready' button tap.

    Transitions to in_conversation and produces the opening turn from the
    facilitator AI. If the user is already past consent, just clears the
    button (idempotent re-tap).
    """
    transitioned = False
    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        if state.phase == Phase.AWAITING_CONSENT:
            state.transition_to(Phase.IN_CONVERSATION)
            session.save(state)
            transitioned = True

    yield ResolveChoice()

    if not transitioned:
        return

    async for action in send_opening_turn(
        participant_id=participant_id, display_name=display_name, session=session
    ):
        yield action


async def send_opening_turn(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
) -> AsyncIterator[OutboundAction]:
    """Generate and send the very first facilitator message.

    Drives the model with an empty user history, seeded with a synthetic
    nudge — the Anthropic Messages API requires the first message to be
    from the user. The system prompt instructs the model to open with a
    gut-reaction question.
    """
    yield TypingIndicator()

    opening: str | None = None
    failed = False
    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        if state.phase != Phase.IN_CONVERSATION:
            return

        seed = ChatMessage(role="user", content="(I'm ready to begin.)")
        try:
            reply = await session.anthropic.complete(
                system=render_facilitator_prompt(
                    question=session.config.session.question,
                    context=session.config.session.context,
                ),
                messages=[seed],
                model=session.config.session.facilitator_model,
                temperature=FACILITATOR_TEMPERATURE,
                max_tokens=FACILITATOR_MAX_TOKENS,
            )
        except Exception:
            logger.exception("opening turn failed")
            failed = True
        else:
            cleaned, _ = _strip_ready_token(reply)
            state.transcript.append(
                TranscriptTurn(role="assistant", content=cleaned, timestamp=_now_iso())
            )
            session.save(state)
            opening = cleaned

    if failed:
        yield SendText(API_FAILURE_MESSAGE)
    elif opening is not None:
        yield SendText(opening)
