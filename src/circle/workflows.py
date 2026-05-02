"""Workflow types — the schemas that drive the admin UI and the per-workflow
prompt assembly.

Each workflow is a recipe: which fields the admin form shows, which default
AI persona to load, which post-processor (synthesis / proposal / revise) to
run at the end, and how to assemble the facilitator's question_block from
the captured fields.

Adding a fourth workflow type later is a matter of registering one more
entry in WORKFLOW_TYPES plus (optionally) a new processor and a new UI hint.
The discovery state machine itself doesn't change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .session import Session


# ---------------------------------------------------------------------------
# Schema types — describe an admin form field.

FieldType = Literal["text", "long_text", "list_of_text"]
ProcessorName = Literal["synthesis", "proposal", "revise"]


@dataclass(frozen=True)
class FieldSchema:
    name: str
    label: str
    type: FieldType
    required: bool = False
    default: Any = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "description": self.description,
        }


@dataclass(frozen=True)
class WorkflowSchema:
    type: str
    label: str
    description: str
    default_persona: str
    processor: ProcessorName
    fields: list[FieldSchema]
    # UI hints for the participant view. Currently supports:
    #   {"side_panel": "<workflow_data field name>"} — render that field's
    #   markdown content in a collapsible side panel next to the chat.
    ui: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "label": self.label,
            "description": self.description,
            "default_persona": self.default_persona,
            "processor": self.processor,
            "fields": [f.to_dict() for f in self.fields],
            "ui": dict(self.ui),
        }

    def field(self, name: str) -> FieldSchema | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None


# ---------------------------------------------------------------------------
# Default personas — one per workflow type. Editable per session via the
# admin UI; if blank, we fall back to these.

_PERSONA_OPEN_DISCUSSION = (
    "You are a thoughtful facilitator helping someone think through a "
    "question that matters to their community. You are NOT an expert, NOT "
    "an advocate, and NOT trying to inform or persuade. Your only job is "
    "to help this person articulate what they actually think and feel — "
    "including the parts they haven't fully worked out yet."
)

_PERSONA_DECISION_DRAFTING = (
    "You are a thoughtful facilitator helping someone work toward a "
    "concrete decision their community is about to make. Your job is to "
    "help them articulate not just their feelings on the question, but "
    "what they would actually want the group to decide — specific "
    "positions, mechanisms, and trade-offs they could live with. You are "
    "NOT an expert and NOT advocating any view; you ARE pulling them "
    "gently toward specifics they could vote on."
)

_PERSONA_DOCUMENT_REVISION = (
    "You are a thoughtful facilitator helping someone react to a specific "
    "document the group is revising. Your job is to help them articulate, "
    "in their own language, what they like, what doesn't sit right, and "
    "what's missing — staying close to the actual document and the "
    "language it uses. Don't drift into generalities. You are NOT an "
    "expert and NOT advocating for any version of the text."
)


# ---------------------------------------------------------------------------
# The registry. Adding a workflow = add an entry here + (optionally) define
# a processor in `circle.<processor>` if you picked a new processor name.

WORKFLOW_TYPES: dict[str, WorkflowSchema] = {
    "open_discussion": WorkflowSchema(
        type="open_discussion",
        label="Open discussion",
        description=(
            "A free-form facilitated conversation around a question. "
            "Output is a discussion synthesis — themes, splits, outliers."
        ),
        default_persona=_PERSONA_OPEN_DISCUSSION,
        processor="synthesis",
        fields=[
            FieldSchema(
                name="question",
                label="Question",
                type="long_text",
                required=True,
                description=(
                    "The question the facilitator AI will explore with each "
                    "participant. Multi-part numbered questions are supported."
                ),
            ),
            FieldSchema(
                name="context",
                label="Context for the AI (optional)",
                type="long_text",
                description=(
                    "Background the facilitator AI can draw on when probing. "
                    "Not shown to participants unless they ask."
                ),
            ),
            FieldSchema(
                name="community_context",
                label="Community context (optional)",
                type="long_text",
                description=(
                    "Used by synthesis to ground output in your community's "
                    "specific values, prior decisions, and named principles."
                ),
            ),
        ],
    ),
    "decision_drafting": WorkflowSchema(
        type="decision_drafting",
        label="Decision drafting",
        description=(
            "Develop concrete language the group could decide on. "
            "Output is a draft proposal + per-participant predicted vote signals."
        ),
        default_persona=_PERSONA_DECISION_DRAFTING,
        processor="proposal",
        fields=[
            FieldSchema(
                name="question",
                label="Question / decision area",
                type="long_text",
                required=True,
                description=(
                    "The decision the group is working toward. Multi-part "
                    "questions are supported and the proposal will be "
                    "organized by sub-question."
                ),
            ),
            FieldSchema(
                name="context",
                label="Context for the AI (optional)",
                type="long_text",
            ),
            FieldSchema(
                name="community_context",
                label="Community context (optional)",
                type="long_text",
            ),
        ],
    ),
    "document_revision": WorkflowSchema(
        type="document_revision",
        label="Document revision",
        description=(
            "Collect reactions to an existing document and produce a "
            "version 2 with rationale for what changed."
        ),
        default_persona=_PERSONA_DOCUMENT_REVISION,
        processor="revise",
        ui={"side_panel": "reference_document"},
        fields=[
            FieldSchema(
                name="reference_document",
                label="The document to revise",
                type="long_text",
                required=True,
                description=(
                    "Markdown content. Will be displayed in a side panel "
                    "next to the chat and used by the revisor as input."
                ),
            ),
            FieldSchema(
                name="framing",
                label="Framing for the participant",
                type="long_text",
                default=(
                    "We're working on version 2 of this document. I'd like "
                    "to hear your reaction."
                ),
                description=(
                    "Shown to the participant alongside the document. Sets "
                    "the conversational stage."
                ),
            ),
            FieldSchema(
                name="sub_questions",
                label="Sub-questions",
                type="list_of_text",
                default=[
                    "What do you like about this — what feels true and important?",
                    "What doesn't sit right — what feels off, dated, or wrong?",
                    "What's missing — what would you add that isn't there?",
                ],
                description=(
                    "The angles the facilitator covers with each participant."
                ),
            ),
            FieldSchema(
                name="community_context",
                label="Community context (optional)",
                type="long_text",
            ),
        ],
    ),
}


def get_workflow(workflow_type: str) -> WorkflowSchema:
    """Return the schema for a workflow type, or raise UnknownWorkflowType."""
    schema = WORKFLOW_TYPES.get(workflow_type)
    if schema is None:
        raise UnknownWorkflowType(
            f"Unknown workflow_type: {workflow_type!r}. "
            f"Known types: {sorted(WORKFLOW_TYPES)}"
        )
    return schema


class UnknownWorkflowType(ValueError):
    """Raised when a workflow_type isn't in WORKFLOW_TYPES."""


class WorkflowDataError(ValueError):
    """Raised when workflow_data fails schema validation."""


def validate_workflow_data(workflow_type: str, data: dict[str, Any]) -> None:
    """Validate a workflow_data dict against its schema.

    Raises WorkflowDataError on the first violation. Checks:
      * required fields are present and non-empty
      * field types match (str for text/long_text, list[str] for list_of_text)
      * no unknown fields (strict)
    """
    schema = get_workflow(workflow_type)
    known_names = {f.name for f in schema.fields}
    extra = set(data) - known_names
    if extra:
        raise WorkflowDataError(
            f"Unknown fields in workflow_data for {workflow_type!r}: {sorted(extra)}"
        )
    for field_schema in schema.fields:
        value = data.get(field_schema.name)
        if field_schema.required:
            if value is None or (isinstance(value, str) and not value.strip()) or (
                isinstance(value, list) and len(value) == 0
            ):
                raise WorkflowDataError(
                    f"Field {field_schema.name!r} is required for "
                    f"workflow {workflow_type!r}"
                )
        if value is None:
            continue
        if field_schema.type in ("text", "long_text"):
            if not isinstance(value, str):
                raise WorkflowDataError(
                    f"Field {field_schema.name!r} must be a string"
                )
        elif field_schema.type == "list_of_text":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise WorkflowDataError(
                    f"Field {field_schema.name!r} must be a list of strings"
                )


# ---------------------------------------------------------------------------
# Per-workflow extractors — used by the controller and the post-processors
# to pull out the bits they care about from a Session in a workflow-aware
# way. New workflows that share the standard "question + context" shape
# get the right behavior for free; novel shapes (like document_revision)
# get a special case here.


def get_default_persona(session: "Session") -> str:
    """The workflow type's built-in default persona for this session.

    This is the fallback used when the session's `ai_persona_id` is empty
    or points to a missing/invalid persona file. Persona resolution by id
    happens in the runtime layer (see `circle.runtime.BotContext`) so this
    module stays free of any filesystem dependency on `config/personas/`.
    """
    return get_workflow(session.workflow_type).default_persona


# Back-compat shim: older call sites used `get_persona(session)` to get the
# resolved persona text. After personas became first-class objects, the
# resolution requires a personas directory we can't see from here. Callers
# that only need the workflow default can use `get_default_persona`; callers
# needing the user-chosen persona should use
# `circle.personas.resolve_persona_text(session.common.ai_persona_id, ...)`.
get_persona = get_default_persona


def build_question_block(session: "Session") -> str:
    """The text that fills the {QUESTION_BLOCK} slot in the facilitator prompt.

    For simple workflows this is just the `question` field. For
    document_revision it's framing + the document + the sub-questions
    woven into a single block the facilitator can use.
    """
    data = session.workflow_data
    if session.workflow_type in ("open_discussion", "decision_drafting"):
        return str(data.get("question", "")).strip()

    if session.workflow_type == "document_revision":
        framing = str(data.get("framing", "")).strip()
        document = str(data.get("reference_document", "")).strip()
        subs = data.get("sub_questions") or []
        sub_lines = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(subs))
        return (
            f"{framing}\n\n"
            f"Here is the current version of the document:\n\n"
            f"---\n{document}\n---\n\n"
            f"Walk through these together — let them spend more time "
            f"on whichever is most alive for them, but get at least a "
            f"first-pass view on each:\n\n"
            f"{sub_lines}"
        ).strip()

    raise UnknownWorkflowType(session.workflow_type)


def get_context(session: "Session") -> str:
    """Optional facilitator-AI-only context. Empty string if none."""
    return str(session.workflow_data.get("context", "")).strip()


def get_community_context(session: "Session") -> str:
    """Synthesis/proposal community grounding. Empty string if none."""
    return str(session.workflow_data.get("community_context", "")).strip()


def get_synthesis_question(session: "Session") -> str:
    """What to embed as {QUESTION} in the synthesis/proposal prompts.

    For simple workflows this is the question. For document_revision the
    synthesis sees the same extended block the facilitator did, so the
    LLM can ground its output in the actual document.
    """
    return build_question_block(session)


def get_workflow_ui(session: "Session") -> dict[str, Any]:
    """The workflow_ui hints surfaced via /api/p/{id}/state to the frontend.

    Empty dict if the workflow has no special UI requirements.
    """
    schema = get_workflow(session.workflow_type)
    side_panel_field = schema.ui.get("side_panel")
    if side_panel_field:
        content = str(session.workflow_data.get(side_panel_field, "")).strip()
        if content:
            label = schema.field(side_panel_field).label if schema.field(side_panel_field) else side_panel_field
            return {
                "side_panel": {
                    "title": label,
                    "content_md": content,
                }
            }
    return {}


__all__ = [
    "FieldSchema",
    "ProcessorName",
    "UnknownWorkflowType",
    "WORKFLOW_TYPES",
    "WorkflowDataError",
    "WorkflowSchema",
    "build_question_block",
    "get_community_context",
    "get_context",
    "get_default_persona",
    "get_persona",
    "get_synthesis_question",
    "get_workflow",
    "get_workflow_ui",
    "validate_workflow_data",
]
