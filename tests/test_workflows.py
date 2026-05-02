"""Tests for the workflow registry, schema validation, and per-workflow
prompt assembly helpers.

Workflow types are the contract between the admin UI (which renders
forms from the schemas) and the runtime (which builds prompts from
session.workflow_data per workflow). If these go out of sync, sessions
break in subtle ways — hence the heavy validation coverage.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from circle.session import (  # noqa: E402
    CommonSettings,
    Session,
    new_session,
)
from circle.workflows import (  # noqa: E402
    UnknownWorkflowType,
    WORKFLOW_TYPES,
    WorkflowDataError,
    build_question_block,
    get_community_context,
    get_context,
    get_persona,
    get_synthesis_question,
    get_workflow,
    get_workflow_ui,
    validate_workflow_data,
)


class WorkflowRegistryTests(unittest.TestCase):
    def test_three_known_workflows_present(self) -> None:
        self.assertIn("open_discussion", WORKFLOW_TYPES)
        self.assertIn("decision_drafting", WORKFLOW_TYPES)
        self.assertIn("document_revision", WORKFLOW_TYPES)

    def test_get_workflow_known(self) -> None:
        schema = get_workflow("open_discussion")
        self.assertEqual(schema.type, "open_discussion")
        self.assertEqual(schema.processor, "synthesis")

    def test_get_workflow_unknown_raises(self) -> None:
        with self.assertRaises(UnknownWorkflowType):
            get_workflow("nonsense")

    def test_each_workflow_to_dict_round_trip_compatible(self) -> None:
        # The admin UI fetches schemas via JSON; make sure they serialize.
        for type_name, schema in WORKFLOW_TYPES.items():
            d = schema.to_dict()
            self.assertEqual(d["type"], type_name)
            self.assertIn("fields", d)
            self.assertIn("processor", d)
            self.assertIn("default_persona", d)

    def test_each_workflow_default_persona_nonempty(self) -> None:
        for schema in WORKFLOW_TYPES.values():
            self.assertTrue(schema.default_persona.strip())


class WorkflowDataValidationTests(unittest.TestCase):
    def test_open_discussion_minimum(self) -> None:
        validate_workflow_data("open_discussion", {"question": "Q?"})

    def test_open_discussion_missing_required(self) -> None:
        with self.assertRaises(WorkflowDataError):
            validate_workflow_data("open_discussion", {})

    def test_open_discussion_blank_required(self) -> None:
        with self.assertRaises(WorkflowDataError):
            validate_workflow_data("open_discussion", {"question": "   "})

    def test_open_discussion_unknown_field(self) -> None:
        with self.assertRaises(WorkflowDataError):
            validate_workflow_data(
                "open_discussion",
                {"question": "Q?", "extra": "shouldn't be here"},
            )

    def test_document_revision_full(self) -> None:
        validate_workflow_data(
            "document_revision",
            {
                "reference_document": "## Why we exist\n\n…",
                "framing": "We're working on v2.",
                "sub_questions": ["Like?", "Don't like?", "Missing?"],
                "community_context": "We value X, Y, Z.",
            },
        )

    def test_document_revision_missing_doc(self) -> None:
        with self.assertRaises(WorkflowDataError):
            validate_workflow_data(
                "document_revision",
                {"sub_questions": ["a"]},
            )

    def test_list_of_text_must_be_list(self) -> None:
        with self.assertRaises(WorkflowDataError):
            validate_workflow_data(
                "document_revision",
                {
                    "reference_document": "doc",
                    "sub_questions": "this is a string, not a list",
                },
            )

    def test_unknown_workflow_during_validation(self) -> None:
        with self.assertRaises(UnknownWorkflowType):
            validate_workflow_data("not_a_real_workflow", {})


class PerWorkflowExtractorTests(unittest.TestCase):
    def _build(
        self,
        workflow_type: str,
        workflow_data: dict,
        *,
        persona: str = "",
    ) -> Session:
        return new_session(
            id="test_x",
            title="Test",
            workflow_type=workflow_type,
            common=CommonSettings(ai_persona=persona),
            workflow_data=workflow_data,
        )

    def test_get_persona_falls_back_to_workflow_default(self) -> None:
        s = self._build("open_discussion", {"question": "Q?"})
        self.assertIn("thoughtful facilitator", get_persona(s).lower())

    def test_get_persona_uses_override(self) -> None:
        s = self._build(
            "open_discussion",
            {"question": "Q?"},
            persona="You are a goose. Probe like one.",
        )
        self.assertEqual(get_persona(s), "You are a goose. Probe like one.")

    def test_persona_per_workflow_default_is_distinct(self) -> None:
        # workflow_data is schema-validated, so each workflow gets a
        # minimum-valid dict shaped to its own schema.
        per_type_data = {
            "open_discussion": {"question": "Q?"},
            "decision_drafting": {"question": "Q?"},
            "document_revision": {"reference_document": "doc"},
        }
        defaults = {
            t: get_persona(self._build(t, per_type_data[t])) for t in WORKFLOW_TYPES
        }
        # Three distinct strings — defaults don't accidentally collide.
        self.assertEqual(len(set(defaults.values())), 3)

    def test_question_block_open_discussion(self) -> None:
        s = self._build(
            "open_discussion", {"question": "What about hot lunch?"}
        )
        self.assertEqual(build_question_block(s), "What about hot lunch?")

    def test_question_block_document_revision_includes_doc(self) -> None:
        s = self._build(
            "document_revision",
            {
                "reference_document": "## Why\n\nWe exist.",
                "framing": "Take a look.",
                "sub_questions": ["Like?", "Missing?"],
            },
        )
        block = build_question_block(s)
        self.assertIn("Take a look.", block)
        self.assertIn("## Why", block)
        self.assertIn("We exist.", block)
        self.assertIn("1. Like?", block)
        self.assertIn("2. Missing?", block)

    def test_get_context_optional(self) -> None:
        s = self._build("open_discussion", {"question": "Q?"})
        self.assertEqual(get_context(s), "")
        s2 = self._build(
            "open_discussion",
            {"question": "Q?", "context": "Some background."},
        )
        self.assertEqual(get_context(s2), "Some background.")

    def test_get_community_context_present_in_all(self) -> None:
        for type_name, data_extra in [
            ("open_discussion", {"question": "Q?"}),
            ("decision_drafting", {"question": "Q?"}),
            (
                "document_revision",
                {"reference_document": "doc"},
            ),
        ]:
            s = self._build(
                type_name, {**data_extra, "community_context": "We value X."}
            )
            self.assertEqual(get_community_context(s), "We value X.")

    def test_synthesis_question_matches_question_block(self) -> None:
        # For now they're the same; this test will fail loudly if we
        # accidentally diverge them later without thinking.
        s = self._build(
            "document_revision",
            {
                "reference_document": "doc",
                "framing": "f",
                "sub_questions": ["a"],
            },
        )
        self.assertEqual(get_synthesis_question(s), build_question_block(s))

    def test_workflow_ui_open_discussion_empty(self) -> None:
        s = self._build("open_discussion", {"question": "Q?"})
        self.assertEqual(get_workflow_ui(s), {})

    def test_workflow_ui_document_revision_has_side_panel(self) -> None:
        s = self._build(
            "document_revision",
            {
                "reference_document": "## Why\n\nWe exist.",
            },
        )
        ui = get_workflow_ui(s)
        self.assertIn("side_panel", ui)
        self.assertEqual(ui["side_panel"]["content_md"], "## Why\n\nWe exist.")
        self.assertTrue(ui["side_panel"]["title"])

    def test_workflow_ui_no_doc_means_no_side_panel(self) -> None:
        # Even though the schema declares a side_panel, if the actual
        # content is whitespace-only we shouldn't render an empty panel.
        # (Constructing an empty doc fails validation upfront — that's
        # what we're asserting here.)
        with self.assertRaises(WorkflowDataError):
            new_session(
                id="empty_doc",
                title="Empty",
                workflow_type="document_revision",
                workflow_data={"reference_document": "  "},
            )


class SessionDataclassTests(unittest.TestCase):
    def test_round_trip_to_from_dict(self) -> None:
        s = new_session(
            id="round_trip",
            title="Round trip",
            workflow_type="open_discussion",
            common=CommonSettings(ai_persona="Custom persona"),
            workflow_data={
                "question": "Q?",
                "context": "ctx",
                "community_context": "cc",
            },
        )
        d = s.to_dict()
        s2 = Session.from_dict(d)
        self.assertEqual(s2.to_dict(), s.to_dict())

    def test_invalid_session_id(self) -> None:
        from circle.session import InvalidSessionIdError

        with self.assertRaises(InvalidSessionIdError):
            new_session(
                id="Has Spaces",
                title="x",
                workflow_type="open_discussion",
                workflow_data={"question": "Q?"},
            )

    def test_unknown_workflow_in_session(self) -> None:
        with self.assertRaises(UnknownWorkflowType):
            new_session(
                id="bad",
                title="Bad",
                workflow_type="not_real",
                workflow_data={},
            )

    def test_workflow_data_validated_at_construction(self) -> None:
        with self.assertRaises(WorkflowDataError):
            new_session(
                id="bad_data",
                title="Bad data",
                workflow_type="open_discussion",
                workflow_data={},  # missing required `question`
            )


if __name__ == "__main__":
    unittest.main()
