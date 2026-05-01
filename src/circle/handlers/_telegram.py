"""Telegram-side rendering of `OutboundAction` values.

Shared by every adapter file: each Telegram handler resolves identity,
calls the appropriate controller method, and pipes the resulting async
iterator through `render_stream` here. Nothing else in the codebase
should depend on Telegram primitives.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from telegram import (
    CallbackQuery,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatAction

from ..runtime import BotContext
from ..transport import (
    OutboundAction,
    ResolveChoice,
    SendChoicePrompt,
    SendText,
    TypingIndicator,
)

logger = logging.getLogger(__name__)


def _telegram_parse_mode(parse_mode: str) -> str | None:
    return "HTML" if parse_mode == "html" else None


def resolve_telegram_identity(
    context: BotContext, user
) -> tuple[str, str]:
    """Resolve a Telegram user object to (participant_id, display_name).

    `participant_id` is the str-coerced Telegram user id (storage uses this
    as the file key). `display_name` is the configured participant's
    display name when registered, or the user's first name (or "friend")
    as a fallback.
    """
    participant = context.lookup_participant_by_username(user.username)
    display_name = (
        participant.display_name if participant else (user.first_name or "friend")
    )
    return str(user.id), display_name


async def render_action(
    action: OutboundAction,
    *,
    chat: Chat,
    callback_query: CallbackQuery | None = None,
) -> None:
    """Render a single OutboundAction to the Telegram transport."""
    if isinstance(action, SendText):
        await chat.send_message(
            action.text, parse_mode=_telegram_parse_mode(action.parse_mode)
        )
    elif isinstance(action, SendChoicePrompt):
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(c.label, callback_data=c.callback_data)
                    for c in action.choices
                ]
            ]
        )
        await chat.send_message(
            action.text,
            parse_mode=_telegram_parse_mode(action.parse_mode),
            reply_markup=keyboard,
        )
    elif isinstance(action, ResolveChoice):
        if callback_query is None:
            logger.warning(
                "ResolveChoice yielded outside callback context; dropping"
            )
            return
        try:
            if action.text is None:
                await callback_query.edit_message_reply_markup(reply_markup=None)
            else:
                await callback_query.edit_message_text(
                    action.text,
                    parse_mode=_telegram_parse_mode(action.parse_mode),
                )
        except Exception:
            logger.debug("failed to edit callback message", exc_info=True)
    elif isinstance(action, TypingIndicator):
        await chat.send_chat_action(ChatAction.TYPING)
    else:
        logger.warning("unknown OutboundAction: %r", action)


async def render_stream(
    actions: AsyncIterator[OutboundAction],
    *,
    chat: Chat,
    callback_query: CallbackQuery | None = None,
) -> None:
    """Consume an async iterator of actions, rendering each in order."""
    async for action in actions:
        await render_action(action, chat=chat, callback_query=callback_query)
