"""Telegram adapter for text and voice messages during the conversation.

Voice notes are downloaded and transcribed locally (PRD section 5.1) before
being handed to the transport-neutral controller as text. All routing,
state mutation, and LLM interaction lives in `circle.controller.conversation`.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, MessageHandler, filters

from ..controller import conversation as conversation_controller
from ..runtime import BotContext
from ..whisper_client import TranscriptionError, make_temp_ogg
from ._telegram import render_stream, resolve_telegram_identity

logger = logging.getLogger(__name__)


VOICE_FAILED_MESSAGE = (
    "Sorry, I couldn't transcribe that voice message. Could you try again, or "
    "type out what you wanted to say?"
)


def build_handlers(context: BotContext) -> list:
    async def handle_text(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if (
            update.effective_message is None
            or update.effective_user is None
            or update.effective_chat is None
        ):
            return
        if update.effective_message.text is None:
            return

        participant_id, display_name = resolve_telegram_identity(update.effective_user)
        await render_stream(
            conversation_controller.handle_message(
                participant_id=participant_id,
                display_name=display_name,
                session=context,
                text=update.effective_message.text,
                via="text",
                detected_language=None,
            ),
            chat=update.effective_chat,
        )

    async def handle_voice(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if message is None or chat is None or user is None:
            return
        if message.voice is None and message.audio is None:
            return

        # Show "typing" while we download + transcribe locally; the model
        # call itself happens inside the controller (which yields its own
        # TypingIndicator before that step).
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

        participant_id, display_name = resolve_telegram_identity(user)
        await render_stream(
            conversation_controller.handle_message(
                participant_id=participant_id,
                display_name=display_name,
                session=context,
                text=result.text,
                via="voice",
                detected_language=result.language,
            ),
            chat=chat,
        )

    return [
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
        MessageHandler(filters.VOICE | filters.AUDIO, handle_voice),
    ]
