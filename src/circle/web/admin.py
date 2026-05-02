"""Admin REST endpoints — the surface the admin UI talks to.

No auth in phase 1 (per architectural decision). The admin UI is
intended to be reached either over loopback or behind whatever
network-level protection the deployment provides; auth is a follow-up.

Routes mounted under /api/admin:

  GET    /workflow-types            → schemas for all workflow types
                                       (used to render the admin form)
  GET    /sessions                  → list of all sessions (disk truth)
  POST   /sessions                  → create a new session
  GET    /sessions/{id}             → fetch a session config
  PATCH  /sessions/{id}             → update a session config
  DELETE /sessions/{id}             → delete a session config
  POST   /sessions/{id}/run/{processor}
                                    → trigger synthesis | proposal | revise
                                       (returns 202 + run id; output written
                                       to the session's output dir)
  GET    /sessions/{id}/outputs     → list past outputs for a session
  GET    /sessions/{id}/outputs/{filename}
                                    → download / view one output
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from ..telegram_manager import TelegramManager

from fastapi import (
    APIRouter,
    BackgroundTasks,
    FastAPI,
    HTTPException,
    Path as PathParam,
)
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ..registry import SessionRegistry
from ..session import (
    CommonSettings,
    InvalidSessionIdError,
    Session,
    SessionError,
    SessionFileError,
    WhisperSettings,
    delete_session,
    new_session,
    save_session,
    session_path,
)
from ..storage import (
    list_participant_files,
    load_participant,
    read_index,
)
from ..prompts import FACILITATOR_MECHANICS
from ..workflow_overrides import (
    WorkflowOverrides,
    list_overrides,
    load_overrides,
    save_overrides,
)
from ..workflows import (
    UnknownWorkflowType,
    WORKFLOW_TYPES,
    WorkflowDataError,
    get_workflow,
    validate_workflow_data,
)


logger = logging.getLogger(__name__)


def _count_participant_words(transcript: list[dict]) -> int:
    """Total words contributed by the participant across all their turns.

    Whitespace-split — same definition the admin would get from a quick
    `wc -w`, no language-aware tokenization. Facilitator (assistant) turns
    are excluded so the count reflects what the participant actually said.
    """
    total = 0
    for turn in transcript:
        if turn.get("role") != "user":
            continue
        content = turn.get("content")
        if not isinstance(content, str):
            continue
        total += len(content.split())
    return total


# ---------------------------------------------------------------------------
# Schemas the admin form consumes / produces.


class CreateSessionRequest(BaseModel):
    id: str = Field(..., description="kebab/snake_case slug. Used in URLs.")
    title: str
    workflow_type: str
    common: dict[str, Any] = Field(default_factory=dict)
    whisper: dict[str, Any] = Field(default_factory=dict)
    workflow_data: dict[str, Any] = Field(default_factory=dict)


class UpdateSessionRequest(BaseModel):
    """Partial update — only fields that should change. id and workflow_type
    are immutable. Editing workflow_type would invalidate workflow_data;
    we make the admin delete + recreate instead."""

    title: str | None = None
    common: dict[str, Any] | None = None
    whisper: dict[str, Any] | None = None
    workflow_data: dict[str, Any] | None = None


class SessionResponse(BaseModel):
    id: str
    title: str
    workflow_type: str
    created_at: str
    common: dict[str, Any]
    whisper: dict[str, Any]
    workflow_data: dict[str, Any]


class WorkflowTypeResponse(BaseModel):
    """The full per-workflow-type record the admin UI consumes.

    Includes the structural bits (label, description, processor, field
    schema, UI hints) plus both the code-defined defaults and the current
    admin overrides for the three editable prompt fragments. The session
    form only needs the structural fields; the workflow editor needs the
    rest.
    """

    type: str
    label: str
    description: str
    processor: str
    fields: list[dict[str, Any]]
    ui: dict[str, Any]
    # Defaults (what runs if nothing is overridden).
    default_task_framing: str
    default_output_template: str
    default_mechanics: str
    # Current overrides (empty string = no override, default applies).
    task_framing_override: str
    output_template_override: str
    mechanics_override: str


class WorkflowOverridesUpdate(BaseModel):
    """Partial update to a workflow type's editable prompt fragments.

    Any field omitted is left unchanged. Pass empty string to clear an
    override (revert to the code-defined default).
    """

    task_framing: str | None = None
    output_template: str | None = None
    mechanics_override: str | None = None


class RunResponse(BaseModel):
    status: str
    processor: str
    session_id: str


class OutputFileEntry(BaseModel):
    filename: str
    bytes: int
    created_at: str


class ParticipantSummary(BaseModel):
    """One row in the participants table the admin sees per session."""

    participant_id: str
    participant_name: str
    phase: str
    status: str
    started_at: str | None
    completed_at: str | None
    num_turns: int
    # Words contributed by THIS participant only — facilitator turns are
    # excluded. Useful as a proxy for how much they actually said vs. how
    # many times they replied (a 23-turn participant who answers in three
    # words each is very different from a 9-turn one writing paragraphs).
    participant_word_count: int
    num_extracted_points: int
    num_additions: int


class ParticipantDetail(BaseModel):
    """Full per-participant record. Includes the conversation transcript and
    the extracted points + additions with their permission choices.

    PRD §5.1 says participant conversations are not viewable during the
    session. This admin endpoint is for after the fact (and admin-only,
    because there's no auth gating it from the participant facing routes
    yet — single-laptop deployment assumed). Consider locking down once
    auth lands.
    """

    participant_id: str
    participant_name: str
    session_id: str
    question: str
    phase: str
    status: str
    started_at: str | None
    completed_at: str | None
    transcript: list[dict]
    extracted_points: list[dict]
    additions: list[dict]


class TelegramStatusResponse(BaseModel):
    """Current state of the Telegram binding.

    `available` is False in processes that don't run Telegram (e.g.
    circle.web) — the UI should hide the binding card in that case.
    """

    available: bool
    bound_session_id: str | None


class TelegramBindRequest(BaseModel):
    """Bind to a session, or unbind when session_id is null."""

    session_id: str | None = None


class ErrorResponse(BaseModel):
    code: str
    error: str


# ---------------------------------------------------------------------------
# Mount.


def mount(
    app: FastAPI,
    *,
    registry: SessionRegistry,
    telegram: "TelegramManager | None" = None,
) -> None:
    """Attach the admin REST endpoints to the given FastAPI app.

    `telegram` enables the GET/PUT /telegram binding endpoints. Pass
    None for processes that don't run Telegram (e.g. circle.web), in
    which case GET returns `available: false` and PUT returns 503.
    """
    router = _build_router(registry, telegram)
    app.include_router(router, prefix="/api/admin", tags=["admin"])


def _build_router(
    registry: SessionRegistry,
    telegram: "TelegramManager | None",
) -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------------ types

    # ------------------------------------------------------------------ telegram

    @router.get(
        "/telegram", response_model=TelegramStatusResponse,
    )
    async def get_telegram_status() -> TelegramStatusResponse:
        if telegram is None:
            return TelegramStatusResponse(available=False, bound_session_id=None)
        return TelegramStatusResponse(
            available=True,
            bound_session_id=telegram.bound_session_id,
        )

    @router.put(
        "/telegram",
        response_model=TelegramStatusResponse,
        responses={
            400: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def put_telegram_binding(
        body: TelegramBindRequest,
    ) -> TelegramStatusResponse:
        if telegram is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "telegram_not_available",
                    "error": (
                        "This server process doesn't run Telegram. Start "
                        "the combined entrypoint (`python -m circle.run`)."
                    ),
                },
            )
        sid = body.session_id
        if sid is not None and not sid.strip():
            sid = None
        try:
            from ..telegram_manager import TelegramBindingError

            await telegram.bind(sid)
        except TelegramBindingError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "telegram_bind_failed", "error": str(exc)},
            )
        return TelegramStatusResponse(
            available=True,
            bound_session_id=telegram.bound_session_id,
        )

    # ------------------------------------------------------------------ workflow types

    def _workflow_type_response(workflow_type: str) -> WorkflowTypeResponse:
        """Assemble the full record (defaults + overrides) for one workflow type."""
        schema = get_workflow(workflow_type)
        overrides = load_overrides(workflow_type, registry.app_config.workflows_dir)
        return WorkflowTypeResponse(
            type=schema.type,
            label=schema.label,
            description=schema.description,
            processor=schema.processor,
            fields=[f.to_dict() for f in schema.fields],
            ui=dict(schema.ui),
            default_task_framing=schema.default_task_framing,
            default_output_template=schema.default_output_template,
            default_mechanics=FACILITATOR_MECHANICS,
            task_framing_override=overrides.task_framing,
            output_template_override=overrides.output_template,
            mechanics_override=overrides.mechanics_override,
        )

    @router.get("/workflow-types", response_model=list[WorkflowTypeResponse])
    async def list_workflow_types() -> list[WorkflowTypeResponse]:
        return [_workflow_type_response(t) for t in WORKFLOW_TYPES]

    @router.get(
        "/workflow-types/{workflow_type}",
        response_model=WorkflowTypeResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_workflow_type(workflow_type: str) -> WorkflowTypeResponse:
        if workflow_type not in WORKFLOW_TYPES:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "workflow_type_not_found",
                    "error": f"No workflow type {workflow_type!r}",
                },
            )
        return _workflow_type_response(workflow_type)

    @router.patch(
        "/workflow-types/{workflow_type}",
        response_model=WorkflowTypeResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def patch_workflow_type(
        workflow_type: str,
        body: WorkflowOverridesUpdate,
    ) -> WorkflowTypeResponse:
        """Update any subset of the editable prompt fragments. Empty
        string clears an override (revert to default)."""
        if workflow_type not in WORKFLOW_TYPES:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "workflow_type_not_found",
                    "error": f"No workflow type {workflow_type!r}",
                },
            )
        current = load_overrides(workflow_type, registry.app_config.workflows_dir)
        merged = WorkflowOverrides(
            type=workflow_type,
            task_framing=(
                body.task_framing if body.task_framing is not None
                else current.task_framing
            ),
            output_template=(
                body.output_template if body.output_template is not None
                else current.output_template
            ),
            mechanics_override=(
                body.mechanics_override if body.mechanics_override is not None
                else current.mechanics_override
            ),
        )
        save_overrides(merged, registry.app_config.workflows_dir)
        logger.info("admin updated workflow_type=%s overrides", workflow_type)
        return _workflow_type_response(workflow_type)

    # ------------------------------------------------------------------ sessions

    @router.get("/sessions", response_model=list[SessionResponse])
    async def list_sessions() -> list[SessionResponse]:
        return [SessionResponse(**s.to_dict()) for s in registry.list_sessions()]

    @router.post(
        "/sessions",
        response_model=SessionResponse,
        responses={
            400: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    async def create_session(body: CreateSessionRequest) -> SessionResponse:
        if session_path(registry.app_config.sessions_dir, body.id).exists():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "session_exists",
                    "error": f"A session with id {body.id!r} already exists.",
                },
            )
        try:
            session = new_session(
                id=body.id,
                title=body.title,
                workflow_type=body.workflow_type,
                common=CommonSettings.from_dict(body.common),
                whisper=WhisperSettings.from_dict(body.whisper),
                workflow_data=body.workflow_data,
            )
        except (InvalidSessionIdError, UnknownWorkflowType, WorkflowDataError, SessionError) as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_session", "error": str(exc)},
            )
        await registry.register_or_reload(session)
        # Make sure the per-session data dir exists so the dashboard can
        # immediately list it (even with zero participants).
        registry.app_config.data_dir_for(session.id).mkdir(
            parents=True, exist_ok=True
        )
        logger.info(
            "admin created session id=%s workflow=%s",
            session.id,
            session.workflow_type,
        )
        return SessionResponse(**session.to_dict())

    @router.get(
        "/sessions/{session_id}",
        response_model=SessionResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_session(
        session_id: Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")],
    ) -> SessionResponse:
        try:
            from ..session import load_session as _load

            session = _load(session_id, registry.app_config.sessions_dir)
        except SessionFileError:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "session_not_found",
                    "error": f"No session {session_id!r}",
                },
            )
        return SessionResponse(**session.to_dict())

    @router.patch(
        "/sessions/{session_id}",
        response_model=SessionResponse,
        responses={
            400: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
        },
    )
    async def patch_session(
        session_id: Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")],
        body: UpdateSessionRequest,
    ) -> SessionResponse:
        try:
            from ..session import load_session as _load

            current = _load(session_id, registry.app_config.sessions_dir)
        except SessionFileError:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "session_not_found",
                    "error": f"No session {session_id!r}",
                },
            )
        merged_common = (
            CommonSettings.from_dict(body.common)
            if body.common is not None
            else current.common
        )
        merged_whisper = (
            WhisperSettings.from_dict(body.whisper)
            if body.whisper is not None
            else current.whisper
        )
        merged_workflow_data = (
            dict(body.workflow_data)
            if body.workflow_data is not None
            else dict(current.workflow_data)
        )
        try:
            updated = Session(
                id=current.id,
                title=body.title if body.title is not None else current.title,
                workflow_type=current.workflow_type,
                created_at=current.created_at,
                common=merged_common,
                whisper=merged_whisper,
                workflow_data=merged_workflow_data,
            )
        except (WorkflowDataError, UnknownWorkflowType, SessionError) as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_session", "error": str(exc)},
            )
        await registry.register_or_reload(updated)
        logger.info("admin updated session id=%s", updated.id)
        return SessionResponse(**updated.to_dict())

    @router.delete(
        "/sessions/{session_id}",
        responses={404: {"model": ErrorResponse}},
    )
    async def remove_session(
        session_id: Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")],
    ) -> dict[str, Any]:
        existed = delete_session(session_id, registry.app_config.sessions_dir)
        if not existed:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "session_not_found",
                    "error": f"No session {session_id!r}",
                },
            )
        await registry.drop(session_id)
        # If Telegram was bound to the deleted session, unbind it so the
        # bot doesn't end up pointing at a session that no longer exists
        # — that'd silently fail on the next message.
        if telegram is not None:
            await telegram.unbind_if_session(session_id)
        logger.info(
            "admin deleted session id=%s (data dir kept at data/%s/)",
            session_id,
            session_id,
        )
        # The per-session data dir is intentionally preserved so syntheses
        # / proposals / revisions can still be run for archival purposes.
        return {"status": "ok", "data_kept_at": f"data/{session_id}"}

    # ------------------------------------------------------------------ run

    @router.post(
        "/sessions/{session_id}/run/{processor}",
        response_model=RunResponse,
        responses={
            400: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
        },
    )
    async def run_processor(
        session_id: Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")],
        processor: Literal["synthesis", "proposal", "revise"],
        background: BackgroundTasks,
    ) -> RunResponse:
        try:
            from ..session import load_session as _load

            session = _load(session_id, registry.app_config.sessions_dir)
        except SessionFileError:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "session_not_found",
                    "error": f"No session {session_id!r}",
                },
            )
        # Make sure the chosen processor matches what this workflow declares.
        wf = get_workflow(session.workflow_type)
        if wf.processor != processor:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "processor_mismatch",
                    "error": (
                        f"Session {session_id!r} is workflow_type "
                        f"{session.workflow_type!r}; its processor is "
                        f"{wf.processor!r}, not {processor!r}."
                    ),
                },
            )

        async def _run() -> None:
            try:
                if processor == "synthesis":
                    from ..synthesis import run_synthesis

                    await run_synthesis(session, registry.app_config)
                elif processor == "proposal":
                    from ..proposal import run_proposal

                    await run_proposal(session, registry.app_config)
                elif processor == "revise":
                    from ..revise import run_revise

                    await run_revise(session, registry.app_config)
                logger.info(
                    "admin run %s for session=%s completed",
                    processor,
                    session_id,
                )
            except Exception:
                logger.exception(
                    "admin run %s for session=%s failed", processor, session_id
                )

        background.add_task(_run)
        return RunResponse(status="started", processor=processor, session_id=session_id)

    # ------------------------------------------------------------------ participants

    @router.get(
        "/sessions/{session_id}/participants",
        response_model=list[ParticipantSummary],
        responses={404: {"model": ErrorResponse}},
    )
    async def list_participants(
        session_id: Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")],
    ) -> list[ParticipantSummary]:
        # 404 if the session config doesn't exist; participant data may
        # exist for it on disk regardless, but there's no point listing
        # the participants of a session the admin can't open.
        try:
            from ..session import load_session as _load

            _load(session_id, registry.app_config.sessions_dir)
        except SessionFileError:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "session_not_found",
                    "error": f"No session {session_id!r}",
                },
            )

        data_dir = registry.app_config.data_dir_for(session_id)
        # Index gives us a stable join order; fall back to scanning if the
        # index is stale or missing.
        index = read_index(data_dir)
        summaries: dict[str, ParticipantSummary] = {}
        for path in list_participant_files(data_dir):
            raw = load_participant(data_dir, path.stem)
            if raw is None:
                continue
            pid = str(raw.get("participant_id") or path.stem)
            transcript = raw.get("transcript", []) or []
            summaries[pid] = ParticipantSummary(
                participant_id=pid,
                participant_name=str(
                    raw.get("participant_name") or index.get(pid) or pid
                ),
                phase=str(raw.get("phase", "")),
                status=str(raw.get("status", "")),
                started_at=raw.get("started_at"),
                completed_at=raw.get("completed_at"),
                num_turns=len(transcript),
                participant_word_count=_count_participant_words(transcript),
                num_extracted_points=len(raw.get("extracted_points", []) or []),
                num_additions=len(raw.get("additions", []) or []),
            )

        # Order: index order first (preserves join order), then any
        # on-disk participants the index doesn't know about.
        ordered: list[ParticipantSummary] = []
        for pid in index:
            if pid in summaries:
                ordered.append(summaries.pop(pid))
        ordered.extend(summaries.values())
        return ordered

    @router.get(
        "/sessions/{session_id}/participants/{participant_id}",
        response_model=ParticipantDetail,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_participant(
        session_id: Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")],
        participant_id: Annotated[
            str, PathParam(pattern=r"^[a-zA-Z0-9_-]+$")
        ],
    ) -> ParticipantDetail:
        try:
            from ..session import load_session as _load

            _load(session_id, registry.app_config.sessions_dir)
        except SessionFileError:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "session_not_found",
                    "error": f"No session {session_id!r}",
                },
            )

        data_dir = registry.app_config.data_dir_for(session_id)
        raw = load_participant(data_dir, participant_id)
        if raw is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "participant_not_found",
                    "error": "No participant with that id in this session",
                },
            )
        return ParticipantDetail(
            participant_id=str(raw.get("participant_id", participant_id)),
            participant_name=str(raw.get("participant_name", "")),
            session_id=str(raw.get("session_id", session_id)),
            question=str(raw.get("question", "")),
            phase=str(raw.get("phase", "")),
            status=str(raw.get("status", "")),
            started_at=raw.get("started_at"),
            completed_at=raw.get("completed_at"),
            transcript=list(raw.get("transcript", []) or []),
            extracted_points=list(raw.get("extracted_points", []) or []),
            additions=list(raw.get("additions", []) or []),
        )

    # ------------------------------------------------------------------ outputs

    @router.get(
        "/sessions/{session_id}/outputs",
        response_model=list[OutputFileEntry],
    )
    async def list_outputs(
        session_id: Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")],
    ) -> list[OutputFileEntry]:
        # Look across all output dirs; filter by filename containing the
        # session id (since we now namespace output filenames per session).
        out: list[OutputFileEntry] = []
        for dir_ in (
            registry.app_config.syntheses_dir,
            registry.app_config.proposals_dir,
            registry.app_config.revisions_dir,
        ):
            if not dir_.exists():
                continue
            for path in sorted(dir_.glob(f"*_{session_id}_*.md")):
                stat = path.stat()
                out.append(
                    OutputFileEntry(
                        filename=path.name,
                        bytes=stat.st_size,
                        created_at=datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                    )
                )
        return out

    @router.get(
        "/sessions/{session_id}/outputs/{filename}",
        responses={404: {"model": ErrorResponse}},
    )
    async def get_output(
        session_id: Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")],
        filename: str,
    ):
        # Find the file in whichever output dir contains it.
        if "/" in filename or "\\" in filename or filename.startswith("."):
            raise HTTPException(status_code=400, detail={"code": "bad_filename", "error": "invalid filename"})
        if f"_{session_id}_" not in filename:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "output_not_found",
                    "error": "No output by that name for this session",
                },
            )
        for dir_ in (
            registry.app_config.syntheses_dir,
            registry.app_config.proposals_dir,
            registry.app_config.revisions_dir,
        ):
            candidate = dir_ / filename
            if candidate.exists():
                return FileResponse(
                    candidate, media_type="text/markdown; charset=utf-8"
                )
        raise HTTPException(
            status_code=404,
            detail={
                "code": "output_not_found",
                "error": "No output by that name for this session",
            },
        )

    return router
