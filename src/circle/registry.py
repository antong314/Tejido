"""Process-wide session registry — multi-session in one process.

A single registry instance is constructed at startup and shared between
the web app and (optionally) the Telegram adapter. It owns:

  * the shared whisper transcriber (one model loaded for all sessions)
  * the shared Anthropic API key (per-session AnthropicClient instances
    are cheap; one is constructed per session at first access)
  * the per-session BotContext cache, lazily populated on demand

Web routes look up by URL session id (`/s/<id>` → registry.get(id)).
The Telegram adapter, when bound to a single session via the
--telegram-session CLI flag, holds a direct reference. Admin endpoints
use list_sessions / register_or_reload / drop to manage the registry
in response to CRUD operations on the on-disk session JSONs.

The on-disk session JSONs are the source of truth. The registry is a
runtime cache keyed by session id; it can be rebuilt at any time by
re-reading config/sessions/.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable

from .anthropic_client import AnthropicClient
from .config import AppConfig
from .runtime import BotContext
from .session import (
    Session,
    list_session_ids,
    load_session,
    save_session,
)
from .whisper_client import WhisperTranscriber

logger = logging.getLogger(__name__)


class SessionRegistry:
    def __init__(
        self,
        *,
        app_config: AppConfig,
        whisper: WhisperTranscriber,
    ) -> None:
        self._app_config = app_config
        self._whisper = whisper
        self._contexts: dict[str, BotContext] = {}
        self._lock = asyncio.Lock()

    @property
    def app_config(self) -> AppConfig:
        return self._app_config

    @property
    def whisper(self) -> WhisperTranscriber:
        return self._whisper

    # ------------------------------------------------------------------ context

    async def get(self, session_id: str) -> BotContext | None:
        """Return the BotContext for a session id, lazy-loading from disk.

        Returns None if the session JSON doesn't exist. Cached after the
        first successful load so subsequent requests are immediate.
        """
        # Hot path: already cached.
        ctx = self._contexts.get(session_id)
        if ctx is not None:
            return ctx
        # Cold path: take the lock, double-check, load.
        async with self._lock:
            ctx = self._contexts.get(session_id)
            if ctx is not None:
                return ctx
            try:
                session = load_session(session_id, self._app_config.sessions_dir)
            except Exception as exc:
                logger.debug(
                    "registry.get(%s) — not found or invalid: %s",
                    session_id,
                    exc,
                )
                return None
            ctx = self._build_context(session)
            self._contexts[session_id] = ctx
            return ctx

    def _build_context(self, session: Session) -> BotContext:
        anthropic = AnthropicClient(
            api_key=self._app_config.secrets.anthropic_api_key,
            default_model=session.common.facilitator_model,
        )
        ctx = BotContext(
            session=session,
            app_config=self._app_config,
            anthropic=anthropic,
            whisper=self._whisper,
        )
        # Make sure the per-session data dir exists.
        ctx.data_dir.mkdir(parents=True, exist_ok=True)
        return ctx

    # ------------------------------------------------------------------ admin

    def list_session_ids(self) -> list[str]:
        """Disk-truth list of session ids."""
        return list_session_ids(self._app_config.sessions_dir)

    def list_sessions(self) -> list[Session]:
        """Disk-truth list of all sessions, in id order. Skips invalid."""
        out: list[Session] = []
        for sid in self.list_session_ids():
            try:
                out.append(load_session(sid, self._app_config.sessions_dir))
            except Exception:
                logger.warning("skipping invalid session JSON for id=%s", sid)
                continue
        return out

    async def register_or_reload(self, session: Session) -> BotContext:
        """Persist `session` to disk and refresh the in-memory context.

        Used by the admin POST/PATCH endpoints — after writing the JSON,
        we drop the cached context so the next access loads fresh.
        """
        save_session(session, self._app_config.sessions_dir)
        async with self._lock:
            self._contexts.pop(session.id, None)
        ctx = await self.get(session.id)
        assert ctx is not None
        return ctx

    async def drop(self, session_id: str) -> bool:
        """Forget the cached context for `session_id`. Returns True if cached.

        Does NOT delete the on-disk JSON or the per-session data dir —
        callers (e.g. the admin DELETE endpoint) handle those separately.
        """
        async with self._lock:
            return self._contexts.pop(session_id, None) is not None

    def cached_session_ids(self) -> Iterable[str]:
        return list(self._contexts.keys())
