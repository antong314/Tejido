"""/start and the awaiting_consent -> in_conversation transition.

PRD section 4.3 specifies the awaiting_consent phase: after /start the bot
sends a welcome message explaining what's about to happen and waits for the
participant to confirm they're ready before any AI conversation begins.
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from ..runtime import BotContext
from ..state import Phase

logger = logging.getLogger(__name__)


CONSENT_CALLBACK_PREFIX = "consent:"


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


READY_BUTTON_LABEL = "I'm ready, let's begin"


def build_handlers(context: BotContext) -> list:
    async def start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_chat is None:
            return
        user = update.effective_user

        if not context.is_registered(user.username):
            await update.effective_chat.send_message(NOT_REGISTERED_MESSAGE)
            logger.info(
                "rejected /start from non-registered user id=%s username=%s",
                user.id,
                user.username,
            )
            return

        async with context.lock_for(user.id):
            state = context.load_or_create(
                telegram_user_id=user.id,
                telegram_username=user.username,
                fallback_name=user.first_name or "friend",
            )

            if state.phase != Phase.NOT_STARTED:
                # PRD section 4.8: /start twice -> gentle acknowledgement.
                await update.effective_chat.send_message(ALREADY_BEGUN_MESSAGE)
                return

            state.transition_to(Phase.AWAITING_CONSENT)
            context.save(state)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        READY_BUTTON_LABEL,
                        callback_data=f"{CONSENT_CALLBACK_PREFIX}ready",
                    )
                ]
            ]
        )
        await update.effective_chat.send_message(
            WELCOME_TEMPLATE.format(
                name=state.participant_name,
                question=context.config.session.question,
            ),
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    async def consent_callback(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.from_user is None:
            return
        await query.answer()

        user_id = query.from_user.id
        async with context.lock_for(user_id):
            raw = context.load_or_create(
                telegram_user_id=user_id,
                telegram_username=query.from_user.username,
                fallback_name=query.from_user.first_name or "friend",
            )
            if raw.phase != Phase.AWAITING_CONSENT:
                # Already past consent; nothing to do.
                if query.message:
                    try:
                        await query.edit_message_reply_markup(reply_markup=None)
                    except Exception:
                        logger.debug("failed to clear consent markup", exc_info=True)
                return

            raw.transition_to(Phase.IN_CONVERSATION)
            context.save(raw)

        if query.message:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                logger.debug("failed to clear consent markup", exc_info=True)

        # Kick off the conversation by sending the opening invitation. The
        # facilitator AI is told to begin with a gut-reaction question; we let
        # it generate that opening turn rather than hardcoding text, so the
        # exact phrasing comes from the prompt-tuned model.
        from . import conversation  # local import to avoid circular import

        await conversation.send_opening_turn(update, context)

    return [
        CommandHandler("start", start),
        CallbackQueryHandler(consent_callback, pattern=f"^{CONSENT_CALLBACK_PREFIX}"),
    ]
