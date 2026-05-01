"""/done, /permissions, /restart, /help — slash command logic.

Each command corresponds to a PRD section 4.8 edge case.

  /done        — participant signals they're finished talking; if very
                 early (<5 minutes) we confirm before transitioning.
  /permissions — re-open the walk-through to edit choices, valid until
                 the file has been used in synthesis (we approximate that
                 by allowing it any time before the bot is shut down).
  /restart     — wipe state and return to not_started; participant must
                 /start again. Confirmation required.
  /help        — short pointer message.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Literal

from ..runtime import BotContext
from ..state import ParticipantState, Phase
from ..transport import (
    Choice,
    OutboundAction,
    ResolveChoice,
    SendChoicePrompt,
    SendText,
)
from . import permissions as permissions_controller

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

NOT_IN_CONVERSATION_MESSAGE = "We're not in the middle of a conversation right now."

NOTHING_TO_EDIT_MESSAGE = (
    "There's nothing to edit yet — we haven't gotten to the permissions step."
)

PERMISSIONS_NOT_YET_MESSAGE = (
    "You can edit permissions once we've gotten to that step."
)

PERMISSIONS_RESTART_MESSAGE = (
    "OK — let's walk through your sharing choices again. Your previous "
    "selections have been cleared so you can choose fresh."
)

KEEP_GOING_MESSAGE = "OK, let's keep going."
RESTART_CANCELLED_MESSAGE = "OK, nothing was changed."
RESTART_DONE_MESSAGE = (
    "Done — everything is cleared. Send /start when you're ready to begin again."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _minutes_in_phase(phase_entered_at: str) -> int:
    try:
        entered = datetime.fromisoformat(phase_entered_at)
    except Exception:
        return 999
    return max(0, int((_now() - entered).total_seconds() // 60))


def _reset_permissions(state: ParticipantState) -> None:
    state.current_point_index = 0
    for point in state.extracted_points:
        point.permission = None
    for addition in state.additions:
        addition.permission = None


async def handle_help() -> AsyncIterator[OutboundAction]:
    yield SendText(HELP_MESSAGE)


async def handle_done(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
) -> AsyncIterator[OutboundAction]:
    """/done — wrap up early. If <5 minutes, confirm; else go straight to permissions."""
    in_conversation = False
    elapsed = 0
    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        if state.phase == Phase.IN_CONVERSATION:
            in_conversation = True
            elapsed = _minutes_in_phase(state.phase_entered_at)

    if not in_conversation:
        yield SendText(NOT_IN_CONVERSATION_MESSAGE)
        return

    if elapsed < EARLY_DONE_THRESHOLD_MINUTES:
        yield SendChoicePrompt(
            text=DONE_TOO_EARLY_TEMPLATE.format(minutes=elapsed),
            choices=(
                Choice(
                    label="Yes, I'm done",
                    callback_data=f"{DONE_CONFIRM_PREFIX}yes",
                ),
                Choice(
                    label="No, keep going",
                    callback_data=f"{DONE_CONFIRM_PREFIX}no",
                ),
            ),
        )
        return

    async for action in permissions_controller.begin_permissions_phase(
        participant_id=participant_id, display_name=display_name, session=session
    ):
        yield action


async def handle_done_callback(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
    choice: Literal["yes", "no"],
) -> AsyncIterator[OutboundAction]:
    yield ResolveChoice()
    if choice != "yes":
        yield SendText(KEEP_GOING_MESSAGE)
        return
    async for action in permissions_controller.begin_permissions_phase(
        participant_id=participant_id, display_name=display_name, session=session
    ):
        yield action


async def handle_permissions_command(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
) -> AsyncIterator[OutboundAction]:
    """/permissions — re-open the walk-through to edit choices.

    PRD section 4.8: from `complete` we transition back to `in_permissions`;
    in either case the walk-through restarts at point 0 with previous
    selections cleared.
    """
    can_walkthrough = False
    early_message: str | None = None
    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        if not state.extracted_points:
            early_message = NOTHING_TO_EDIT_MESSAGE
        elif state.phase == Phase.COMPLETE:
            state.transition_to(Phase.IN_PERMISSIONS)
            _reset_permissions(state)
            session.save(state)
            can_walkthrough = True
        elif state.phase == Phase.IN_PERMISSIONS:
            _reset_permissions(state)
            session.save(state)
            can_walkthrough = True
        else:
            early_message = PERMISSIONS_NOT_YET_MESSAGE

    if early_message is not None:
        yield SendText(early_message)
        return

    if not can_walkthrough:
        return

    yield SendText(PERMISSIONS_RESTART_MESSAGE)
    async for action in permissions_controller.begin_permissions_phase(
        participant_id=participant_id, display_name=display_name, session=session
    ):
        yield action


async def handle_restart() -> AsyncIterator[OutboundAction]:
    """/restart — send the confirmation prompt."""
    yield SendChoicePrompt(
        text=RESTART_CONFIRM_MESSAGE,
        choices=(
            Choice(
                label="Yes, restart",
                callback_data=f"{RESTART_CONFIRM_PREFIX}yes",
            ),
            Choice(
                label="No, keep what I have",
                callback_data=f"{RESTART_CONFIRM_PREFIX}no",
            ),
        ),
    )


async def handle_restart_callback(
    *,
    participant_id: str,
    display_name: str,
    session: BotContext,
    choice: Literal["yes", "no"],
) -> AsyncIterator[OutboundAction]:
    yield ResolveChoice()
    if choice != "yes":
        yield SendText(RESTART_CANCELLED_MESSAGE)
        return

    async with session.lock_for(participant_id):
        state = session.load_or_create(participant_id, display_name)
        try:
            state.transition_to(Phase.NOT_STARTED)
            session.save(state)
        except Exception:
            logger.exception("could not restart")
            return

    yield SendText(RESTART_DONE_MESSAGE)
