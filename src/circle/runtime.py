"""Shared runtime context for the controller and adapters.

A single `BotContext` is constructed at startup and threaded into the
controller (transport-neutral) and adapters (Telegram now, web later).
The controller-facing methods (`lock_for`, `load_or_create`, `save`) are
transport-neutral. The Telegram adapter additionally uses
`is_registered` / `lookup_participant_by_username` to resolve a Telegram
@username to a configured participant before invoking the controller.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .anthropic_client import AnthropicClient
from .config import AppConfig, Participant
from .state import ParticipantState, new_participant_state
from .storage import load_participant, save_participant
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
        self._handle_to_participant: dict[str, Participant] = {
            self._normalize_handle(p.handle): p for p in self.config.session.participants
        }

    def lock_for(self, participant_id: str) -> asyncio.Lock:
        lock = self._user_locks.get(participant_id)
        if lock is None:
            lock = asyncio.Lock()
            self._user_locks[participant_id] = lock
        return lock

    @staticmethod
    def _normalize_handle(handle: str) -> str:
        return handle.lstrip("@").lower()

    def lookup_participant_by_username(self, username: str | None) -> Participant | None:
        """Telegram-specific: resolve an `@username` to a configured participant."""
        if not username:
            return None
        return self._handle_to_participant.get(self._normalize_handle(username))

    def is_registered(self, telegram_username: str | None) -> bool:
        """Telegram-specific: is this username on the participant list?"""
        return self.lookup_participant_by_username(telegram_username) is not None

    def load_or_create(
        self, participant_id: str, display_name: str
    ) -> ParticipantState:
        """Load existing state or create fresh state for a new participant.

        `display_name` is used only on the create path. The adapter resolves
        identity (Telegram username → participant entry) and supplies a real
        display name when known, or a fallback (e.g. the user's first name)
        when the participant isn't on the registered list.
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
        return state

    def save(self, state: ParticipantState) -> None:
        save_participant(self.config.data_dir, state.participant_id, state.to_dict())
