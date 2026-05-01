"""Telegram adapter for permission-button callbacks.

Three callback patterns:
  - `perm:{index}:{choice}`     — per-point sharing choice
  - `add:{yes|no}`              — yes/no on the "anything to add?" prompt
  - `addperm:{choice}`          — sharing choice for the addition itself

All conversation logic lives in `circle.controller.permissions`.
"""

from __future__ import annotations

import logging
from typing import Literal, cast

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from ..controller import permissions as permissions_controller
from ..runtime import BotContext
from ..state import PermissionChoice
from ._telegram import render_stream, resolve_telegram_identity

logger = logging.getLogger(__name__)


PERMISSION_CALLBACK_PREFIX = "perm:"
ADDITION_CALLBACK_PREFIX = "add:"
ADDITION_PERM_CALLBACK_PREFIX = "addperm:"


_VALID_PERMISSION_CHOICES: set[str] = {"attributed", "anonymous", "private"}
_VALID_YES_NO: set[str] = {"yes", "no"}


def build_handlers(context: BotContext) -> list:
    async def on_permission_choice(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.from_user is None or query.message is None:
            return
        await query.answer()

        try:
            _, payload = (query.data or "").split(":", 1)
            idx_str, choice_str = payload.split(":", 1)
            point_index = int(idx_str)
            if choice_str not in _VALID_PERMISSION_CHOICES:
                raise ValueError(f"unknown choice {choice_str}")
        except Exception:
            logger.warning("bad permission callback data: %r", query.data)
            return

        participant_id, display_name = resolve_telegram_identity(query.from_user)
        await render_stream(
            permissions_controller.handle_permission_choice(
                participant_id=participant_id,
                display_name=display_name,
                session=context,
                point_index=point_index,
                choice=cast(PermissionChoice, choice_str),
            ),
            chat=query.message.chat,
            callback_query=query,
        )

    async def on_addition_choice(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.from_user is None or query.message is None:
            return
        await query.answer()

        choice = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
        if choice not in _VALID_YES_NO:
            logger.warning("bad addition callback data: %r", query.data)
            return

        participant_id, display_name = resolve_telegram_identity(query.from_user)
        await render_stream(
            permissions_controller.handle_addition_choice(
                participant_id=participant_id,
                display_name=display_name,
                session=context,
                choice=cast(Literal["yes", "no"], choice),
            ),
            chat=query.message.chat,
            callback_query=query,
        )

    async def on_addition_permission(
        update: Update, _ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if query is None or query.from_user is None or query.message is None:
            return
        await query.answer()

        try:
            choice_str = (query.data or "").split(":", 1)[1]
            if choice_str not in _VALID_PERMISSION_CHOICES:
                raise ValueError(f"unknown choice {choice_str}")
        except Exception:
            logger.warning("bad addition perm callback: %r", query.data)
            return

        participant_id, display_name = resolve_telegram_identity(query.from_user)
        await render_stream(
            permissions_controller.handle_addition_permission(
                participant_id=participant_id,
                display_name=display_name,
                session=context,
                choice=cast(PermissionChoice, choice_str),
            ),
            chat=query.message.chat,
            callback_query=query,
        )

    return [
        CallbackQueryHandler(on_permission_choice, pattern=f"^{PERMISSION_CALLBACK_PREFIX}"),
        CallbackQueryHandler(on_addition_choice, pattern=f"^{ADDITION_CALLBACK_PREFIX}"),
        CallbackQueryHandler(
            on_addition_permission, pattern=f"^{ADDITION_PERM_CALLBACK_PREFIX}"
        ),
    ]
