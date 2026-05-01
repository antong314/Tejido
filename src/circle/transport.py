"""Transport-neutral types for the controller layer.

Adapters (Telegram now, web later) translate these into their own primitives.
The controller knows nothing about Telegram updates, callback queries, HTTP
responses, or SSE — it speaks only in these types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ParseMode = Literal["plain", "html"]


@dataclass(frozen=True)
class Choice:
    """A single inline button on a choice prompt."""

    label: str
    callback_data: str


@dataclass(frozen=True)
class SendText:
    """Send a plain message to the participant."""

    text: str
    parse_mode: ParseMode = "plain"


@dataclass(frozen=True)
class SendChoicePrompt:
    """Send a message with inline button choices.

    The adapter renders this as inline keyboard buttons (Telegram), HTML
    radio buttons (web), or whatever the transport's equivalent is. The
    callback_data on each Choice is opaque to the controller — when the
    user picks, the adapter dispatches based on that string.
    """

    text: str
    choices: tuple[Choice, ...]
    parse_mode: ParseMode = "plain"


@dataclass(frozen=True)
class ResolveChoice:
    """Acknowledge a choice prompt by removing its buttons.

    Optionally replaces the prompt text. Only valid as a response to a
    callback (button tap) — adapters render this by editing the source
    message in place. If `text` is None, only the buttons are cleared
    and the original message text stays.
    """

    text: str | None = None
    parse_mode: ParseMode = "plain"


@dataclass(frozen=True)
class TypingIndicator:
    """Show a 'typing'/'thinking' indicator while the next action is prepared."""

    pass


# Tagged union of action types. Adapters dispatch via isinstance().
OutboundAction = SendText | SendChoicePrompt | ResolveChoice | TypingIndicator


__all__ = [
    "Choice",
    "OutboundAction",
    "ParseMode",
    "ResolveChoice",
    "SendChoicePrompt",
    "SendText",
    "TypingIndicator",
]
