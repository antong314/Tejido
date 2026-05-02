"""Tests for the FastAPI web adapter — join + state endpoints.

Multi-session now: every per-participant route is scoped under a
session id. The TestClient drives the same routes through a stub
SessionRegistry holding a single session.
"""

from __future__ import annotations

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
from circle.web.app import create_app  # noqa: E402


SESSION_ID = "test_session"


def _build_test_client(test: unittest.TestCase) -> tuple[TestClient, Path]:
    """Returns (client, data_dir). Tempdir cleanup is registered with `test`."""
    tmpdir = tempfile.TemporaryDirectory()
    test.addCleanup(tmpdir.cleanup)
    root = Path(tmpdir.name)

    sessions_dir = root / "config" / "sessions"
    data_dir_base = root / "data"
    syntheses_dir = root / "syntheses"
    proposals_dir = root / "proposals"
    revisions_dir = root / "revisions"
    sessions_dir.mkdir(parents=True)
    data_dir_base.mkdir(parents=True)
    syntheses_dir.mkdir(parents=True)
    proposals_dir.mkdir(parents=True)
    revisions_dir.mkdir(parents=True)

    secrets = Secrets(anthropic_api_key="test", telegram_bot_token="test")
    app_config = AppConfig(
        secrets=secrets,
        sessions_dir=sessions_dir,
        data_dir_base=data_dir_base,
        syntheses_dir=syntheses_dir,
        proposals_dir=proposals_dir,
        revisions_dir=revisions_dir,
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

    registry = SessionRegistry(app_config=app_config, whisper=MagicMock())
    app = create_app(registry=registry)
    client = TestClient(app)

    data_dir = app_config.data_dir_for(SESSION_ID)
    data_dir.mkdir(parents=True, exist_ok=True)
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
        self.assertIn("Tejido", r.text)

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
        r = self.client.post("/api/s/bad..id/join", json={"name": "Anton"})
        self.assertEqual(r.status_code, 422)


class StateEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.data_dir = _build_test_client(self)
        r = self.client.post(
            f"/api/s/{SESSION_ID}/join", json={"name": "Anton"}
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.participant_id = r.json()["participant_id"]

    def test_state_returns_initial_shape(self) -> None:
        r = self.client.get(
            f"/api/s/{SESSION_ID}/p/{self.participant_id}/state"
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["participant_id"], self.participant_id)
        self.assertEqual(body["participant_name"], "Anton")
        self.assertEqual(body["session_id"], SESSION_ID)
        # /join transitions NOT_STARTED → AWAITING_CONSENT.
        self.assertEqual(body["phase"], "awaiting_consent")
        self.assertEqual(body["transcript"], [])
        self.assertEqual(body["extracted_points"], [])
        self.assertEqual(body["additions"], [])
        # Workflow type + UI hints surface to the frontend.
        self.assertEqual(body["workflow_type"], "open_discussion")
        self.assertEqual(body["workflow_ui"], {})

    def test_state_404s_unknown_participant(self) -> None:
        r = self.client.get(f"/api/s/{SESSION_ID}/p/does_not_exist/state")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "participant_not_found")

    def test_state_404s_unknown_session(self) -> None:
        r = self.client.get(f"/api/s/wrong/p/{self.participant_id}/state")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
