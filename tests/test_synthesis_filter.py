"""Tests for the synthesis filter.

PRD section 4.5 makes the filtering invariant explicit: private content must
not reach the synthesis prompt, attributed content must be tagged with the
participant's name, anonymous content must be tagged anonymous. The filter
is the single source of truth for what reaches the model.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from circle.synthesis import filter_for_synthesis  # noqa: E402


def _completed_state(*, points, additions=None, name="Ana"):
    """Build a minimal completed-participant dict with the given points."""
    return {
        "participant_id": "1",
        "participant_name": name,
        "session_id": "s",
        "question": "Q?",
        "phase": "complete",
        "transcript": [
            {"role": "user", "content": "hi", "timestamp": "t", "via": "text"},
            {"role": "assistant", "content": "ok", "timestamp": "t"},
        ],
        "extracted_points": [
            {"point": p, "permission": perm, "index": i}
            for i, (p, perm) in enumerate(points)
        ],
        "additions": [
            {"content": c, "permission": perm} for c, perm in (additions or [])
        ],
        "status": "complete",
        "started_at": "t",
        "completed_at": "t",
    }


class SynthesisFilterTests(unittest.TestCase):
    def test_skips_incomplete_participants(self) -> None:
        raw = _completed_state(points=[("p1", "attributed")])
        raw["phase"] = "in_conversation"
        self.assertIsNone(filter_for_synthesis(raw))

    def test_drops_private_points(self) -> None:
        raw = _completed_state(
            points=[("public", "attributed"), ("secret", "private")]
        )
        result = filter_for_synthesis(raw)
        self.assertIsNotNone(result)
        joined = "\n".join(result.annotated_points)
        self.assertIn("public", joined)
        self.assertNotIn("secret", joined)

    def test_attributes_by_name(self) -> None:
        raw = _completed_state(points=[("hello", "attributed")], name="Boris")
        result = filter_for_synthesis(raw)
        self.assertIsNotNone(result)
        self.assertIn("ATTRIBUTED to Boris", result.annotated_points[0])
        self.assertIn("hello", result.annotated_points[0])

    def test_anonymous_marker(self) -> None:
        raw = _completed_state(points=[("hello", "anonymous")], name="Carolina")
        result = filter_for_synthesis(raw)
        self.assertIsNotNone(result)
        self.assertIn("ANONYMOUS", result.annotated_points[0])
        self.assertNotIn("Carolina", result.annotated_points[0])

    def test_unset_permission_is_dropped(self) -> None:
        # PRD section 3.3: "When in doubt, leave it out." A permission of None
        # means the participant never made a choice; filter must omit.
        raw = _completed_state(points=[("dangling", None)])
        result = filter_for_synthesis(raw)
        self.assertIsNone(result)

    def test_returns_none_when_everything_is_private(self) -> None:
        raw = _completed_state(
            points=[("a", "private"), ("b", "private")],
            additions=[("c", "private")],
        )
        self.assertIsNone(filter_for_synthesis(raw))

    def test_addition_attributed_and_anonymous(self) -> None:
        raw = _completed_state(
            points=[("p", "attributed")],
            additions=[("extra", "anonymous"), ("named", "attributed")],
            name="Diego",
        )
        result = filter_for_synthesis(raw)
        self.assertIsNotNone(result)
        joined = "\n".join(result.annotated_points)
        self.assertIn("(addition) ", joined)
        self.assertIn("[ANONYMOUS] (addition)", joined)
        self.assertIn("[ATTRIBUTED to Diego] (addition)", joined)

    def test_private_addition_is_filtered(self) -> None:
        raw = _completed_state(
            points=[("p", "attributed")],
            additions=[("secret addition", "private")],
        )
        result = filter_for_synthesis(raw)
        self.assertIsNotNone(result)
        joined = "\n".join(result.annotated_points)
        self.assertNotIn("secret addition", joined)


if __name__ == "__main__":
    unittest.main()
