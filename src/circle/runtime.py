"""Shared runtime context wired into every Telegram handler.

Avoids stuffing everything into `Application.bot_data` as untyped dicts. A
single `BotContext` is constructed in `bot.py` and passed to handler
factories, which capture it in closures.
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
        # Per-user lock so concurrent voice/text messages from the same user
        # don't interleave state writes. Bot-wide single-process; in-memory is fine.
        self._user_locks: dict[int, asyncio.Lock] = {}
        self._handle_to_participant: dict[str, Participant] = {
            self._normalize_handle(p.handle): p for p in self.config.session.participants
        }

    def lock_for(self, telegram_user_id: int) -> asyncio.Lock:
        lock = self._user_locks.get(telegram_user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._user_locks[telegram_user_id] = lock
        return lock

    @staticmethod
    def _normalize_handle(handle: str) -> str:
        return handle.lstrip("@").lower()

    def lookup_participant_by_username(self, username: str | None) -> Participant | None:
        if not username:
            return None
        return self._handle_to_participant.get(self._normalize_handle(username))

    def load_or_create(
        self, telegram_user_id: int, telegram_username: str | None, fallback_name: str
    ) -> ParticipantState:
        raw = load_participant(self.config.data_dir, telegram_user_id)
        if raw is not None:
            return ParticipantState.from_dict(raw)

        participant = self.lookup_participant_by_username(telegram_username)
        display_name = participant.display_name if participant else fallback_name

        state = new_participant_state(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            session_id=self.config.session.session_id,
            question=self.config.session.question,
        )
        save_participant(self.config.data_dir, telegram_user_id, state.to_dict())
        return state

    def save(self, state: ParticipantState) -> None:
        save_participant(self.config.data_dir, state.participant_id, state.to_dict())

    def is_registered(self, telegram_username: str | None) -> bool:
        return self.lookup_participant_by_username(telegram_username) is not None
