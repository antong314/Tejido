"""Permissions phase — extract 3-5 points and walk through with inline buttons.

Implements PRD section 3.2 (extraction prompt + UI flow), section 4.4 button
handling, and section 4.8 /permissions re-edit. Per-point UI is one message
with three inline buttons (By name / Anonymous / Private). On callback, the
buttons are removed and the choice is appended to the message text. Flow
ends with the "anything to add?" addition prompt.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Literal

from ..anthropic_client import (
    EXTRACTION_MAX_TOKENS,
    EXTRACTION_TEMPERATURE,
    ChatMessage,
)
from ..prompts import render_extraction_prompt
from ..runtime import BotContext
from ..state import (
    Addition,
    ExtractedPoint,
    ParticipantState,
    PermissionChoice,
    Phase,
)
from ..transport import (
    Choice,
    OutboundAction,
    ResolveChoice,
    SendChoicePrompt,
    SendText,
)

logger = logging.getLogger(__name__)


PERMISSION_CALLBACK_PREFIX = "perm:"
ADDITION_CALLBACK_PREFIX = "add:"
ADDITION_PERM_CALLBACK_PREFIX = "addperm:"


PERMISSIONS_INTRO = (
    "Thanks for that conversation. Before we wrap up, I want to check with you "
    "about what gets shared with the group. I'll walk through {n} things you "
    "said, and for each one, you can choose how it gets shared — by name, "
    "anonymously, or not at all."
)

ADDITION_PROMPT = (
    "Is there anything else you'd like to add that didn't come up? Anything "
    "the group should hear?"
)

ADDITION_GO_AHEAD_MESSAGE = (
    "Go ahead — type or send a voice message with what you'd like to add."
)

CLOSING_MESSAGE = (
    "That's it. Thank you. We'll come back together in the circle when "
    "everyone has finished."
)

EXTRACTION_FAILED_MESSAGE = (
    "I had trouble pulling out the main points from our conversation. The "
    "facilitator can help — please flag it."
)


CHOICE_LABELS: dict[PermissionChoice, str] = {
    "attributed": "By name",
    "anonymous": "Anonymous",
    "private": "Private",
}

CHOICE_GLYPHS: dict[PermissionChoice, str] = {
    "attributed": "✓ By name",
    "anonymous": "✓ Anonymous",
    "private": "✓ Private",
}


def _format_transcript_for_extraction(state: ParticipantState) -> str:
    lines: list[str] = []
    for turn in state.transcript:
        speaker = "Participant" if turn.role == "user" else "Facilitator"
        lines.append(f"{speaker}: {turn.content}")
    return "\n\n".join(lines)


def _parse_points_json(raw: str) -> list[str]:
    """Pull a JSON array of strings from the model's response.

    The prompt asks for "ONLY the JSON array, no other text", but defensively
    extract the outermost [...] block (greedy) and reject anything that isn't
    a list of strings.
    """
    candidate = raw.strip()
    start = candidate.find("[")
    end = candidate.rfind("]")
    if 0 <= start < end:
        candidate = candidate[start : end + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, list):
        raise ValueError("extraction did not return a JSON array")
    points = [str(item).strip() for item in parsed if str(item).strip()]
    if not 1 <= len(points) <= 8:
        # PRD says 3-5; accept slightly outside for prototype robustness, fail outside 1-8.
        raise ValueError(f"unexpected point count: {len(points)}")
    return points


def _point_choices(point_index: int) -> tuple[Choice, ...]:
    return (
        Choice(
            label=CHOICE_LABELS["attributed"],
            callback_data=f"{PERMISSION_CALLBACK_PREFIX}{point_index}:attributed",
        ),
        Choice(
            label=CHOICE_LABELS["anonymous"],
            callback_data=f"{PERMISSION_CALLBACK_PREFIX}{point_index}:anonymous",
        ),
        Choice(
            label=CHOICE_LABELS["private"],
            callback_data=f"{PERMISSION_CALLBACK_PREFIX}{point_index}:private",
        ),
    )


def _addition_perm_choices() -> tuple[Choice, ...]:
    return (
        Choice(
            label=CHOICE_LABELS["attributed"],
            callback_data=f"{ADDITION_PERM_CALLBACK_PREFIX}attributed",
        ),
        Choice(
            label=CHOICE_LABELS["anonymous"],
            callback_data=f"{ADDITION_PERM_CALLBACK_PREFIX}anonymous",
        ),
        Choice(
            label=CHOICE_LABELS["private"],
            callback_data=f"{ADDITION_PERM_CALLBACK_PREFIX}private",
        ),
    )


def _format_point_message(index: int, total: int, point: str) -> str:
    return f"<b>{index + 1} of {total}</b>\n\n{point}"


async def begin_permissions_phase(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
) -> AsyncIterator[OutboundAction]:
    """Extract points (if not already done) and send the first prompt.

    Called from three places:
      * the conversation flow when the facilitator emits [READY_FOR_PERMISSIONS]
      * the /done command after the early-done confirmation
      * the /permissions command (re-edit path)
    """
    intro_text: str | None = None
    failed_extraction = False
    next_idx = 0
    total = 0
    point_text = ""

    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)

        if state.phase == Phase.IN_CONVERSATION:
            try:
                state.transition_to(Phase.IN_PERMISSIONS)
            except Exception:
                logger.exception("could not enter permissions phase")
                return

        if state.phase != Phase.IN_PERMISSIONS:
            return

        if not state.extracted_points:
            transcript_text = _format_transcript_for_extraction(state)
            try:
                raw = await session.anthropic.complete(
                    system="You extract concise main points from conversation transcripts.",
                    messages=[
                        ChatMessage(
                            role="user",
                            content=render_extraction_prompt(transcript_text),
                        )
                    ],
                    model=session.config.session.facilitator_model,
                    temperature=EXTRACTION_TEMPERATURE,
                    max_tokens=EXTRACTION_MAX_TOKENS,
                )
                points = _parse_points_json(raw)
            except Exception:
                logger.exception("point extraction failed")
                failed_extraction = True
            else:
                state.extracted_points = [
                    ExtractedPoint(point=text, permission=None, index=i)
                    for i, text in enumerate(points)
                ]

        if not failed_extraction:
            state.current_point_index = 0
            session.save(state)
            total = len(state.extracted_points)
            next_idx = state.current_point_index
            point_text = _format_point_message(
                next_idx, total, state.extracted_points[next_idx].point
            )
            intro_text = PERMISSIONS_INTRO.format(n=total)

    if failed_extraction:
        yield SendText(EXTRACTION_FAILED_MESSAGE)
        return

    if intro_text is None or total == 0:
        return

    yield SendText(intro_text)
    yield SendChoicePrompt(
        text=point_text,
        parse_mode="html",
        choices=_point_choices(next_idx),
    )


async def handle_permission_choice(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
    point_index: int,
    choice: PermissionChoice,
) -> AsyncIterator[OutboundAction]:
    """Handle a By-name / Anonymous / Private button tap on a point prompt."""
    updated_text: str | None = None
    next_idx = -1
    total = 0
    done_with_points = False

    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        if not (0 <= point_index < len(state.extracted_points)):
            return
        state.extracted_points[point_index].permission = choice
        # Advance past any consecutive already-answered points (handles the
        # /permissions re-edit case where some points were already chosen).
        if point_index == state.current_point_index:
            state.current_point_index += 1
            while (
                state.current_point_index < len(state.extracted_points)
                and state.extracted_points[state.current_point_index].permission
                is not None
            ):
                state.current_point_index += 1
        session.save(state)

        total = len(state.extracted_points)
        updated_text = (
            f"<b>{point_index + 1} of {total}</b>\n\n"
            f"{state.extracted_points[point_index].point}\n\n"
            f"<i>{CHOICE_GLYPHS[choice]}</i>"
        )
        next_idx = state.current_point_index
        done_with_points = next_idx >= total

    yield ResolveChoice(text=updated_text, parse_mode="html")

    if done_with_points:
        async for action in _ask_addition(
            participant_id=participant_id,
            display_name=display_name,
            session=session,
        ):
            yield action
    else:
        async for action in _send_next_point_prompt(
            participant_id=participant_id,
            display_name=display_name,
            session=session,
        ):
            yield action


async def _send_next_point_prompt(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
) -> AsyncIterator[OutboundAction]:
    next_idx = -1
    total = 0
    text = ""

    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        idx = state.current_point_index
        total = len(state.extracted_points)
        if idx >= total:
            return
        next_idx = idx
        text = _format_point_message(idx, total, state.extracted_points[idx].point)

    yield SendChoicePrompt(
        text=text,
        parse_mode="html",
        choices=_point_choices(next_idx),
    )


async def _ask_addition(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
) -> AsyncIterator[OutboundAction]:
    transitioned = False
    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        try:
            state.transition_to(Phase.AWAITING_ADDITION)
            session.save(state)
            transitioned = True
        except Exception:
            logger.exception("could not transition to awaiting_addition")

    if not transitioned:
        return

    yield SendChoicePrompt(
        text=ADDITION_PROMPT,
        choices=(
            Choice(
                label="Yes, I want to add something",
                callback_data=f"{ADDITION_CALLBACK_PREFIX}yes",
            ),
            Choice(
                label="No, I'm done",
                callback_data=f"{ADDITION_CALLBACK_PREFIX}no",
            ),
        ),
    )


async def handle_addition_choice(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
    choice: Literal["yes", "no"],
) -> AsyncIterator[OutboundAction]:
    """Handle the yes/no button on the 'anything to add?' prompt."""
    yield ResolveChoice()

    if choice == "no":
        async for action in _finish(
            participant_id=participant_id,
            display_name=display_name,
            session=session,
        ):
            yield action
        return

    yield SendText(ADDITION_GO_AHEAD_MESSAGE)
    # The participant's next text/voice message will be routed to
    # handle_addition_text via the conversation controller's phase check.


async def handle_addition_text(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
    text: str,
) -> AsyncIterator[OutboundAction]:
    """Receive the participant's addition text and ask for its permission."""
    transitioned = False
    addition_content = ""

    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        if state.phase != Phase.AWAITING_ADDITION:
            return
        state.additions.append(Addition(content=text, permission=None))
        try:
            state.transition_to(Phase.IN_ADDITION_PERMISSIONS)
        except Exception:
            logger.exception("could not transition addition")
            return
        session.save(state)
        transitioned = True
        addition_content = state.additions[-1].content

    if not transitioned:
        return

    yield SendChoicePrompt(
        text=(
            f"<b>Your addition</b>\n\n{addition_content}\n\n"
            f"How should this be shared with the group?"
        ),
        parse_mode="html",
        choices=_addition_perm_choices(),
    )


async def handle_addition_permission(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
    choice: PermissionChoice,
) -> AsyncIterator[OutboundAction]:
    """Handle the permission button tap on the addition's permission prompt."""
    updated_text: str | None = None
    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        if not state.additions:
            return
        state.additions[-1].permission = choice
        session.save(state)
        updated_text = (
            f"<b>Your addition</b>\n\n"
            f"{state.additions[-1].content}\n\n"
            f"<i>{CHOICE_GLYPHS[choice]}</i>"
        )

    yield ResolveChoice(text=updated_text, parse_mode="html")
    async for action in _finish(
        participant_id=participant_id,
        display_name=display_name,
        session=session,
    ):
        yield action


async def _finish(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
) -> AsyncIterator[OutboundAction]:
    finalized = False
    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        # Allow either awaiting_addition -> complete or in_addition_permissions -> complete.
        if state.phase in (Phase.AWAITING_ADDITION, Phase.IN_ADDITION_PERMISSIONS):
            try:
                state.transition_to(Phase.COMPLETE)
                session.save(state)
                finalized = True
            except Exception:
                logger.exception("could not finalize participant")
                return
        elif state.phase == Phase.COMPLETE:
            finalized = True

    if finalized:
        yield SendText(CLOSING_MESSAGE)
