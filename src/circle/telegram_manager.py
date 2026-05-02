"""Runtime owner of the (single) Telegram bot binding.

Telegram has one bot token per process and a single long-poller. There's no
URL path or other discriminator on incoming Telegram messages — chat_id is
the only identity Telegram gives us — so the process must commit to ONE
session at a time. This used to be wired via `--telegram-session <id>` at
startup and was immutable for the lifetime of the process; now it's
admin-controlled at runtime and persisted across restarts in
`config/telegram.json`.

Lifecycle:
  * `TelegramManager(...)` is constructed once at app startup.
  * `await tm.resume_persisted()` re-binds to whatever was persisted
    (or no-ops if the file is missing/empty).
  * Admin REST hits `await tm.bind(session_id | None)` to switch.
    Switching means: stop the previous python-telegram-bot Application
    cleanly, build a new one with handlers closing over the new
    BotContext, start polling.
  * `await tm.stop()` shuts down on process exit.

Concurrency: every transition is serialized by an asyncio.Lock so two
admin REST calls (or admin + auto-unbind from session delete) can't
race the python-telegram-bot Application's start/shutdown sequence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

from telegram.ext import Application, ApplicationBuilder

from .handlers import commands, consent, conversation, permissions
from .registry import SessionRegistry

logger = logging.getLogger(__name__)


class TelegramBindingError(Exception):
    """Raised when a bind request can't be satisfied (unknown session, etc.)."""


class TelegramManager:
    def __init__(
        self,
        *,
        registry: SessionRegistry,
        bot_token: str,
        state_path: Path,
    ) -> None:
        self._registry = registry
        self._bot_token = bot_token
        self._state_path = state_path
        self._app: Application | None = None
        self._bound_session_id: str | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ public

    @property
    def bound_session_id(self) -> str | None:
        """Currently-bound session id, or None if Telegram is unbound."""
        return self._bound_session_id

    @property
    def is_running(self) -> bool:
        return self._app is not None

    async def resume_persisted(self) -> None:
        """Re-bind to whatever was persisted on disk, if anything.

        Called once at process startup. If the persisted session id no
        longer exists or fails to load, we clear the persisted state so
        a stale binding doesn't keep failing on every restart.
        """
        sid = self._read_state()
        if not sid:
            logger.info("telegram: no persisted binding; starting unbound")
            return
        try:
            await self.bind(sid)
            logger.info("telegram: resumed binding to session=%s", sid)
        except TelegramBindingError as exc:
            logger.warning(
                "telegram: persisted binding session=%s no longer valid (%s); clearing",
                sid,
                exc,
            )
            self._write_state(None)

    async def bind(self, session_id: str | None) -> None:
        """Bind Telegram to `session_id`, or unbind when None.

        Re-binding to a different session tears down the current
        Application and builds a new one. Re-binding to the same
        session is a no-op (returns silently, doesn't restart polling).
        """
        async with self._lock:
            if session_id == self._bound_session_id:
                # Already bound to that session (or already unbound).
                return

            await self._stop_locked()

            if session_id is not None:
                ctx = await self._registry.get(session_id)
                if ctx is None:
                    raise TelegramBindingError(
                        f"session {session_id!r} not found"
                    )
                await self._start_locked(session_id)

            self._write_state(session_id)
            logger.info("telegram: bound to session=%s", session_id)

    async def stop(self) -> None:
        """Shutdown the Telegram poller. Used at process exit.

        Does NOT clear the persisted binding — on next startup,
        `resume_persisted` will re-bind to the same session.
        """
        async with self._lock:
            await self._stop_locked()

    async def unbind_if_session(self, session_id: str) -> bool:
        """If currently bound to `session_id`, unbind. Returns True if it was.

        Used by the admin DELETE-session endpoint so the binding doesn't
        end up pointing at a session that no longer exists.
        """
        async with self._lock:
            if self._bound_session_id != session_id:
                return False
            await self._stop_locked()
            self._write_state(None)
            logger.info(
                "telegram: auto-unbound because session=%s was deleted",
                session_id,
            )
            return True

    # ------------------------------------------------------------------ internals

    async def _start_locked(self, session_id: str) -> None:
        """Build, initialize, and start polling. Caller holds self._lock."""
        ctx = await self._registry.get(session_id)
        if ctx is None:  # defensive — checked by caller
            raise TelegramBindingError(f"session {session_id!r} not found")

        app = ApplicationBuilder().token(self._bot_token).build()
        for handler in commands.build_handlers(ctx):
            app.add_handler(handler)
        for handler in consent.build_handlers(ctx):
            app.add_handler(handler)
        for handler in permissions.build_handlers(ctx):
            app.add_handler(handler)
        for handler in conversation.build_handlers(ctx):
            app.add_handler(handler)

        await app.initialize()
        await app.start()
        await app.updater.start_polling()

        self._app = app
        self._bound_session_id = session_id

    async def _stop_locked(self) -> None:
        """Drain and shut down the Application. Caller holds self._lock."""
        app = self._app
        if app is None:
            return
        try:
            if app.updater is not None:
                await app.updater.stop()
            await app.stop()
            await app.shutdown()
        except Exception:
            # We don't want a shutdown error to wedge the manager —
            # subsequent bind calls would fail forever otherwise.
            logger.exception("telegram: error during shutdown; clearing anyway")
        finally:
            self._app = None
            self._bound_session_id = None

    # ------------------------------------------------------------------ persistence

    def _read_state(self) -> str | None:
        if not self._state_path.exists():
            return None
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning(
                "telegram: state file %s couldn't be parsed; ignoring",
                self._state_path,
            )
            return None
        sid = data.get("session_id")
        if not isinstance(sid, str) or not sid.strip():
            return None
        return sid.strip()

    def _write_state(self, session_id: str | None) -> None:
        """Atomic write of {"session_id": ...} to the state file."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"session_id": session_id}, ensure_ascii=False, indent=2
        )
        fd, tmp_name = tempfile.mkstemp(
            prefix=".telegram.", suffix=".json.tmp", dir=self._state_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as h:
                h.write(payload)
                h.flush()
                os.fsync(h.fileno())
            os.replace(tmp_name, self._state_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise


__all__ = ["TelegramBindingError", "TelegramManager"]
