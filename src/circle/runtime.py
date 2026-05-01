"""Shared runtime context for the controller and adapters.

A single `BotContext` is constructed at startup and threaded into the
controller (transport-neutral) and adapters (Telegram now, web later).
All methods are transport-neutral: an adapter resolves its transport
identity to a `participant_id` + `display_name` before calling in.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .anthropic_client import AnthropicClient
from .config import AppConfig
from .state import ParticipantState, new_participant_state
from .storage import (
    load_participant,
    register_in_index,
    save_participant,
)
from .whisper_client import WhisperTranscriber

logger = logging.getLogger(__name__)


@dataclass
class BotContext:
    config: AppConfig
    anthropic: AnthropicClient
    whisper: WhisperTranscriber

    def __post_init__(self) -> None:
        # Per-participant lock so concurrent voice/text/callback events for
        # the same participant don't interleave state writes. Single-process,
        # in-memory; keyed by the canonical str participant_id (whatever the
        # adapter resolved the transport identity to).
        self._user_locks: dict[str, asyncio.Lock] = {}

    def lock_for(self, participant_id: str) -> asyncio.Lock:
        lock = self._user_locks.get(participant_id)
        if lock is None:
            lock = asyncio.Lock()
            self._user_locks[participant_id] = lock
        return lock

    def load_or_create(
        self, participant_id: str, display_name: str
    ) -> ParticipantState:
        """Load existing state or create fresh state for a new participant.

        `display_name` is used only on the create path. The adapter has
        already resolved the transport identity to a stable participant_id
        and chosen the display name (Telegram first_name, or the name the
        user typed in the web join form).

        On creation, also registers the participant in the session's
        `_index.json` so the web join endpoint and the dashboard can list
        joined participants without scanning every JSON.
        """
        raw = load_participant(self.config.data_dir, participant_id)
        if raw is not None:
            return ParticipantState.from_dict(raw)

        state = new_participant_state(
            telegram_user_id=participant_id,
            display_name=display_name,
            session_id=self.config.session.session_id,
            question=self.config.session.question,
        )
        save_participant(self.config.data_dir, participant_id, state.to_dict())
        register_in_index(self.config.data_dir, participant_id, display_name)
        return state

    def save(self, state: ParticipantState) -> None:
        save_participant(self.config.data_dir, state.participant_id, state.to_dict())
