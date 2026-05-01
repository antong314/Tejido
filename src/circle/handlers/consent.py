"""Telegram adapter for /start and the consent button.

All conversation logic lives in `circle.controller.consent`; this file
just translates Telegram primitives (Update, CallbackQuery) into calls
into the controller and pipes the yielded actions to Telegram.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from ..controller import consent as consent_controller
from ..runtime import BotContext
from ._telegram import render_stream, resolve_telegram_identity

logger = logging.getLogger(__name__)


CONSENT_CALLBACK_PREFIX = "consent:"


def build_handlers(context: BotContext) -> list:
    async def start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_chat is None:
            return
        user = update.effective_user
        chat = update.effective_chat

        if not context.is_registered(user.username):
            await chat.send_message(consent_controller.NOT_REGISTERED_MESSAGE)
            logger.info(
                "rejected /start from non-registered user id=%s username=%s",
                user.id,
                user.username,
            )
            return

        participant_id, display_name = resolve_telegram_identity(context, user)
        await render_stream(
            consent_controller.handle_start(
                participant_id=participant_id,
                display_name=display_name,
                session=context,
            ),
            chat=chat,
        )

    async def consent_callback(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.from_user is None or query.message is None:
            return
        await query.answer()

        participant_id, display_name = resolve_telegram_identity(context, query.from_user)
        await render_stream(
            consent_controller.handle_consent_callback(
                participant_id=participant_id,
                display_name=display_name,
                session=context,
            ),
            chat=query.message.chat,
            callback_query=query,
        )

    return [
        CommandHandler("start", start),
        CallbackQueryHandler(consent_callback, pattern=f"^{CONSENT_CALLBACK_PREFIX}"),
    ]
