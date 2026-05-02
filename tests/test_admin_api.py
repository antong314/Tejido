"""Tests for the admin REST endpoints under /api/admin/.

The admin API is the contract the React admin UI talks to. These tests
cover the CRUD shape, validation, and error paths; the React UI
itself is not tested here.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from circle.config import AppConfig, Secrets  # noqa: E402
from circle.registry import SessionRegistry  # noqa: E402
from circle.web.app import create_app  # noqa: E402


def _build_client(
    test: unittest.TestCase,
    *,
    telegram=None,
) -> tuple[TestClient, AppConfig]:
    tmpdir = tempfile.TemporaryDirectory()
    test.addCleanup(tmpdir.cleanup)
    root = Path(tmpdir.name)

    sessions_dir = root / "config" / "sessions"
    sessions_dir.mkdir(parents=True)
    workflows_dir = root / "config" / "workflows"
    workflows_dir.mkdir(parents=True)

    secrets = Secrets(anthropic_api_key="t", telegram_bot_token="t")
    app_config = AppConfig(
        secrets=secrets,
        sessions_dir=sessions_dir,
        workflows_dir=workflows_dir,
        data_dir_base=root / "data",
        syntheses_dir=root / "syntheses",
        proposals_dir=root / "proposals",
        revisions_dir=root / "revisions",
    )
    app_config.data_dir_base.mkdir(parents=True, exist_ok=True)
    app_config.syntheses_dir.mkdir(parents=True, exist_ok=True)
    app_config.proposals_dir.mkdir(parents=True, exist_ok=True)
    app_config.revisions_dir.mkdir(parents=True, exist_ok=True)

    registry = SessionRegistry(app_config=app_config, whisper=MagicMock())
    app = create_app(registry=registry, telegram=telegram)
    return TestClient(app), app_config


class WorkflowTypesTests(unittest.TestCase):
    def test_lists_three_workflow_types(self) -> None:
        client, _ = _build_client(self)
        r = client.get("/api/admin/workflow-types")
        self.assertEqual(r.status_code, 200, r.text)
        types = {entry["type"] for entry in r.json()}
        self.assertEqual(
            types,
            {"open_discussion", "decision_drafting", "document_revision"},
        )

    def test_each_entry_has_fields_array(self) -> None:
        client, _ = _build_client(self)
        for entry in client.get("/api/admin/workflow-types").json():
            self.assertIsInstance(entry["fields"], list)
            self.assertTrue(entry["default_task_framing"])
            self.assertTrue(entry["default_output_template"])
            self.assertTrue(entry["default_mechanics"])
            # Overrides start empty since no JSON file exists yet.
            self.assertEqual(entry["task_framing_override"], "")
            self.assertEqual(entry["output_template_override"], "")
            self.assertEqual(entry["mechanics_override"], "")
            self.assertIn("processor", entry)


class SessionCRUDTests(unittest.TestCase):
    def test_list_empty(self) -> None:
        client, _ = _build_client(self)
        r = client.get("/api/admin/sessions")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_create_open_discussion(self) -> None:
        client, _ = _build_client(self)
        r = client.post(
            "/api/admin/sessions",
            json={
                "id": "test_open",
                "title": "Test Open",
                "workflow_type": "open_discussion",
                "common": {},
                "whisper": {},
                "workflow_data": {"question": "What's up?"},
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["id"], "test_open")
        self.assertEqual(body["workflow_type"], "open_discussion")

    def test_create_then_list(self) -> None:
        client, _ = _build_client(self)
        client.post(
            "/api/admin/sessions",
            json={
                "id": "alpha",
                "title": "A",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        client.post(
            "/api/admin/sessions",
            json={
                "id": "beta",
                "title": "B",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        r = client.get("/api/admin/sessions")
        ids = [s["id"] for s in r.json()]
        self.assertEqual(sorted(ids), ["alpha", "beta"])

    def test_create_409_on_dupe_id(self) -> None:
        client, _ = _build_client(self)
        for code in (200, 409):
            r = client.post(
                "/api/admin/sessions",
                json={
                    "id": "dupe",
                    "title": "X",
                    "workflow_type": "open_discussion",
                    "workflow_data": {"question": "Q?"},
                },
            )
            self.assertEqual(r.status_code, code, r.text)

    def test_create_400_on_invalid_id(self) -> None:
        client, _ = _build_client(self)
        r = client.post(
            "/api/admin/sessions",
            json={
                "id": "Has Spaces",
                "title": "X",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_create_400_on_invalid_workflow_data(self) -> None:
        client, _ = _build_client(self)
        # document_revision requires reference_document
        r = client.post(
            "/api/admin/sessions",
            json={
                "id": "doc_rev",
                "title": "Doc",
                "workflow_type": "document_revision",
                "workflow_data": {"sub_questions": ["a"]},
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_create_400_on_unknown_workflow_type(self) -> None:
        client, _ = _build_client(self)
        r = client.post(
            "/api/admin/sessions",
            json={
                "id": "x",
                "title": "X",
                "workflow_type": "not_real",
                "workflow_data": {},
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_get_404_on_unknown(self) -> None:
        client, _ = _build_client(self)
        r = client.get("/api/admin/sessions/nope")
        self.assertEqual(r.status_code, 404)

    def test_patch_updates_title(self) -> None:
        client, _ = _build_client(self)
        client.post(
            "/api/admin/sessions",
            json={
                "id": "patch_me",
                "title": "old",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        r = client.patch(
            "/api/admin/sessions/patch_me", json={"title": "new"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["title"], "new")
        # Other fields preserved.
        self.assertEqual(r.json()["workflow_data"]["question"], "Q?")

    def test_patch_400_on_bad_workflow_data(self) -> None:
        client, _ = _build_client(self)
        client.post(
            "/api/admin/sessions",
            json={
                "id": "patch_bad",
                "title": "x",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        # blank required field
        r = client.patch(
            "/api/admin/sessions/patch_bad",
            json={"workflow_data": {"question": ""}},
        )
        self.assertEqual(r.status_code, 400)

    def test_delete_then_404(self) -> None:
        client, _ = _build_client(self)
        client.post(
            "/api/admin/sessions",
            json={
                "id": "to_delete",
                "title": "x",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        r = client.delete("/api/admin/sessions/to_delete")
        self.assertEqual(r.status_code, 200, r.text)
        r2 = client.get("/api/admin/sessions/to_delete")
        self.assertEqual(r2.status_code, 404)
        # Idempotent: second delete returns 404.
        r3 = client.delete("/api/admin/sessions/to_delete")
        self.assertEqual(r3.status_code, 404)


class RunProcessorMismatchTests(unittest.TestCase):
    def test_400_when_processor_doesnt_match_workflow(self) -> None:
        client, _ = _build_client(self)
        client.post(
            "/api/admin/sessions",
            json={
                "id": "open_only",
                "title": "x",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        # open_discussion's processor is synthesis; ask for proposal:
        r = client.post("/api/admin/sessions/open_only/run/proposal")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"]["code"], "processor_mismatch")


class ParticipantsAdminTests(unittest.TestCase):
    """The admin endpoints that expose participants + their transcripts."""

    def _make_session_and_participant(
        self, client: TestClient, session_id: str = "smoke"
    ) -> str:
        client.post(
            "/api/admin/sessions",
            json={
                "id": session_id,
                "title": "x",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        # Use the participant-facing /join to materialize an actual
        # ParticipantState file on disk; the admin endpoint reads from
        # the same files.
        r = client.post(
            f"/api/s/{session_id}/join", json={"name": "Anton"}
        )
        assert r.status_code == 200, r.text
        return r.json()["participant_id"]

    def test_404_when_session_missing(self) -> None:
        client, _ = _build_client(self)
        r = client.get("/api/admin/sessions/nope/participants")
        self.assertEqual(r.status_code, 404)

    def test_empty_when_nobody_joined(self) -> None:
        client, _ = _build_client(self)
        client.post(
            "/api/admin/sessions",
            json={
                "id": "empty_session",
                "title": "x",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        r = client.get("/api/admin/sessions/empty_session/participants")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])

    def test_lists_after_join(self) -> None:
        client, _ = _build_client(self)
        pid = self._make_session_and_participant(client)
        r = client.get("/api/admin/sessions/smoke/participants")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body), 1)
        entry = body[0]
        self.assertEqual(entry["participant_id"], pid)
        self.assertEqual(entry["participant_name"], "Anton")
        # /join transitions NOT_STARTED → AWAITING_CONSENT
        self.assertEqual(entry["phase"], "awaiting_consent")
        self.assertEqual(entry["num_turns"], 0)
        self.assertEqual(entry["num_extracted_points"], 0)
        self.assertEqual(entry["num_additions"], 0)

    def test_detail_404_when_session_missing(self) -> None:
        client, _ = _build_client(self)
        r = client.get("/api/admin/sessions/nope/participants/whatever")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "session_not_found")

    def test_detail_404_when_participant_missing(self) -> None:
        client, _ = _build_client(self)
        client.post(
            "/api/admin/sessions",
            json={
                "id": "with_session",
                "title": "x",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        r = client.get(
            "/api/admin/sessions/with_session/participants/no_such_pid"
        )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "participant_not_found")

    def test_detail_returns_full_record(self) -> None:
        client, _ = _build_client(self)
        pid = self._make_session_and_participant(client)
        r = client.get(f"/api/admin/sessions/smoke/participants/{pid}")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["participant_id"], pid)
        self.assertEqual(body["participant_name"], "Anton")
        self.assertEqual(body["session_id"], "smoke")
        self.assertEqual(body["phase"], "awaiting_consent")
        self.assertEqual(body["transcript"], [])
        self.assertEqual(body["extracted_points"], [])
        self.assertEqual(body["additions"], [])


class OutputListingTests(unittest.TestCase):
    def test_outputs_empty_when_none_run(self) -> None:
        client, _ = _build_client(self)
        client.post(
            "/api/admin/sessions",
            json={
                "id": "no_outputs",
                "title": "x",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        r = client.get("/api/admin/sessions/no_outputs/outputs")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_outputs_lists_by_filename_pattern(self) -> None:
        client, app_config = _build_client(self)
        client.post(
            "/api/admin/sessions",
            json={
                "id": "with_outputs",
                "title": "x",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        # Drop a pretend synthesis output in the right shape.
        f = app_config.syntheses_dir / "synthesis_with_outputs_20260501.md"
        f.write_text("# fake synthesis")
        r = client.get("/api/admin/sessions/with_outputs/outputs")
        self.assertEqual(r.status_code, 200, r.text)
        names = [e["filename"] for e in r.json()]
        self.assertIn("synthesis_with_outputs_20260501.md", names)


class WorkflowTypeOverridesTests(unittest.TestCase):
    """The admin can edit task_framing, output_template, and mechanics
    per workflow type. Empty string clears the override (revert to default)."""

    def test_get_one_returns_defaults_when_no_override(self) -> None:
        client, _ = _build_client(self)
        r = client.get("/api/admin/workflow-types/open_discussion")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["default_task_framing"])
        self.assertTrue(body["default_output_template"])
        self.assertEqual(body["task_framing_override"], "")
        self.assertEqual(body["output_template_override"], "")
        self.assertEqual(body["mechanics_override"], "")

    def test_get_404_on_unknown_type(self) -> None:
        client, _ = _build_client(self)
        r = client.get("/api/admin/workflow-types/not_a_real_workflow")
        self.assertEqual(r.status_code, 404)

    def test_patch_writes_overrides_and_round_trips(self) -> None:
        client, _ = _build_client(self)
        r = client.patch(
            "/api/admin/workflow-types/open_discussion",
            json={
                "task_framing": "You are a sharp researcher.",
                "mechanics_override": "Probe quickly.",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(
            body["task_framing_override"], "You are a sharp researcher."
        )
        self.assertEqual(body["mechanics_override"], "Probe quickly.")
        # Output template unchanged.
        self.assertEqual(body["output_template_override"], "")
        # Subsequent GET returns the same.
        r2 = client.get("/api/admin/workflow-types/open_discussion")
        self.assertEqual(
            r2.json()["task_framing_override"],
            "You are a sharp researcher.",
        )

    def test_patch_partial_update_preserves_other_fields(self) -> None:
        client, _ = _build_client(self)
        client.patch(
            "/api/admin/workflow-types/open_discussion",
            json={"task_framing": "First."},
        )
        client.patch(
            "/api/admin/workflow-types/open_discussion",
            json={"output_template_override": None, "mechanics_override": "Second."},
        )
        r = client.get("/api/admin/workflow-types/open_discussion")
        self.assertEqual(r.json()["task_framing_override"], "First.")
        self.assertEqual(r.json()["mechanics_override"], "Second.")

    def test_patch_empty_string_clears_override(self) -> None:
        client, _ = _build_client(self)
        # Set then clear.
        client.patch(
            "/api/admin/workflow-types/open_discussion",
            json={"task_framing": "Custom"},
        )
        r = client.patch(
            "/api/admin/workflow-types/open_discussion",
            json={"task_framing": ""},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["task_framing_override"], "")

    def test_patch_404_on_unknown_type(self) -> None:
        client, _ = _build_client(self)
        r = client.patch(
            "/api/admin/workflow-types/not_a_real_workflow",
            json={"task_framing": "x"},
        )
        self.assertEqual(r.status_code, 404)

    def test_patch_actually_changes_resolved_runtime_value(self) -> None:
        # End-to-end: PATCH the override, then call the resolver and
        # confirm it returns the new text instead of the default.
        from circle.workflow_overrides import (
            get_mechanics,
            get_output_template,
            get_task_framing,
        )

        client, app_config = _build_client(self)
        client.patch(
            "/api/admin/workflow-types/open_discussion",
            json={
                "task_framing": "Override A.",
                "output_template": "Override B.",
                "mechanics_override": "Override C.",
            },
        )
        self.assertEqual(
            get_task_framing("open_discussion", app_config.workflows_dir),
            "Override A.",
        )
        self.assertEqual(
            get_output_template("open_discussion", app_config.workflows_dir),
            "Override B.",
        )
        self.assertEqual(
            get_mechanics("open_discussion", app_config.workflows_dir),
            "Override C.",
        )


class TelegramAdminTests(unittest.TestCase):
    """REST surface around the Telegram binding.

    Uses a stub TelegramManager (MagicMock) since the manager itself is
    covered in test_telegram_manager.py — we just need to confirm the
    REST routes call through correctly.
    """

    def _make_telegram_stub(self, bound: str | None = None) -> MagicMock:
        from unittest.mock import AsyncMock

        tm = MagicMock()
        tm.bound_session_id = bound
        tm.bind = AsyncMock()
        tm.unbind_if_session = AsyncMock(return_value=False)
        return tm

    def test_get_status_when_telegram_unavailable(self) -> None:
        # No telegram passed → admin endpoint reports available: false.
        client, _ = _build_client(self, telegram=None)
        r = client.get("/api/admin/telegram")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(
            r.json(),
            {"available": False, "bound_session_id": None},
        )

    def test_get_status_when_unbound(self) -> None:
        tm = self._make_telegram_stub(bound=None)
        client, _ = _build_client(self, telegram=tm)
        r = client.get("/api/admin/telegram")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(
            r.json(), {"available": True, "bound_session_id": None}
        )

    def test_get_status_when_bound(self) -> None:
        tm = self._make_telegram_stub(bound="alpha")
        client, _ = _build_client(self, telegram=tm)
        r = client.get("/api/admin/telegram")
        self.assertEqual(r.json()["bound_session_id"], "alpha")

    def test_put_503_when_telegram_unavailable(self) -> None:
        client, _ = _build_client(self, telegram=None)
        r = client.put("/api/admin/telegram", json={"session_id": "alpha"})
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["detail"]["code"], "telegram_not_available")

    def test_put_calls_bind_with_session_id(self) -> None:
        tm = self._make_telegram_stub(bound=None)

        # bind() updates bound_session_id when called.
        async def fake_bind(sid):
            tm.bound_session_id = sid

        tm.bind.side_effect = fake_bind
        client, _ = _build_client(self, telegram=tm)
        r = client.put("/api/admin/telegram", json={"session_id": "beta"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["bound_session_id"], "beta")
        tm.bind.assert_awaited_once_with("beta")

    def test_put_with_null_session_unbinds(self) -> None:
        tm = self._make_telegram_stub(bound="alpha")

        async def fake_bind(sid):
            tm.bound_session_id = sid

        tm.bind.side_effect = fake_bind
        client, _ = _build_client(self, telegram=tm)
        r = client.put("/api/admin/telegram", json={"session_id": None})
        self.assertEqual(r.status_code, 200, r.text)
        tm.bind.assert_awaited_once_with(None)

    def test_put_400_when_bind_raises(self) -> None:
        from circle.telegram_manager import TelegramBindingError

        tm = self._make_telegram_stub(bound=None)
        tm.bind.side_effect = TelegramBindingError("session 'ghost' not found")
        client, _ = _build_client(self, telegram=tm)
        r = client.put("/api/admin/telegram", json={"session_id": "ghost"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"]["code"], "telegram_bind_failed")

    def test_delete_session_auto_unbinds_telegram(self) -> None:
        tm = self._make_telegram_stub(bound="to_delete")
        tm.unbind_if_session = AsyncMock(return_value=True)
        client, _ = _build_client(self, telegram=tm)
        client.post(
            "/api/admin/sessions",
            json={
                "id": "to_delete",
                "title": "x",
                "workflow_type": "open_discussion",
                "workflow_data": {"question": "Q?"},
            },
        )
        r = client.delete("/api/admin/sessions/to_delete")
        self.assertEqual(r.status_code, 200, r.text)
        tm.unbind_if_session.assert_awaited_once_with("to_delete")


class FacilitatorPromptDepthTests(unittest.TestCase):
    """The depth slider must surface in the rendered facilitator prompt."""

    def test_depth_blocks_distinct(self) -> None:
        from circle.prompts import DEPTH_BLOCKS, render_facilitator_prompt

        for depth in ("minimal", "medium", "deep"):
            out = render_facilitator_prompt(
                question_block="Q?", facilitation_depth=depth
            )
            self.assertIn(DEPTH_BLOCKS[depth], out)

    def test_unknown_depth_falls_back_to_medium(self) -> None:
        from circle.prompts import DEPTH_BLOCKS, render_facilitator_prompt

        out = render_facilitator_prompt(
            question_block="Q?", facilitation_depth="forever"
        )
        self.assertIn(DEPTH_BLOCKS["medium"], out)


if __name__ == "__main__":
    unittest.main()
