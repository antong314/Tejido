"""Per-session runtime context shared between the controller and adapters.

A `BotContext` is now strictly per-session. The SessionRegistry holds one
per active session; web routes look it up by URL session id, and the
Telegram adapter (which is single-session) holds a reference to whichever
one was selected at startup.

Methods are transport-neutral: an adapter resolves its transport identity
to (participant_id, display_name) before calling in.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from .anthropic_client import AnthropicClient
from .config import AppConfig
from .personas import resolve_persona_text
from .prompts import render_facilitator_prompt
from .session import Session
from .state import ParticipantState, new_participant_state
from .storage import (
    load_participant,
    register_in_index,
    save_participant,
)
from .whisper_client import WhisperTranscriber
from .workflows import build_question_block, get_context, get_default_persona

logger = logging.getLogger(__name__)


@dataclass
class BotContext:
    session: Session
    app_config: AppConfig
    anthropic: AnthropicClient
    whisper: WhisperTranscriber

    def __post_init__(self) -> None:
        # Per-participant lock — concurrent voice/text/callback events for
        # the same participant don't interleave state writes.
        self._user_locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------ paths

    @property
    def data_dir(self) -> Path:
        return self.app_config.data_dir_for(self.session.id)

    # ------------------------------------------------------------------ prompts

    @property
    def facilitator_system_prompt(self) -> str:
        """Assemble the workflow-specific facilitator system prompt.

        Persona + question_block + context + mechanics + depth pacing.
        Recomputed on access so an admin edit to the session OR to the
        referenced persona takes effect on the next LLM call without a
        restart.
        """
        persona_text = resolve_persona_text(
            self.session.common.ai_persona_id,
            self.app_config.personas_dir,
            fallback=get_default_persona(self.session),
        )
        return render_facilitator_prompt(
            persona=persona_text,
            question_block=build_question_block(self.session),
            context=get_context(self.session),
            facilitation_depth=self.session.common.facilitation_depth,
        )

    @property
    def facilitator_model(self) -> str:
        """Convenience: the Anthropic model name for the facilitator turn."""
        return self.session.common.facilitator_model

    # ------------------------------------------------------------------ locks

    def lock_for(self, participant_id: str) -> asyncio.Lock:
        lock = self._user_locks.get(participant_id)
        if lock is None:
            lock = asyncio.Lock()
            self._user_locks[participant_id] = lock
        return lock

    # ------------------------------------------------------------------ state I/O

    def load_or_create(
        self, participant_id: str, display_name: str
    ) -> ParticipantState:
        """Load existing participant state or create fresh state for a new one.

        On creation, also registers them in the session's `_index.json`
        so the web join endpoint and dashboard can list joined
        participants without scanning every JSON.
        """
        raw = load_participant(self.data_dir, participant_id)
        if raw is not None:
            return ParticipantState.from_dict(raw)

        state = new_participant_state(
            telegram_user_id=participant_id,
            display_name=display_name,
            session_id=self.session.id,
            question=build_question_block(self.session),
        )
        save_participant(self.data_dir, participant_id, state.to_dict())
        register_in_index(self.data_dir, participant_id, display_name)
        return state

    def save(self, state: ParticipantState) -> None:
        save_participant(self.data_dir, state.participant_id, state.to_dict())
