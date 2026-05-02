"""Tests for the web pieces beyond join/state: render_action, SSEHub,
dispatch, and the /message and /callback endpoints.

The /events SSE endpoint is exercised manually via curl in the smoke
test; testing streaming responses through TestClient is awkward and
provides little value over the unit tests of the SSEHub itself.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from circle.config import AppConfig, Secrets  # noqa: E402
from circle.registry import SessionRegistry  # noqa: E402
from circle.session import (  # noqa: E402
    CommonSettings,
    WhisperSettings,
    new_session,
    save_session,
)
from circle.transport import (  # noqa: E402
    Choice,
    ResolveChoice,
    SendChoicePrompt,
    SendText,
    TypingIndicator,
)
from circle.web.app import create_app  # noqa: E402
from circle.web.dispatch import (  # noqa: E402
    InvalidCallbackError,
    dispatch_callback,
)
from circle.web.render_action import action_to_json  # noqa: E402
from circle.web.sse import SSEHub  # noqa: E402


SESSION_ID = "test_session"


class RenderActionTests(unittest.TestCase):
    def test_send_text(self) -> None:
        self.assertEqual(
            action_to_json(SendText("hello", parse_mode="html")),
            {"type": "text", "text": "hello", "parse_mode": "html"},
        )

    def test_send_choice_prompt(self) -> None:
        action = SendChoicePrompt(
            text="pick",
            parse_mode="plain",
            choices=(
                Choice(label="A", callback_data="cb:a"),
                Choice(label="B", callback_data="cb:b"),
            ),
        )
        self.assertEqual(
            action_to_json(action),
            {
                "type": "choice_prompt",
                "text": "pick",
                "parse_mode": "plain",
                "choices": [
                    {"label": "A", "callback_data": "cb:a"},
                    {"label": "B", "callback_data": "cb:b"},
                ],
            },
        )

    def test_resolve_choice(self) -> None:
        self.assertEqual(
            action_to_json(ResolveChoice(text="✓ A", parse_mode="html")),
            {"type": "resolve_choice", "text": "✓ A", "parse_mode": "html"},
        )

    def test_resolve_choice_no_text(self) -> None:
        self.assertEqual(
            action_to_json(ResolveChoice()),
            {"type": "resolve_choice", "text": None, "parse_mode": "plain"},
        )

    def test_typing(self) -> None:
        self.assertEqual(action_to_json(TypingIndicator()), {"type": "typing"})


class SSEHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_subscribe_and_broadcast(self) -> None:
        hub = SSEHub()
        async with hub.subscribe("p1") as q:
            await hub.broadcast("p1", {"type": "text", "text": "hi"})
            event = await asyncio.wait_for(q.get(), timeout=0.5)
            self.assertEqual(event, {"type": "text", "text": "hi"})

    async def test_subscriber_count_tracks(self) -> None:
        hub = SSEHub()
        self.assertEqual(hub.subscriber_count("p1"), 0)
        async with hub.subscribe("p1"):
            self.assertEqual(hub.subscriber_count("p1"), 1)
            async with hub.subscribe("p1"):
                self.assertEqual(hub.subscriber_count("p1"), 2)
            self.assertEqual(hub.subscriber_count("p1"), 1)
        self.assertEqual(hub.subscriber_count("p1"), 0)

    async def test_broadcast_per_participant(self) -> None:
        hub = SSEHub()
        async with hub.subscribe("alice") as qa, hub.subscribe("bob") as qb:
            await hub.broadcast("alice", {"x": 1})
            ea = await asyncio.wait_for(qa.get(), timeout=0.5)
            self.assertEqual(ea, {"x": 1})
            self.assertTrue(qb.empty())

    async def test_broadcast_with_no_subscribers_is_noop(self) -> None:
        hub = SSEHub()
        await hub.broadcast("ghost", {"x": 1})  # should not raise


class _StubAnthropic:
    """Anthropic client double — single canned response per call."""

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def complete(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        if not self._responses:
            return ""
        return self._responses.pop(0)


def _build_test_client(
    test: unittest.TestCase, anthropic_responses: tuple[str, ...] = ()
) -> tuple[TestClient, Path, _StubAnthropic]:
    tmpdir = tempfile.TemporaryDirectory()
    test.addCleanup(tmpdir.cleanup)
    root = Path(tmpdir.name)

    sessions_dir = root / "config" / "sessions"
    data_dir_base = root / "data"
    sessions_dir.mkdir(parents=True)
    data_dir_base.mkdir(parents=True)

    secrets = Secrets(anthropic_api_key="test", telegram_bot_token="test")
    app_config = AppConfig(
        secrets=secrets,
        sessions_dir=sessions_dir,
        data_dir_base=data_dir_base,
        syntheses_dir=root / "syntheses",
        proposals_dir=root / "proposals",
        revisions_dir=root / "revisions",
    )

    session = new_session(
        id=SESSION_ID,
        title="Test session",
        workflow_type="open_discussion",
        common=CommonSettings(),
        whisper=WhisperSettings(),
        workflow_data={"question": "Test?"},
    )
    save_session(session, sessions_dir)

    anthropic = _StubAnthropic(*anthropic_responses)
    registry = SessionRegistry(app_config=app_config, whisper=MagicMock())

    # Pre-seed the registry's BotContext with our stub Anthropic so the
    # controller routes don't try to make real API calls.
    async def _seed():
        ctx = await registry.get(SESSION_ID)
        assert ctx is not None
        ctx.anthropic = anthropic  # type: ignore[assignment]
    asyncio.run(_seed())

    app = create_app(registry=registry)
    client = TestClient(app)
    return client, app_config.data_dir_for(SESSION_ID), anthropic


def _create_participant(client: TestClient, name: str = "Anton") -> tuple[str, str]:
    r = client.post(f"/api/s/{SESSION_ID}/join", json={"name": name})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["participant_id"], body["display_name"]


class MessageEndpointTests(unittest.TestCase):
    def test_404s_unknown_participant(self) -> None:
        client, _, _ = _build_test_client(self)
        r = client.post(
            f"/api/s/{SESSION_ID}/p/does_not_exist/message",
            json={"text": "hi"},
        )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "participant_not_found")

    def test_message_in_awaiting_consent_phase_emits_nudge(self) -> None:
        # After /join, phase is AWAITING_CONSENT; a free-text submission
        # at this point gets nudged toward the button.
        client, _, _ = _build_test_client(self)
        pid, _ = _create_participant(client)
        r = client.post(
            f"/api/s/{SESSION_ID}/p/{pid}/message", json={"text": "hi"}
        )
        self.assertEqual(r.status_code, 200)
        s = client.get(f"/api/s/{SESSION_ID}/p/{pid}/state").json()
        self.assertEqual(s["phase"], "awaiting_consent")
        self.assertEqual(s["transcript"], [])


class CallbackEndpointTests(unittest.TestCase):
    def test_404s_unknown_participant(self) -> None:
        client, _, _ = _build_test_client(self)
        r = client.post(
            f"/api/s/{SESSION_ID}/p/does_not_exist/callback",
            json={"callback_data": "consent:ready"},
        )
        self.assertEqual(r.status_code, 404)

    def test_400s_invalid_callback_data(self) -> None:
        client, _, _ = _build_test_client(self)
        pid, _ = _create_participant(client)
        r = client.post(
            f"/api/s/{SESSION_ID}/p/{pid}/callback",
            json={"callback_data": "bogus:thing"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"]["code"], "invalid_callback")


class DispatchTests(unittest.TestCase):
    def test_unknown_prefix_raises(self) -> None:
        with self.assertRaises(InvalidCallbackError):
            dispatch_callback(
                callback_data="bogus:thing",
                participant_id="p",
                display_name="P",
                session=MagicMock(),
            )

    def test_perm_malformed_index_raises(self) -> None:
        with self.assertRaises(InvalidCallbackError):
            dispatch_callback(
                callback_data="perm:notanint:attributed",
                participant_id="p",
                display_name="P",
                session=MagicMock(),
            )

    def test_perm_unknown_choice_raises(self) -> None:
        with self.assertRaises(InvalidCallbackError):
            dispatch_callback(
                callback_data="perm:0:unknown",
                participant_id="p",
                display_name="P",
                session=MagicMock(),
            )

    def test_add_unknown_choice_raises(self) -> None:
        with self.assertRaises(InvalidCallbackError):
            dispatch_callback(
                callback_data="add:maybe",
                participant_id="p",
                display_name="P",
                session=MagicMock(),
            )

    def test_cmd_unknown_command_raises(self) -> None:
        with self.assertRaises(InvalidCallbackError):
            dispatch_callback(
                callback_data="cmd:unknown",
                participant_id="p",
                display_name="P",
                session=MagicMock(),
            )

    def test_consent_returns_iterator(self) -> None:
        result = dispatch_callback(
            callback_data="consent:ready",
            participant_id="p",
            display_name="P",
            session=MagicMock(),
        )
        self.assertTrue(hasattr(result, "__aiter__"))


class StartFlowEndToEndTests(unittest.TestCase):
    """Drive a real /callback through the controller using a stub Anthropic.

    Goes /join -> consent:ready -> verifies the opening turn arrived as a
    transcript turn.
    """

    def test_consent_callback_drives_opening_turn(self) -> None:
        client, _, anthropic = _build_test_client(
            self, anthropic_responses=("Welcome — what's on your mind?",)
        )
        pid, _ = _create_participant(client)

        r = client.post(
            f"/api/s/{SESSION_ID}/p/{pid}/callback",
            json={"callback_data": "consent:ready"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        s = client.get(f"/api/s/{SESSION_ID}/p/{pid}/state").json()
        self.assertEqual(s["phase"], "in_conversation")
        roles = [t["role"] for t in s["transcript"]]
        self.assertEqual(roles, ["assistant"])
        self.assertIn("Welcome", s["transcript"][0]["content"])


if __name__ == "__main__":
    unittest.main()
