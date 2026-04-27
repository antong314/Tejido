"""Facilitator conversation: text + voice messages during in_conversation.

Implements PRD section 4.4 message handling. On each user message:
  1. Append to transcript with timestamp + via.
  2. Persist to disk before calling Anthropic (so a crash doesn't lose words).
  3. Call Anthropic with the facilitator system prompt + history.
  4. Detect the [READY_FOR_PERMISSIONS] token; strip it before replying.
  5. Save the assistant turn, then transition to permissions if signaled.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, MessageHandler, filters

from ..anthropic_client import (
    FACILITATOR_MAX_TOKENS,
    FACILITATOR_TEMPERATURE,
    ChatMessage,
)
from ..prompts import READY_TOKEN, render_facilitator_prompt
from ..state import Phase, TranscriptTurn
from ..whisper_client import TranscriptionError, make_temp_ogg

if TYPE_CHECKING:
    from ..runtime import BotContext

logger = logging.getLogger(__name__)


VOICE_FAILED_MESSAGE = (
    "Sorry, I couldn't transcribe that voice message. Could you try again, or "
    "type out what you wanted to say?"
)

WRONG_PHASE_MESSAGE = (
    "We're in the {phase} phase right now — let's finish that before continuing."
)

API_FAILURE_MESSAGE = (
    "I'm having a technical issue on my end. The facilitator can help — please "
    "let them know, and we'll pick this back up."
)

# PRD section 4.4 step 7: "transition to permissions phase after a short delay"
READY_TRANSITION_DELAY_SECONDS = 2.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_ready_token(text: str) -> tuple[str, bool]:
    if READY_TOKEN not in text:
        return text, False
    cleaned_lines = [
        line for line in text.splitlines() if line.strip() != READY_TOKEN
    ]
    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned, True


async def send_opening_turn(update: Update, context: "BotContext") -> None:
    """Generate and send the very first facilitator message.

    Called right after the consent button is tapped. Drives the model with an
    empty user history; the system prompt instructs it to open with a
    gut-reaction question.
    """
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return

    async with context.lock_for(user.id):
        state = context.load_or_create(
            telegram_user_id=user.id,
            telegram_username=user.username,
            fallback_name=user.first_name or "friend",
        )
        if state.phase != Phase.IN_CONVERSATION:
            return

        # Seed with a synthetic user nudge so the model produces an opening
        # turn (the Anthropic Messages API requires the first message to be
        # from the user).
        seed = ChatMessage(role="user", content="(I'm ready to begin.)")
        await chat.send_chat_action(ChatAction.TYPING)
        try:
            reply = await context.anthropic.complete(
                system=render_facilitator_prompt(
                    question=context.config.session.question,
                    context=context.config.session.context,
                ),
                messages=[seed],
                model=context.config.session.facilitator_model,
                temperature=FACILITATOR_TEMPERATURE,
                max_tokens=FACILITATOR_MAX_TOKENS,
            )
        except Exception:
            logger.exception("opening turn failed")
            await chat.send_message(API_FAILURE_MESSAGE)
            return

        cleaned, _ = _strip_ready_token(reply)
        state.transcript.append(
            TranscriptTurn(role="assistant", content=cleaned, timestamp=_now_iso())
        )
        context.save(state)

    await chat.send_message(cleaned)


def build_handlers(context: "BotContext") -> list:
    async def handle_text(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            return
        if update.effective_message.text is None:
            return
        await _route_user_message(
            update=update,
            user_text=update.effective_message.text,
            via="text",
            detected_language=None,
            context=context,
        )

    async def handle_voice(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if message is None or chat is None or user is None:
            return
        if message.voice is None and message.audio is None:
            return

        await chat.send_chat_action(ChatAction.TYPING)
        ogg_path = make_temp_ogg()
        try:
            file_obj = await (message.voice or message.audio).get_file()
            await file_obj.download_to_drive(custom_path=str(ogg_path))
            try:
                result = await context.whisper.transcribe_ogg(ogg_path)
            except TranscriptionError:
                logger.exception("voice transcription failed")
                await chat.send_message(VOICE_FAILED_MESSAGE)
                return
        except Exception:
            logger.exception("voice download failed")
            await chat.send_message(VOICE_FAILED_MESSAGE)
            return

        await _route_user_message(
            update=update,
            user_text=result.text,
            via="voice",
            detected_language=result.language,
            context=context,
        )

    return [
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
        MessageHandler(filters.VOICE | filters.AUDIO, handle_voice),
    ]


async def _route_user_message(
    *,
    update: Update,
    user_text: str,
    via: str,
    detected_language: str | None,
    context: "BotContext",
) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return

    # Peek at the current phase under lock to decide where to route this message.
    async with context.lock_for(user.id):
        state = context.load_or_create(
            telegram_user_id=user.id,
            telegram_username=user.username,
            fallback_name=user.first_name or "friend",
        )
        current_phase = state.phase

    if current_phase == Phase.NOT_STARTED:
        await chat.send_message("Send /start when you're ready to begin.")
        return
    if current_phase == Phase.AWAITING_CONSENT:
        await chat.send_message(
            "Tap the button above when you're ready, and we'll begin."
        )
        return
    if current_phase == Phase.AWAITING_ADDITION:
        from . import permissions  # local import to avoid circular import

        await permissions.receive_addition_text(
            chat=chat,
            user_id=user.id,
            username=user.username,
            text=user_text,
            context=context,
        )
        return
    if current_phase != Phase.IN_CONVERSATION:
        # Permissions / in_addition_permissions / complete are handled by
        # their own handlers; a stray text message here gets a polite nudge.
        phase_label = current_phase.value.replace("_", " ")
        await chat.send_message(WRONG_PHASE_MESSAGE.format(phase=phase_label))
        return

    async with context.lock_for(user.id):
        state = context.load_or_create(
            telegram_user_id=user.id,
            telegram_username=user.username,
            fallback_name=user.first_name or "friend",
        )
        if state.phase != Phase.IN_CONVERSATION:
            # Phase changed between peek and lock acquisition; bail.
            return

        state.transcript.append(
            TranscriptTurn(
                role="user",
                content=user_text,
                timestamp=_now_iso(),
                via=via,  # type: ignore[arg-type]
                detected_language=detected_language,
            )
        )
        context.save(state)

        await chat.send_chat_action(ChatAction.TYPING)
        messages = [
            ChatMessage(role=turn.role, content=turn.content) for turn in state.transcript
        ]

        try:
            reply = await context.anthropic.complete(
                system=render_facilitator_prompt(
                    question=context.config.session.question,
                    context=context.config.session.context,
                ),
                messages=messages,
                model=context.config.session.facilitator_model,
                temperature=FACILITATOR_TEMPERATURE,
                max_tokens=FACILITATOR_MAX_TOKENS,
            )
        except Exception:
            logger.exception("facilitator completion failed")
            await chat.send_message(API_FAILURE_MESSAGE)
            return

        cleaned, ready = _strip_ready_token(reply)
        if not cleaned:
            cleaned = "Let's pause here for a moment."

        state.transcript.append(
            TranscriptTurn(role="assistant", content=cleaned, timestamp=_now_iso())
        )
        context.save(state)

    await chat.send_message(cleaned)

    if ready:
        await asyncio.sleep(READY_TRANSITION_DELAY_SECONDS)
        from . import permissions  # local import to avoid circular import

        await permissions.begin_permissions_phase(
            chat=chat, user_id=user.id, username=user.username, context=context
        )
