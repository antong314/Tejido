"""Participant state machine and storage schema.

Mirrors PRD section 4.3 (state machine) and PRD section 4.5 (data model).
The state machine has an exhaustive `next_phase()` that validates allowed
transitions. Any unauthorized move raises `IllegalTransition` instead of
silently corrupting state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


class Phase(str, Enum):
    NOT_STARTED = "not_started"
    AWAITING_CONSENT = "awaiting_consent"
    IN_CONVERSATION = "in_conversation"
    IN_PERMISSIONS = "in_permissions"
    AWAITING_ADDITION = "awaiting_addition"
    IN_ADDITION_PERMISSIONS = "in_addition_permissions"
    COMPLETE = "complete"


# Maps each phase to the set of phases it may transition to. Mirrors PRD section 4.3
# verbatim, plus the `complete -> in_permissions` re-edit path from PRD section 4.8.
ALLOWED_TRANSITIONS: dict[Phase, frozenset[Phase]] = {
    Phase.NOT_STARTED: frozenset({Phase.AWAITING_CONSENT}),
    Phase.AWAITING_CONSENT: frozenset({Phase.IN_CONVERSATION, Phase.NOT_STARTED}),
    Phase.IN_CONVERSATION: frozenset({Phase.IN_PERMISSIONS, Phase.NOT_STARTED}),
    Phase.IN_PERMISSIONS: frozenset({Phase.AWAITING_ADDITION, Phase.NOT_STARTED}),
    Phase.AWAITING_ADDITION: frozenset(
        {Phase.IN_ADDITION_PERMISSIONS, Phase.COMPLETE, Phase.NOT_STARTED}
    ),
    Phase.IN_ADDITION_PERMISSIONS: frozenset({Phase.COMPLETE, Phase.NOT_STARTED}),
    Phase.COMPLETE: frozenset({Phase.IN_PERMISSIONS, Phase.NOT_STARTED}),
}


PermissionChoice = Literal["attributed", "anonymous", "private"]


class IllegalTransition(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TranscriptTurn:
    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    via: Literal["text", "voice"] = "text"
    detected_language: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.role == "user":
            out["via"] = self.via
            if self.detected_language:
                out["detected_language"] = self.detected_language
        return out

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TranscriptTurn":
        return cls(
            role=raw["role"],
            content=raw["content"],
            timestamp=raw.get("timestamp", _now_iso()),
            via=raw.get("via", "text"),
            detected_language=raw.get("detected_language"),
        )


@dataclass
class ExtractedPoint:
    point: str
    permission: PermissionChoice | None = None
    index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"point": self.point, "permission": self.permission, "index": self.index}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExtractedPoint":
        return cls(
            point=raw["point"],
            permission=raw.get("permission"),
            index=int(raw.get("index", 0)),
        )


@dataclass
class Addition:
    content: str
    permission: PermissionChoice | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"content": self.content, "permission": self.permission}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Addition":
        return cls(content=raw["content"], permission=raw.get("permission"))


@dataclass
class ParticipantState:
    """Mirrors the JSON shape in PRD section 4.5."""

    participant_id: str
    participant_name: str
    session_id: str
    question: str
    phase: Phase = Phase.NOT_STARTED
    transcript: list[TranscriptTurn] = field(default_factory=list)
    extracted_points: list[ExtractedPoint] = field(default_factory=list)
    additions: list[Addition] = field(default_factory=list)
    status: str = "in_progress"
    started_at: str | None = None
    completed_at: str | None = None
    phase_entered_at: str = field(default_factory=_now_iso)

    # Tracks which point the permissions walkthrough is currently asking about.
    # Resets when a new walkthrough starts (initial run or /permissions re-edit).
    current_point_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "participant_id": self.participant_id,
            "participant_name": self.participant_name,
            "session_id": self.session_id,
            "question": self.question,
            "phase": self.phase.value,
            "transcript": [turn.to_dict() for turn in self.transcript],
            "extracted_points": [point.to_dict() for point in self.extracted_points],
            "additions": [addition.to_dict() for addition in self.additions],
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "phase_entered_at": self.phase_entered_at,
            "current_point_index": self.current_point_index,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ParticipantState":
        return cls(
            participant_id=str(raw["participant_id"]),
            participant_name=raw["participant_name"],
            session_id=raw["session_id"],
            question=raw["question"],
            phase=Phase(raw.get("phase", Phase.NOT_STARTED.value)),
            transcript=[TranscriptTurn.from_dict(t) for t in raw.get("transcript", [])],
            extracted_points=[
                ExtractedPoint.from_dict(p) for p in raw.get("extracted_points", [])
            ],
            additions=[Addition.from_dict(a) for a in raw.get("additions", [])],
            status=raw.get("status", "in_progress"),
            started_at=raw.get("started_at"),
            completed_at=raw.get("completed_at"),
            phase_entered_at=raw.get("phase_entered_at", _now_iso()),
            current_point_index=int(raw.get("current_point_index", 0)),
        )

    def transition_to(self, new_phase: Phase) -> None:
        if new_phase not in ALLOWED_TRANSITIONS[self.phase]:
            raise IllegalTransition(
                f"Cannot transition {self.phase.value} -> {new_phase.value}"
            )
        self.phase = new_phase
        self.phase_entered_at = _now_iso()
        if new_phase == Phase.IN_CONVERSATION and self.started_at is None:
            self.started_at = _now_iso()
        if new_phase == Phase.COMPLETE:
            self.status = "complete"
            self.completed_at = _now_iso()
        if new_phase == Phase.NOT_STARTED:
            # A /restart wipes prior conversation but preserves identity.
            self.transcript = []
            self.extracted_points = []
            self.additions = []
            self.status = "in_progress"
            self.started_at = None
            self.completed_at = None
            self.current_point_index = 0


def new_participant_state(
    *, telegram_user_id: int | str, display_name: str, session_id: str, question: str
) -> ParticipantState:
    return ParticipantState(
        participant_id=str(telegram_user_id),
        participant_name=display_name,
        session_id=session_id,
        question=question,
    )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "Addition",
    "ExtractedPoint",
    "IllegalTransition",
    "ParticipantState",
    "PermissionChoice",
    "Phase",
    "TranscriptTurn",
    "new_participant_state",
]
