"""Telegram adapter for /done, /permissions, /restart, /help.

Each command has matching logic in `circle.controller.commands`; this
file only translates Telegram primitives into controller calls.
"""

from __future__ import annotations

import logging
from typing import Literal, cast

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from ..controller import commands as commands_controller
from ..runtime import BotContext
from ._telegram import render_stream, resolve_telegram_identity

logger = logging.getLogger(__name__)


DONE_CONFIRM_PREFIX = "done:"
RESTART_CONFIRM_PREFIX = "restart:"


_VALID_YES_NO: set[str] = {"yes", "no"}


def build_handlers(context: BotContext) -> list:
    async def help_command(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat is None:
            return
        await render_stream(
            commands_controller.handle_help(),
            chat=update.effective_chat,
        )

    async def done_command(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        if chat is None or user is None:
            return
        participant_id, display_name = resolve_telegram_identity(user)
        await render_stream(
            commands_controller.handle_done(
                participant_id=participant_id,
                display_name=display_name,
                session=context,
            ),
            chat=chat,
        )

    async def done_callback(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.from_user is None or query.message is None:
            return
        await query.answer()
        choice = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
        if choice not in _VALID_YES_NO:
            return
        participant_id, display_name = resolve_telegram_identity(query.from_user)
        await render_stream(
            commands_controller.handle_done_callback(
                participant_id=participant_id,
                display_name=display_name,
                session=context,
                choice=cast(Literal["yes", "no"], choice),
            ),
            chat=query.message.chat,
            callback_query=query,
        )

    async def permissions_command(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        user = update.effective_user
        if chat is None or user is None:
            return
        participant_id, display_name = resolve_telegram_identity(user)
        await render_stream(
            commands_controller.handle_permissions_command(
                participant_id=participant_id,
                display_name=display_name,
                session=context,
            ),
            chat=chat,
        )

    async def restart_command(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        if chat is None:
            return
        await render_stream(
            commands_controller.handle_restart(),
            chat=chat,
        )

    async def restart_callback(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.from_user is None or query.message is None:
            return
        await query.answer()
        choice = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
        if choice not in _VALID_YES_NO:
            return
        participant_id, display_name = resolve_telegram_identity(query.from_user)
        await render_stream(
            commands_controller.handle_restart_callback(
                participant_id=participant_id,
                display_name=display_name,
                session=context,
                choice=cast(Literal["yes", "no"], choice),
            ),
            chat=query.message.chat,
            callback_query=query,
        )

    return [
        CommandHandler("help", help_command),
        CommandHandler("done", done_command),
        CommandHandler("permissions", permissions_command),
        CommandHandler("restart", restart_command),
        CallbackQueryHandler(done_callback, pattern=f"^{DONE_CONFIRM_PREFIX}"),
        CallbackQueryHandler(restart_callback, pattern=f"^{RESTART_CONFIRM_PREFIX}"),
    ]
