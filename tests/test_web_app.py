"""Tests for the FastAPI web adapter — join + state endpoints.

These exercise the full HTTP path through to the storage layer using
FastAPI's TestClient (sync, runs the app in-process), so we get a real
end-to-end check that name claiming, dupe detection, and state retrieval
work as expected. The Anthropic + Whisper clients are stubbed because
the join/state paths never call them.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from circle.config import (  # noqa: E402
    AppConfig,
    Secrets,
    SessionConfig,
    WhisperConfig,
)
from circle.runtime import BotContext  # noqa: E402
from circle.web.app import create_app  # noqa: E402


SESSION_ID = "test_session"


def _build_test_client(test: unittest.TestCase) -> tuple[TestClient, Path]:
    """Returns (client, data_dir). Tempdir cleanup is registered with `test`."""
    tmpdir = tempfile.TemporaryDirectory()
    test.addCleanup(tmpdir.cleanup)

    data_dir = Path(tmpdir.name) / "data" / SESSION_ID
    data_dir.mkdir(parents=True)

    session = SessionConfig(
        session_id=SESSION_ID,
        question="Test?",
        context="",
        community_context="",
        language="auto",
        facilitator_model="claude-sonnet-4-5",
        synthesis_model="claude-sonnet-4-5",
        whisper=WhisperConfig(),
        config_path=Path("test.yaml"),
    )
    secrets = Secrets(anthropic_api_key="test", telegram_bot_token="test")
    app_config = AppConfig(
        session=session,
        secrets=secrets,
        data_dir=data_dir,
        syntheses_dir=Path(tmpdir.name) / "syntheses",
        proposals_dir=Path(tmpdir.name) / "proposals",
    )
    context = BotContext(
        config=app_config, anthropic=MagicMock(), whisper=MagicMock()
    )
    app = create_app(context)
    client = TestClient(app)
    return client, data_dir


class JoinEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.data_dir = _build_test_client(self)

    def test_redirect_root_to_session(self) -> None:
        r = self.client.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 307)
        self.assertEqual(r.headers["location"], f"/s/{SESSION_ID}")

    def test_session_page_renders(self) -> None:
        r = self.client.get(f"/s/{SESSION_ID}")
        self.assertEqual(r.status_code, 200)
        # Either the built React app's index.html (when web/dist exists) or
        # the placeholder HTML (when it doesn't) — both contain "Tejido".
        self.assertIn("Tejido", r.text)
        # The React app reads session_id from window.location at runtime,
        # so we don't assert on it being present in the HTML.

    def test_session_page_404s_unknown_session(self) -> None:
        r = self.client.get("/s/wrong_session")
        self.assertEqual(r.status_code, 404)

    def test_join_succeeds_with_fresh_name(self) -> None:
        r = self.client.post(
            f"/api/s/{SESSION_ID}/join", json={"name": "Anton"}
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["display_name"], "Anton")
        self.assertTrue(body["participant_id"])
        # Persisted on disk.
        self.assertTrue(
            (self.data_dir / f"{body['participant_id']}.json").exists()
        )
        self.assertTrue((self.data_dir / "_index.json").exists())

    def test_join_normalizes_whitespace(self) -> None:
        r = self.client.post(
            f"/api/s/{SESSION_ID}/join", json={"name": "  Anton   K.  "}
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["display_name"], "Anton K.")

    def test_join_rejects_empty(self) -> None:
        r = self.client.post(f"/api/s/{SESSION_ID}/join", json={"name": "   "})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"]["code"], "invalid_name")

    def test_join_rejects_dupe(self) -> None:
        r1 = self.client.post(f"/api/s/{SESSION_ID}/join", json={"name": "Anton"})
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post(f"/api/s/{SESSION_ID}/join", json={"name": "anton"})
        self.assertEqual(r2.status_code, 409)
        self.assertEqual(r2.json()["detail"]["code"], "name_taken")

    def test_join_404s_unknown_session(self) -> None:
        r = self.client.post(
            "/api/s/wrong_session/join", json={"name": "Anton"}
        )
        self.assertEqual(r.status_code, 404)

    def test_join_validates_session_id_pattern(self) -> None:
        # Path constraint rejects characters outside [a-zA-Z0-9_-]
        r = self.client.post("/api/s/bad..id/join", json={"name": "Anton"})
        self.assertEqual(r.status_code, 422)


class StateEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.data_dir = _build_test_client(self)
        # Pre-create a participant via /join.
        r = self.client.post(
            f"/api/s/{SESSION_ID}/join", json={"name": "Anton"}
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.participant_id = r.json()["participant_id"]

    def test_state_returns_initial_shape(self) -> None:
        r = self.client.get(f"/api/p/{self.participant_id}/state")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["participant_id"], self.participant_id)
        self.assertEqual(body["participant_name"], "Anton")
        self.assertEqual(body["session_id"], SESSION_ID)
        self.assertEqual(body["question"], "Test?")
        # /join transitions NOT_STARTED → AWAITING_CONSENT so the
        # frontend can render the welcome card with the consent button.
        self.assertEqual(body["phase"], "awaiting_consent")
        self.assertEqual(body["transcript"], [])
        self.assertEqual(body["extracted_points"], [])
        self.assertEqual(body["additions"], [])

    def test_state_404s_unknown_participant(self) -> None:
        r = self.client.get("/api/p/does_not_exist/state")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "participant_not_found")


if __name__ == "__main__":
    unittest.main()
