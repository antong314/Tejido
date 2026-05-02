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
from typing import Annotated, Any, Literal

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
from ..workflows import (
    UnknownWorkflowType,
    WORKFLOW_TYPES,
    WorkflowDataError,
    get_workflow,
    validate_workflow_data,
)


logger = logging.getLogger(__name__)


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
    type: str
    label: str
    description: str
    default_persona: str
    processor: str
    fields: list[dict[str, Any]]
    ui: dict[str, Any]


class RunResponse(BaseModel):
    status: str
    processor: str
    session_id: str


class OutputFileEntry(BaseModel):
    filename: str
    bytes: int
    created_at: str


class ErrorResponse(BaseModel):
    code: str
    error: str


# ---------------------------------------------------------------------------
# Mount.


def mount(app: FastAPI, *, registry: SessionRegistry) -> None:
    """Attach the admin REST endpoints to the given FastAPI app."""
    router = _build_router(registry)
    app.include_router(router, prefix="/api/admin", tags=["admin"])


def _build_router(registry: SessionRegistry) -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------------ types

    @router.get("/workflow-types", response_model=list[WorkflowTypeResponse])
    async def list_workflow_types() -> list[WorkflowTypeResponse]:
        return [
            WorkflowTypeResponse(**schema.to_dict())
            for schema in WORKFLOW_TYPES.values()
        ]

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
