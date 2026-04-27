"""Tests for the state machine.

The state machine is one of two places where a silent bug would corrupt the
participant experience (the other is synthesis filtering). Cover every
transition declared in PRD section 4.3 and reject every illegal one.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from circle.state import (  # noqa: E402
    ALLOWED_TRANSITIONS,
    IllegalTransition,
    Phase,
    new_participant_state,
)


def _make_state():
    return new_participant_state(
        telegram_user_id=1,
        display_name="Ana",
        session_id="test_session",
        question="Q?",
    )


class StateMachineTests(unittest.TestCase):
    def test_initial_phase_is_not_started(self) -> None:
        state = _make_state()
        self.assertEqual(state.phase, Phase.NOT_STARTED)
        self.assertIsNone(state.started_at)
        self.assertIsNone(state.completed_at)

    def test_full_happy_path(self) -> None:
        state = _make_state()
        for next_phase in (
            Phase.AWAITING_CONSENT,
            Phase.IN_CONVERSATION,
            Phase.IN_PERMISSIONS,
            Phase.AWAITING_ADDITION,
            Phase.IN_ADDITION_PERMISSIONS,
            Phase.COMPLETE,
        ):
            state.transition_to(next_phase)
            self.assertEqual(state.phase, next_phase)
        self.assertIsNotNone(state.started_at)
        self.assertIsNotNone(state.completed_at)
        self.assertEqual(state.status, "complete")

    def test_skip_addition_path(self) -> None:
        state = _make_state()
        state.transition_to(Phase.AWAITING_CONSENT)
        state.transition_to(Phase.IN_CONVERSATION)
        state.transition_to(Phase.IN_PERMISSIONS)
        state.transition_to(Phase.AWAITING_ADDITION)
        state.transition_to(Phase.COMPLETE)
        self.assertEqual(state.phase, Phase.COMPLETE)

    def test_permissions_re_edit_from_complete(self) -> None:
        # PRD section 4.8: /permissions allows re-editing after complete.
        state = _make_state()
        for p in (
            Phase.AWAITING_CONSENT,
            Phase.IN_CONVERSATION,
            Phase.IN_PERMISSIONS,
            Phase.AWAITING_ADDITION,
            Phase.COMPLETE,
        ):
            state.transition_to(p)
        state.transition_to(Phase.IN_PERMISSIONS)
        self.assertEqual(state.phase, Phase.IN_PERMISSIONS)

    def test_restart_clears_transcript(self) -> None:
        state = _make_state()
        state.transition_to(Phase.AWAITING_CONSENT)
        state.transition_to(Phase.IN_CONVERSATION)
        from circle.state import TranscriptTurn

        state.transcript.append(
            TranscriptTurn(role="user", content="hi", timestamp="2026-01-01T00:00:00+00:00")
        )
        state.transition_to(Phase.NOT_STARTED)
        self.assertEqual(state.transcript, [])
        self.assertIsNone(state.started_at)

    def test_illegal_transitions_are_rejected(self) -> None:
        # Sample of illegal jumps from the PRD diagram.
        bad: list[tuple[Phase, Phase]] = [
            (Phase.NOT_STARTED, Phase.IN_CONVERSATION),
            (Phase.NOT_STARTED, Phase.COMPLETE),
            (Phase.AWAITING_CONSENT, Phase.IN_PERMISSIONS),
            (Phase.IN_CONVERSATION, Phase.AWAITING_ADDITION),
            (Phase.IN_PERMISSIONS, Phase.COMPLETE),
            (Phase.IN_PERMISSIONS, Phase.IN_CONVERSATION),
            (Phase.AWAITING_ADDITION, Phase.IN_PERMISSIONS),
            (Phase.COMPLETE, Phase.IN_CONVERSATION),
            (Phase.COMPLETE, Phase.AWAITING_ADDITION),
        ]
        for start, end in bad:
            with self.subTest(start=start, end=end):
                state = _make_state()
                state.phase = start
                with self.assertRaises(IllegalTransition):
                    state.transition_to(end)

    def test_every_phase_has_an_allowed_transitions_entry(self) -> None:
        for phase in Phase:
            self.assertIn(phase, ALLOWED_TRANSITIONS)

    def test_serialization_round_trip(self) -> None:
        from circle.state import (
            Addition,
            ExtractedPoint,
            ParticipantState,
            TranscriptTurn,
        )

        state = _make_state()
        state.transition_to(Phase.AWAITING_CONSENT)
        state.transition_to(Phase.IN_CONVERSATION)
        state.transcript.append(
            TranscriptTurn(
                role="user",
                content="hi",
                timestamp="2026-01-01T00:00:00+00:00",
                via="voice",
                detected_language="es",
            )
        )
        state.extracted_points.append(
            ExtractedPoint(point="I think X", permission="anonymous", index=0)
        )
        state.additions.append(Addition(content="one more thing", permission="attributed"))

        round_tripped = ParticipantState.from_dict(state.to_dict())
        self.assertEqual(round_tripped.to_dict(), state.to_dict())


if __name__ == "__main__":
    unittest.main()
