"""Tests for circle.telegram_manager.

Mocks python-telegram-bot's ApplicationBuilder so these tests can run
without a real token or network. The lifecycle invariants we care about:
  * resume_persisted reads + binds when state file has a session id.
  * resume_persisted clears the state file if the persisted id is bad.
  * bind() to a new session stops the previous Application.
  * bind() to the same session is a no-op (no extra start/stop churn).
  * bind(None) cleanly stops without persisting anything.
  * unbind_if_session only unbinds when the id matches.
  * State file is atomic-rewritten on every transition.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from circle.telegram_manager import (  # noqa: E402
    TelegramBindingError,
    TelegramManager,
)


def _fake_application() -> MagicMock:
    """Construct a MagicMock Application with the async lifecycle methods.

    initialize / start / stop / shutdown / updater.start_polling /
    updater.stop are all awaitable in the real Application; we use
    AsyncMock so `await app.initialize()` works.
    """
    app = MagicMock(name="Application")
    app.initialize = AsyncMock()
    app.start = AsyncMock()
    app.stop = AsyncMock()
    app.shutdown = AsyncMock()
    app.updater = MagicMock()
    app.updater.start_polling = AsyncMock()
    app.updater.stop = AsyncMock()
    app.add_handler = MagicMock()
    return app


class _Builder:
    """Stand-in for ApplicationBuilder().token(...).build(). Returns a fresh
    AsyncMock-backed Application each call so we can count instantiations."""

    def __init__(self):
        self.built: list[MagicMock] = []

    def token(self, _t):
        return self

    def build(self):
        app = _fake_application()
        self.built.append(app)
        return app


class TelegramManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmpdir = Path(tmp.name)
        self.state_path = self.tmpdir / "telegram.json"

        # Registry stub: get(sid) returns a stub BotContext for known
        # ids, None otherwise.
        self.known_sessions = {"alpha", "beta"}
        registry = MagicMock()
        registry.get = AsyncMock(
            side_effect=lambda sid: MagicMock() if sid in self.known_sessions else None
        )
        self.registry = registry

        # ApplicationBuilder is constructed once per _start_locked. We
        # patch at module-load site so each call yields a fresh fake.
        self.builder = _Builder()
        self.builder_patch = patch(
            "circle.telegram_manager.ApplicationBuilder",
            return_value=self.builder,
        )
        self.builder_patch.start()
        self.addCleanup(self.builder_patch.stop)

        # Patch the handler builders (they import from circle.handlers
        # which imports the Telegram lib; the real handlers are fine in
        # process but we don't want them to do any real work).
        for mod in ("commands", "consent", "permissions", "conversation"):
            p = patch(
                f"circle.telegram_manager.{mod}.build_handlers",
                return_value=[MagicMock(), MagicMock()],
            )
            p.start()
            self.addCleanup(p.stop)

    def _make(self) -> TelegramManager:
        return TelegramManager(
            registry=self.registry,
            bot_token="fake",
            state_path=self.state_path,
        )

    # ------------------------------------------------------------------ resume

    async def test_resume_with_no_state_file_is_noop(self) -> None:
        tm = self._make()
        await tm.resume_persisted()
        self.assertIsNone(tm.bound_session_id)
        self.assertFalse(self.state_path.exists())

    async def test_resume_with_persisted_binding_starts_polling(self) -> None:
        self.state_path.write_text(json.dumps({"session_id": "alpha"}))
        tm = self._make()
        await tm.resume_persisted()
        self.assertEqual(tm.bound_session_id, "alpha")
        # One Application built, polling started.
        self.assertEqual(len(self.builder.built), 1)
        self.builder.built[0].updater.start_polling.assert_awaited_once()

    async def test_resume_clears_state_when_session_missing(self) -> None:
        self.state_path.write_text(json.dumps({"session_id": "ghost"}))
        tm = self._make()
        await tm.resume_persisted()
        self.assertIsNone(tm.bound_session_id)
        # State file should be cleared (session_id null) so it doesn't
        # keep failing on every restart.
        data = json.loads(self.state_path.read_text())
        self.assertIsNone(data["session_id"])

    # ------------------------------------------------------------------ bind

    async def test_bind_to_unknown_session_raises(self) -> None:
        tm = self._make()
        with self.assertRaises(TelegramBindingError):
            await tm.bind("ghost")
        self.assertIsNone(tm.bound_session_id)
        # Nothing was started.
        self.assertEqual(len(self.builder.built), 0)

    async def test_bind_then_rebind_stops_previous(self) -> None:
        tm = self._make()
        await tm.bind("alpha")
        await tm.bind("beta")
        # Two Applications built — alpha first, beta second.
        self.assertEqual(len(self.builder.built), 2)
        # The first one had its full shutdown sequence.
        first = self.builder.built[0]
        first.updater.stop.assert_awaited_once()
        first.stop.assert_awaited_once()
        first.shutdown.assert_awaited_once()
        self.assertEqual(tm.bound_session_id, "beta")

    async def test_bind_same_session_is_noop(self) -> None:
        tm = self._make()
        await tm.bind("alpha")
        await tm.bind("alpha")
        # Only one Application ever built.
        self.assertEqual(len(self.builder.built), 1)

    async def test_bind_none_unbinds(self) -> None:
        tm = self._make()
        await tm.bind("alpha")
        await tm.bind(None)
        self.assertIsNone(tm.bound_session_id)
        # Persisted state reflects the unbind.
        data = json.loads(self.state_path.read_text())
        self.assertIsNone(data["session_id"])

    async def test_bind_writes_state_atomically(self) -> None:
        tm = self._make()
        await tm.bind("alpha")
        data = json.loads(self.state_path.read_text())
        self.assertEqual(data["session_id"], "alpha")

    # ------------------------------------------------------------------ stop / unbind_if_session

    async def test_stop_does_not_clear_persisted_state(self) -> None:
        # Stop is called at process exit; we want the next startup to
        # auto-resume the same binding, so stop must NOT clear the file.
        tm = self._make()
        await tm.bind("alpha")
        await tm.stop()
        self.assertIsNone(tm.bound_session_id)
        data = json.loads(self.state_path.read_text())
        self.assertEqual(data["session_id"], "alpha")

    async def test_unbind_if_session_only_when_match(self) -> None:
        tm = self._make()
        await tm.bind("alpha")
        # Mismatched id — no-op.
        result = await tm.unbind_if_session("beta")
        self.assertFalse(result)
        self.assertEqual(tm.bound_session_id, "alpha")
        # Matching id — unbind + clear persisted state.
        result = await tm.unbind_if_session("alpha")
        self.assertTrue(result)
        self.assertIsNone(tm.bound_session_id)
        data = json.loads(self.state_path.read_text())
        self.assertIsNone(data["session_id"])


if __name__ == "__main__":
    unittest.main()
