"""Translate a callback_data string into the matching controller call.

The Telegram handlers in `handlers/permissions.py` and `handlers/commands.py`
do equivalent dispatch via per-prefix CallbackQueryHandlers; this module is
the unified dispatcher for the web `/callback` endpoint.

Returns an async iterator of OutboundActions that the caller iterates and
broadcasts over SSE.

Callback prefixes (mirroring Telegram for compatibility):
  consent:ready                        — initial "I'm ready" tap
  perm:<index>:<choice>                — per-point sharing choice
  add:<yes|no>                         — "anything to add?" yes/no
  addperm:<choice>                     — addition's sharing choice
  done:<yes|no>                        — early-/done confirmation
  restart:<yes|no>                     — /restart confirmation
  cmd:<done|permissions|restart|help>  — invokes the command (web has no
                                          slash commands; UI buttons POST
                                          these instead)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal, cast

from ..controller import commands as commands_controller
from ..controller import consent as consent_controller
from ..controller import permissions as permissions_controller
from ..runtime import BotContext
from ..state import PermissionChoice
from ..transport import OutboundAction


_VALID_PERMISSION_CHOICES = {"attributed", "anonymous", "private"}
_VALID_YES_NO = {"yes", "no"}


class InvalidCallbackError(ValueError):
    """Raised when callback_data doesn't match any known dispatch."""


def dispatch_callback(
    *,
    callback_data: str,
    participant_id: str,
    display_name: str,
    session: BotContext,
) -> AsyncIterator[OutboundAction]:
    """Match callback_data to a controller method and return its async generator.

    Does NOT iterate — caller does that, broadcasting each yielded action
    as an SSE event.
    """
    if callback_data == consent_controller.CONSENT_CALLBACK_DATA:
        return consent_controller.handle_consent_callback(
            participant_id=participant_id,
            display_name=display_name,
            session=session,
        )

    if callback_data.startswith("perm:"):
        try:
            _, payload = callback_data.split(":", 1)
            idx_str, choice_str = payload.split(":", 1)
            point_index = int(idx_str)
        except ValueError as exc:
            raise InvalidCallbackError(
                f"malformed perm callback: {callback_data!r}"
            ) from exc
        if choice_str not in _VALID_PERMISSION_CHOICES:
            raise InvalidCallbackError(
                f"unknown permission choice: {choice_str!r}"
            )
        return permissions_controller.handle_permission_choice(
            participant_id=participant_id,
            display_name=display_name,
            session=session,
            point_index=point_index,
            choice=cast(PermissionChoice, choice_str),
        )

    if callback_data.startswith("add:"):
        choice = callback_data.split(":", 1)[1] if ":" in callback_data else ""
        if choice not in _VALID_YES_NO:
            raise InvalidCallbackError(f"unknown add choice: {choice!r}")
        return permissions_controller.handle_addition_choice(
            participant_id=participant_id,
            display_name=display_name,
            session=session,
            choice=cast(Literal["yes", "no"], choice),
        )

    if callback_data.startswith("addperm:"):
        choice_str = (
            callback_data.split(":", 1)[1] if ":" in callback_data else ""
        )
        if choice_str not in _VALID_PERMISSION_CHOICES:
            raise InvalidCallbackError(f"unknown addperm choice: {choice_str!r}")
        return permissions_controller.handle_addition_permission(
            participant_id=participant_id,
            display_name=display_name,
            session=session,
            choice=cast(PermissionChoice, choice_str),
        )

    if callback_data.startswith("done:"):
        choice = callback_data.split(":", 1)[1] if ":" in callback_data else ""
        if choice not in _VALID_YES_NO:
            raise InvalidCallbackError(f"unknown done choice: {choice!r}")
        return commands_controller.handle_done_callback(
            participant_id=participant_id,
            display_name=display_name,
            session=session,
            choice=cast(Literal["yes", "no"], choice),
        )

    if callback_data.startswith("restart:"):
        choice = callback_data.split(":", 1)[1] if ":" in callback_data else ""
        if choice not in _VALID_YES_NO:
            raise InvalidCallbackError(f"unknown restart choice: {choice!r}")
        return commands_controller.handle_restart_callback(
            participant_id=participant_id,
            display_name=display_name,
            session=session,
            choice=cast(Literal["yes", "no"], choice),
        )

    if callback_data.startswith("cmd:"):
        cmd = callback_data.split(":", 1)[1] if ":" in callback_data else ""
        if cmd == "done":
            return commands_controller.handle_done(
                participant_id=participant_id,
                display_name=display_name,
                session=session,
            )
        if cmd == "permissions":
            return commands_controller.handle_permissions_command(
                participant_id=participant_id,
                display_name=display_name,
                session=session,
            )
        if cmd == "restart":
            return commands_controller.handle_restart()
        if cmd == "help":
            return commands_controller.handle_help()
        raise InvalidCallbackError(f"unknown command: {cmd!r}")

    raise InvalidCallbackError(f"unrecognized callback_data: {callback_data!r}")


__all__ = ["InvalidCallbackError", "dispatch_callback"]
