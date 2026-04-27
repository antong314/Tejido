"""Slash commands beyond /start: /done, /permissions, /restart, /help.

Each one corresponds to a PRD section 4.8 edge case.

  /done       — participant signals they're finished talking; if very early
                (<5 minutes) we confirm before transitioning to permissions.
  /permissions — re-open the permissions walk-through to edit choices, valid
                until the file has been used in synthesis (we approximate
                that by allowing it any time before the bot is shut down).
  /restart    — wipe state and return to not_started; participant must
                /start again. Confirmation required.
  /help       — short pointer message.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from ..state import Phase

if TYPE_CHECKING:
    from ..runtime import BotContext

logger = logging.getLogger(__name__)


DONE_CONFIRM_PREFIX = "done:"
RESTART_CONFIRM_PREFIX = "restart:"

EARLY_DONE_THRESHOLD_MINUTES = 5

HELP_MESSAGE = (
    "Just send messages — text or voice — and we'll keep going.\n\n"
    "Other commands you can use:\n"
    "/done — when you feel you've said what you wanted to say\n"
    "/permissions — re-open your sharing choices to edit them\n"
    "/restart — start over from scratch (this erases everything)"
)

DONE_TOO_EARLY_TEMPLATE = (
    "Are you sure? We've only been talking for {minutes} minute(s)."
)

RESTART_CONFIRM_MESSAGE = (
    "If you restart, everything you've said will be erased and we'll start "
    "from the beginning. Are you sure?"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _minutes_in_phase(state) -> int:
    try:
        entered = datetime.fromisoformat(state.phase_entered_at)
    except Exception:
        return 999
    return max(0, int((_now() - entered).total_seconds() // 60))


def build_handlers(context: "BotContext") -> list:
    async def help_command(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat is None:
            return
        await update.effective_chat.send_message(HELP_MESSAGE)

    async def done_command(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
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
                await chat.send_message(
                    "We're not in the middle of a conversation right now."
                )
                return
            elapsed = _minutes_in_phase(state)

        if elapsed < EARLY_DONE_THRESHOLD_MINUTES:
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Yes, I'm done", callback_data=f"{DONE_CONFIRM_PREFIX}yes"
                        ),
                        InlineKeyboardButton(
                            "No, keep going", callback_data=f"{DONE_CONFIRM_PREFIX}no"
                        ),
                    ]
                ]
            )
            await chat.send_message(
                DONE_TOO_EARLY_TEMPLATE.format(minutes=elapsed),
                reply_markup=keyboard,
            )
            return

        await _begin_permissions(chat, user.id, user.username, context)

    async def done_callback(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.from_user is None or query.message is None:
            return
        await query.answer()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            logger.debug("failed to clear done markup", exc_info=True)

        choice = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
        if choice != "yes":
            await query.message.chat.send_message("OK, let's keep going.")
            return
        await _begin_permissions(
            query.message.chat, query.from_user.id, query.from_user.username, context
        )

    async def permissions_command(
        update: Update, _ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        user = update.effective_user
        if chat is None or user is None:
            return

        from . import permissions  # local import to avoid circular import

        async with context.lock_for(user.id):
            state = context.load_or_create(
                telegram_user_id=user.id,
                telegram_username=user.username,
                fallback_name=user.first_name or "friend",
            )
            if not state.extracted_points:
                await chat.send_message(
                    "There's nothing to edit yet — we haven't gotten to the "
                    "permissions step."
                )
                return
            # PRD section 4.8 allows /permissions re-edit. From `complete` we
            # transition back to `in_permissions`; the walk-through restarts
            # at point 0 so the participant can review every choice.
            if state.phase == Phase.COMPLETE:
                state.transition_to(Phase.IN_PERMISSIONS)
            elif state.phase != Phase.IN_PERMISSIONS:
                await chat.send_message(
                    "You can edit permissions once we've gotten to that step."
                )
                return
            state.current_point_index = 0
            for point in state.extracted_points:
                point.permission = None
            for addition in state.additions:
                addition.permission = None
            context.save(state)

        await chat.send_message(
            "OK — let's walk through your sharing choices again. Your previous "
            "selections have been cleared so you can choose fresh."
        )
        await permissions.begin_permissions_phase(
            chat=chat, user_id=user.id, username=user.username, context=context
        )

    async def restart_command(
        update: Update, _ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat = update.effective_chat
        if chat is None:
            return
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Yes, restart", callback_data=f"{RESTART_CONFIRM_PREFIX}yes"
                    ),
                    InlineKeyboardButton(
                        "No, keep what I have",
                        callback_data=f"{RESTART_CONFIRM_PREFIX}no",
                    ),
                ]
            ]
        )
        await chat.send_message(RESTART_CONFIRM_MESSAGE, reply_markup=keyboard)

    async def restart_callback(
        update: Update, _ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if query is None or query.from_user is None or query.message is None:
            return
        await query.answer()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            logger.debug("failed to clear restart markup", exc_info=True)

        choice = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""
        if choice != "yes":
            await query.message.chat.send_message("OK, nothing was changed.")
            return

        async with context.lock_for(query.from_user.id):
            state = context.load_or_create(
                telegram_user_id=query.from_user.id,
                telegram_username=query.from_user.username,
                fallback_name=query.from_user.first_name or "friend",
            )
            try:
                state.transition_to(Phase.NOT_STARTED)
            except Exception:
                logger.exception("could not restart")
                return
            context.save(state)

        await query.message.chat.send_message(
            "Done — everything is cleared. Send /start when you're ready to begin again."
        )

    return [
        CommandHandler("help", help_command),
        CommandHandler("done", done_command),
        CommandHandler("permissions", permissions_command),
        CommandHandler("restart", restart_command),
        CallbackQueryHandler(done_callback, pattern=f"^{DONE_CONFIRM_PREFIX}"),
        CallbackQueryHandler(restart_callback, pattern=f"^{RESTART_CONFIRM_PREFIX}"),
    ]


async def _begin_permissions(
    chat, user_id: int, username: str | None, context: "BotContext"
) -> None:
    from . import permissions  # local import to avoid circular import

    await permissions.begin_permissions_phase(
        chat=chat, user_id=user_id, username=username, context=context
    )
