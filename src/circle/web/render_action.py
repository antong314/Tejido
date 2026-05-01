"""Serialize OutboundAction values to JSON dicts for the web transport.

Symmetric with `circle/handlers/_telegram.py:render_action`, which converts
the same actions into Telegram primitives. The web side just packages them
as JSON; rendering happens in the React frontend.

The JSON shapes here ARE the public protocol between the FastAPI server
and the frontend. Keep them stable; new fields are fine, renames break
the client.
"""

from __future__ import annotations

from typing import Any

from ..transport import (
    OutboundAction,
    ResolveChoice,
    SendChoicePrompt,
    SendText,
    TypingIndicator,
)


def action_to_json(action: OutboundAction) -> dict[str, Any]:
    if isinstance(action, SendText):
        return {
            "type": "text",
            "text": action.text,
            "parse_mode": action.parse_mode,
        }
    if isinstance(action, SendChoicePrompt):
        return {
            "type": "choice_prompt",
            "text": action.text,
            "parse_mode": action.parse_mode,
            "choices": [
                {"label": c.label, "callback_data": c.callback_data}
                for c in action.choices
            ],
        }
    if isinstance(action, ResolveChoice):
        return {
            "type": "resolve_choice",
            "text": action.text,
            "parse_mode": action.parse_mode,
        }
    if isinstance(action, TypingIndicator):
        return {"type": "typing"}
    raise TypeError(f"unknown OutboundAction: {action!r}")


__all__ = ["action_to_json"]
