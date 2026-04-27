"""Permissions phase: extract 3-5 points, walk through with inline buttons.

Implements PRD section 3.2 (extraction prompt + UI flow), section 4.4 button
handling, and section 4.8 /permissions re-edit. Per-point UI is one message
with three inline buttons (By name / Anonymous / Private). On callback, the
buttons are removed and the choice is appended to the message text. The flow
ends with the "anything to add?" addition prompt.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from telegram import (
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import CallbackQueryHandler, ContextTypes

from ..anthropic_client import (
    EXTRACTION_MAX_TOKENS,
    EXTRACTION_TEMPERATURE,
    ChatMessage,
)
from ..prompts import render_extraction_prompt
from ..state import (
    Addition,
    ExtractedPoint,
    ParticipantState,
    PermissionChoice,
    Phase,
)

if TYPE_CHECKING:
    from ..runtime import BotContext

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _build_point_keyboard(point_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    CHOICE_LABELS["attributed"],
                    callback_data=f"{PERMISSION_CALLBACK_PREFIX}{point_index}:attributed",
                ),
                InlineKeyboardButton(
                    CHOICE_LABELS["anonymous"],
                    callback_data=f"{PERMISSION_CALLBACK_PREFIX}{point_index}:anonymous",
                ),
                InlineKeyboardButton(
                    CHOICE_LABELS["private"],
                    callback_data=f"{PERMISSION_CALLBACK_PREFIX}{point_index}:private",
                ),
            ]
        ]
    )


def _format_point_message(index: int, total: int, point: str) -> str:
    return f"<b>{index + 1} of {total}</b>\n\n{point}"


async def begin_permissions_phase(
    *,
    chat: Chat,
    user_id: int,
    username: str | None,
    context: "BotContext",
) -> None:
    """Extract points and send the first one. Called by conversation handler."""
    async with context.lock_for(user_id):
        state = context.load_or_create(
            telegram_user_id=user_id,
            telegram_username=username,
            fallback_name="friend",
        )

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
                raw = await context.anthropic.complete(
                    system="You extract concise main points from conversation transcripts.",
                    messages=[
                        ChatMessage(role="user", content=render_extraction_prompt(transcript_text))
                    ],
                    model=context.config.session.facilitator_model,
                    temperature=EXTRACTION_TEMPERATURE,
                    max_tokens=EXTRACTION_MAX_TOKENS,
                )
                points = _parse_points_json(raw)
            except Exception:
                logger.exception("point extraction failed")
                await chat.send_message(EXTRACTION_FAILED_MESSAGE)
                return

            state.extracted_points = [
                ExtractedPoint(point=text, permission=None, index=i)
                for i, text in enumerate(points)
            ]

        state.current_point_index = 0
        context.save(state)
        total = len(state.extracted_points)

    await chat.send_message(PERMISSIONS_INTRO.format(n=total))
    await _send_next_point(chat=chat, user_id=user_id, username=username, context=context)


async def _send_next_point(
    *,
    chat: Chat,
    user_id: int,
    username: str | None,
    context: "BotContext",
) -> None:
    async with context.lock_for(user_id):
        state = context.load_or_create(
            telegram_user_id=user_id,
            telegram_username=username,
            fallback_name="friend",
        )
        idx = state.current_point_index
        total = len(state.extracted_points)
        if idx >= total:
            return  # caller transitioned us forward already
        point = state.extracted_points[idx]
        text = _format_point_message(idx, total, point.point)

    await chat.send_message(
        text,
        parse_mode="HTML",
        reply_markup=_build_point_keyboard(idx),
    )


async def _ask_addition(
    *,
    chat: Chat,
    user_id: int,
    username: str | None,
    context: "BotContext",
) -> None:
    async with context.lock_for(user_id):
        state = context.load_or_create(
            telegram_user_id=user_id,
            telegram_username=username,
            fallback_name="friend",
        )
        try:
            state.transition_to(Phase.AWAITING_ADDITION)
        except Exception:
            logger.exception("could not transition to awaiting_addition")
            return
        context.save(state)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Yes, I want to add something",
                    callback_data=f"{ADDITION_CALLBACK_PREFIX}yes",
                ),
                InlineKeyboardButton(
                    "No, I'm done",
                    callback_data=f"{ADDITION_CALLBACK_PREFIX}no",
                ),
            ]
        ]
    )
    await chat.send_message(ADDITION_PROMPT, reply_markup=keyboard)


async def _finish(
    *,
    chat: Chat,
    user_id: int,
    username: str | None,
    context: "BotContext",
) -> None:
    async with context.lock_for(user_id):
        state = context.load_or_create(
            telegram_user_id=user_id,
            telegram_username=username,
            fallback_name="friend",
        )
        # Allow either awaiting_addition -> complete or in_addition_permissions -> complete.
        if state.phase in (Phase.AWAITING_ADDITION, Phase.IN_ADDITION_PERMISSIONS):
            try:
                state.transition_to(Phase.COMPLETE)
            except Exception:
                logger.exception("could not finalize participant")
                return
        elif state.phase != Phase.COMPLETE:
            return
        context.save(state)

    await chat.send_message(CLOSING_MESSAGE)


def build_handlers(context: "BotContext") -> list:
    async def on_permission_choice(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.from_user is None or query.message is None:
            return
        await query.answer()
        chat = query.message.chat
        user_id = query.from_user.id
        username = query.from_user.username

        try:
            _, payload = (query.data or "").split(":", 1)
            idx_str, choice_str = payload.split(":", 1)
            point_index = int(idx_str)
            if choice_str not in CHOICE_LABELS:
                raise ValueError(f"unknown choice {choice_str}")
            choice: PermissionChoice = choice_str  # type: ignore[assignment]
        except Exception:
            logger.warning("bad permission callback data: %r", query.data)
            return

        async with context.lock_for(user_id):
            state = context.load_or_create(
                telegram_user_id=user_id,
                telegram_username=username,
                fallback_name="friend",
            )
            if not (0 <= point_index < len(state.extracted_points)):
                return
            state.extracted_points[point_index].permission = choice
            # Advance past any consecutive already-answered points (handles the
            # /permissions re-edit case where some points were already chosen).
            if point_index == state.current_point_index:
                state.current_point_index += 1
                while (
                    state.current_point_index < len(state.extracted_points)
                    and state.extracted_points[state.current_point_index].permission is not None
                ):
                    state.current_point_index += 1
            context.save(state)
            updated_text = (
                f"<b>{point_index + 1} of {len(state.extracted_points)}</b>\n\n"
                f"{state.extracted_points[point_index].point}\n\n"
                f"<i>{CHOICE_GLYPHS[choice]}</i>"
            )
            done_with_points = state.current_point_index >= len(state.extracted_points)

        try:
            await query.edit_message_text(updated_text, parse_mode="HTML")
        except Exception:
            logger.debug("failed to edit point message", exc_info=True)

        if done_with_points:
            await _ask_addition(
                chat=chat, user_id=user_id, username=username, context=context
            )
        else:
            await _send_next_point(
                chat=chat, user_id=user_id, username=username, context=context
            )

    async def on_addition_choice(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.from_user is None or query.message is None:
            return
        await query.answer()
        chat = query.message.chat
        user_id = query.from_user.id
        username = query.from_user.username

        choice = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            logger.debug("failed to clear addition markup", exc_info=True)

        if choice == "no":
            await _finish(chat=chat, user_id=user_id, username=username, context=context)
            return

        await chat.send_message(
            "Go ahead — type or send a voice message with what you'd like to add."
        )
        # Mark that we're expecting an addition next; the text/voice handlers
        # will route it here via the `awaiting_addition` phase check.

    async def on_addition_permission(
        update: Update, _ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if query is None or query.from_user is None or query.message is None:
            return
        await query.answer()
        chat = query.message.chat
        user_id = query.from_user.id
        username = query.from_user.username

        try:
            choice_str = (query.data or "").split(":", 1)[1]
            if choice_str not in CHOICE_LABELS:
                raise ValueError(f"unknown choice {choice_str}")
            choice: PermissionChoice = choice_str  # type: ignore[assignment]
        except Exception:
            logger.warning("bad addition perm callback: %r", query.data)
            return

        async with context.lock_for(user_id):
            state = context.load_or_create(
                telegram_user_id=user_id,
                telegram_username=username,
                fallback_name="friend",
            )
            if not state.additions:
                return
            state.additions[-1].permission = choice
            updated_text = (
                f"<b>Your addition</b>\n\n"
                f"{state.additions[-1].content}\n\n"
                f"<i>{CHOICE_GLYPHS[choice]}</i>"
            )
            context.save(state)

        try:
            await query.edit_message_text(updated_text, parse_mode="HTML")
        except Exception:
            logger.debug("failed to edit addition message", exc_info=True)

        await _finish(chat=chat, user_id=user_id, username=username, context=context)

    return [
        CallbackQueryHandler(on_permission_choice, pattern=f"^{PERMISSION_CALLBACK_PREFIX}"),
        CallbackQueryHandler(on_addition_choice, pattern=f"^{ADDITION_CALLBACK_PREFIX}"),
        CallbackQueryHandler(
            on_addition_permission, pattern=f"^{ADDITION_PERM_CALLBACK_PREFIX}"
        ),
    ]


async def receive_addition_text(
    *,
    chat: Chat,
    user_id: int,
    username: str | None,
    text: str,
    context: "BotContext",
) -> None:
    """Called by the text/voice handlers when the user is in awaiting_addition."""
    async with context.lock_for(user_id):
        state = context.load_or_create(
            telegram_user_id=user_id,
            telegram_username=username,
            fallback_name="friend",
        )
        if state.phase != Phase.AWAITING_ADDITION:
            return
        state.additions.append(Addition(content=text, permission=None))
        try:
            state.transition_to(Phase.IN_ADDITION_PERMISSIONS)
        except Exception:
            logger.exception("could not transition addition")
            return
        context.save(state)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    CHOICE_LABELS["attributed"],
                    callback_data=f"{ADDITION_PERM_CALLBACK_PREFIX}attributed",
                ),
                InlineKeyboardButton(
                    CHOICE_LABELS["anonymous"],
                    callback_data=f"{ADDITION_PERM_CALLBACK_PREFIX}anonymous",
                ),
                InlineKeyboardButton(
                    CHOICE_LABELS["private"],
                    callback_data=f"{ADDITION_PERM_CALLBACK_PREFIX}private",
                ),
            ]
        ]
    )
    await chat.send_message(
        f"<b>Your addition</b>\n\n{text}\n\n"
        f"How should this be shared with the group?",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
