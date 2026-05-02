"""FastAPI app for the web adapter.

Now multi-session: every per-participant route is scoped under a session
id in the URL path. The frontend has the session id from /s/<id> and
keeps the participant_id in localStorage; combined, the URLs are
self-describing and don't need a global participant→session lookup
table on the backend.

Routes:
  GET  /                                            — root: redirects to
                                                       the first known
                                                       session, or the
                                                       admin index
  GET  /s/{session_id}                              — serves the React
                                                       app (or a fallback
                                                       placeholder)

  POST /api/s/{session_id}/join                     — claim a name → pid

  GET  /api/s/{session_id}/p/{participant_id}/state
  POST /api/s/{session_id}/p/{participant_id}/message
  POST /api/s/{session_id}/p/{participant_id}/callback
  POST /api/s/{session_id}/p/{participant_id}/audio
  GET  /api/s/{session_id}/p/{participant_id}/events  (SSE)

Admin REST endpoints live in `circle.web.admin` and are mounted by
`create_app`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Path as PathParam,
    UploadFile,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..controller import conversation as conversation_controller
from ..controller.identity import (
    InvalidNameError,
    NameTakenError,
    claim_name,
)
from ..registry import SessionRegistry
from ..runtime import BotContext
from ..state import Phase
from ..storage import load_participant
from ..whisper_client import TranscriptionError, make_temp_audio
from ..workflows import get_workflow_ui
from .dispatch import InvalidCallbackError, dispatch_callback
from .render_action import action_to_json
from .sse import SSEHub


# Built React app lives at <repo_root>/web/dist.
_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"

logger = logging.getLogger(__name__)

_SESSION_ID_PATTERN = r"^[a-zA-Z0-9_-]+$"
_PARTICIPANT_ID_PATTERN = r"^[a-zA-Z0-9_-]+$"


# ---------------------------------------------------------------------------
# Pydantic models for request / response bodies.


class JoinRequest(BaseModel):
    name: str = Field(..., description="Display name the participant chose.")


class JoinResponse(BaseModel):
    participant_id: str
    display_name: str


class StateResponse(BaseModel):
    participant_id: str
    participant_name: str
    session_id: str
    question: str
    phase: str
    transcript: list[dict]
    extracted_points: list[dict]
    additions: list[dict]
    status: str
    started_at: str | None
    completed_at: str | None
    # Workflow-aware additions for the frontend's per-workflow UI.
    workflow_type: str
    workflow_ui: dict


class MessageRequest(BaseModel):
    text: str


class CallbackRequest(BaseModel):
    callback_data: str = Field(
        ...,
        description=(
            "Discrete event: button tap or command trigger. Mirrors the "
            "Telegram callback_data scheme — see circle.web.dispatch."
        ),
    )


class AckResponse(BaseModel):
    """Returned by /message and /callback once the controller drains."""

    status: str = "ok"


class ErrorResponse(BaseModel):
    code: str
    error: str


# ---------------------------------------------------------------------------


async def _require_context(
    registry: SessionRegistry, session_id: str
) -> BotContext:
    ctx = await registry.get(session_id)
    if ctx is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "session_not_found",
                "error": f"Unknown session {session_id!r}",
            },
        )
    return ctx


def _require_participant(context: BotContext, participant_id: str) -> str:
    """Return the participant's display_name, or raise 404."""
    raw = load_participant(context.data_dir, participant_id)
    if raw is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "participant_not_found",
                "error": "No participant with that id in this session",
            },
        )
    return str(raw.get("participant_name", ""))


async def _broadcast_phase(
    context: BotContext, sse_hub: SSEHub, participant_id: str
) -> None:
    raw = load_participant(context.data_dir, participant_id)
    if raw is None:
        return
    phase = raw.get("phase", "")
    await sse_hub.broadcast(
        participant_id, {"type": "phase_update", "phase": phase}
    )


def _suffix_for_audio(filename: str | None, content_type: str | None) -> str:
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[1].lower()
        if 1 < len(ext) <= 6 and ext.isascii():
            return ext
    if content_type:
        ct = content_type.lower()
        if "webm" in ct:
            return ".webm"
        if "mp4" in ct or "mp4a" in ct or "aac" in ct:
            return ".m4a"
        if "ogg" in ct or "opus" in ct:
            return ".ogg"
        if "wav" in ct:
            return ".wav"
    return ".audio"


def _state_for_response(raw: dict, context: BotContext) -> dict:
    """Pick a stable subset of the on-disk JSON, plus workflow UI hints."""
    return {
        "participant_id": str(raw.get("participant_id", "")),
        "participant_name": str(raw.get("participant_name", "")),
        "session_id": str(raw.get("session_id", "")),
        "question": str(raw.get("question", "")),
        "phase": str(raw.get("phase", "")),
        "transcript": list(raw.get("transcript", [])),
        "extracted_points": list(raw.get("extracted_points", [])),
        "additions": list(raw.get("additions", [])),
        "status": str(raw.get("status", "")),
        "started_at": raw.get("started_at"),
        "completed_at": raw.get("completed_at"),
        "workflow_type": context.session.workflow_type,
        "workflow_ui": get_workflow_ui(context.session),
    }


# ---------------------------------------------------------------------------
# App factory.


def create_app(*, registry: SessionRegistry) -> FastAPI:
    """Build a FastAPI app bound to a SessionRegistry.

    The registry is the source of per-session BotContexts; routes look up
    by session id from the URL. The SSEHub is owned by the app and
    lives for the process lifetime.
    """
    app = FastAPI(
        title="Tejido — Web Adapter",
        description=(
            "AI-facilitated group deliberation. Multi-session web entry "
            "point for participants. The Telegram adapter shares the "
            "same backend (single-session at a time)."
        ),
    )
    sse_hub = SSEHub()
    app.state.sse_hub = sse_hub
    app.state.registry = registry

    # ------------------------------------------------------------------ root

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        ids = registry.list_session_ids()
        if ids:
            return RedirectResponse(url=f"/s/{ids[0]}", status_code=307)
        return RedirectResponse(url="/admin", status_code=307)

    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{rest:path}", include_in_schema=False)
    async def admin_spa(rest: str = "") -> HTMLResponse:
        # The React app handles /admin/* routing client-side, so any path
        # under /admin returns the SPA's index.html and the bundle takes
        # over from there. (rest is ignored — it's there to give FastAPI
        # a path-converter to match.)
        del rest
        index_path = _FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse(
            "<h1>Tejido admin</h1>"
            "<p>The React frontend hasn't been built yet. "
            "Run <code>cd web &amp;&amp; npm run build</code>.</p>"
        )

    @app.get("/s/{session_id}", include_in_schema=False)
    async def session_page(
        session_id: Annotated[str, PathParam(pattern=_SESSION_ID_PATTERN)],
    ):
        # 404 the page if the session config doesn't exist on disk.
        await _require_context(registry, session_id)
        index_path = _FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse(_PLACEHOLDER_HTML.replace("{{SESSION_ID}}", session_id))

    if _FRONTEND_DIST.exists() and (_FRONTEND_DIST / "assets").exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
            name="frontend_assets",
        )

    # ------------------------------------------------------------------ join

    @app.post(
        "/api/s/{session_id}/join",
        response_model=JoinResponse,
        responses={
            400: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    async def join(
        session_id: Annotated[str, PathParam(pattern=_SESSION_ID_PATTERN)],
        body: JoinRequest,
    ) -> JoinResponse:
        context = await _require_context(registry, session_id)
        try:
            participant_id, display_name = claim_name(context.data_dir, body.name)
        except InvalidNameError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_name", "error": str(exc)},
            )
        except NameTakenError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "name_taken", "error": str(exc)},
            )

        async with context.lock_for(participant_id):
            state = context.load_or_create(participant_id, display_name)
            if state.phase == Phase.NOT_STARTED:
                state.transition_to(Phase.AWAITING_CONSENT)
                context.save(state)

        logger.info(
            "web join session=%s participant_id=%s display_name=%s",
            session_id,
            participant_id,
            display_name,
        )
        return JoinResponse(
            participant_id=participant_id, display_name=display_name
        )

    # ------------------------------------------------------------------ state

    @app.get(
        "/api/s/{session_id}/p/{participant_id}/state",
        response_model=StateResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_state(
        session_id: Annotated[str, PathParam(pattern=_SESSION_ID_PATTERN)],
        participant_id: Annotated[str, PathParam(pattern=_PARTICIPANT_ID_PATTERN)],
    ) -> StateResponse:
        context = await _require_context(registry, session_id)
        raw = load_participant(context.data_dir, participant_id)
        if raw is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "participant_not_found",
                    "error": "No participant with that id in this session",
                },
            )
        return StateResponse(**_state_for_response(raw, context))

    # ------------------------------------------------------------------ message

    @app.post(
        "/api/s/{session_id}/p/{participant_id}/message",
        response_model=AckResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def post_message(
        session_id: Annotated[str, PathParam(pattern=_SESSION_ID_PATTERN)],
        participant_id: Annotated[str, PathParam(pattern=_PARTICIPANT_ID_PATTERN)],
        body: MessageRequest,
    ) -> AckResponse:
        context = await _require_context(registry, session_id)
        display_name = _require_participant(context, participant_id)

        actions = conversation_controller.handle_message(
            participant_id=participant_id,
            display_name=display_name,
            session=context,
            text=body.text,
            via="text",
            detected_language=None,
        )
        async for action in actions:
            await sse_hub.broadcast(participant_id, action_to_json(action))
        await _broadcast_phase(context, sse_hub, participant_id)
        return AckResponse()

    # ------------------------------------------------------------------ callback

    @app.post(
        "/api/s/{session_id}/p/{participant_id}/callback",
        response_model=AckResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    async def post_callback(
        session_id: Annotated[str, PathParam(pattern=_SESSION_ID_PATTERN)],
        participant_id: Annotated[str, PathParam(pattern=_PARTICIPANT_ID_PATTERN)],
        body: CallbackRequest,
    ) -> AckResponse:
        context = await _require_context(registry, session_id)
        display_name = _require_participant(context, participant_id)

        try:
            actions = dispatch_callback(
                callback_data=body.callback_data,
                participant_id=participant_id,
                display_name=display_name,
                session=context,
            )
        except InvalidCallbackError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_callback", "error": str(exc)},
            )

        async for action in actions:
            await sse_hub.broadcast(participant_id, action_to_json(action))
        await _broadcast_phase(context, sse_hub, participant_id)
        return AckResponse()

    # ------------------------------------------------------------------ audio

    @app.post(
        "/api/s/{session_id}/p/{participant_id}/audio",
        response_model=AckResponse,
        responses={
            400: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )
    async def post_audio(
        session_id: Annotated[str, PathParam(pattern=_SESSION_ID_PATTERN)],
        participant_id: Annotated[str, PathParam(pattern=_PARTICIPANT_ID_PATTERN)],
        file: UploadFile = File(...),
    ) -> AckResponse:
        context = await _require_context(registry, session_id)
        display_name = _require_participant(context, participant_id)

        suffix = _suffix_for_audio(file.filename, file.content_type)
        audio_path = make_temp_audio(suffix=suffix)
        try:
            data = await file.read()
            audio_path.write_bytes(data)
        except Exception:
            audio_path.unlink(missing_ok=True)
            logger.exception("audio upload save failed")
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "audio_save_failed",
                    "error": "Could not save the upload",
                },
            )

        try:
            result = await context.whisper.transcribe_audio(audio_path)
        except TranscriptionError as exc:
            logger.warning("whisper transcription failed: %s", exc)
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "transcription_failed",
                    "error": "Couldn't transcribe that audio. Try again or type instead.",
                },
            )

        await sse_hub.broadcast(
            participant_id,
            {"type": "user_message", "text": result.text, "via": "voice"},
        )

        actions = conversation_controller.handle_message(
            participant_id=participant_id,
            display_name=display_name,
            session=context,
            text=result.text,
            via="voice",
            detected_language=result.language,
        )
        async for action in actions:
            await sse_hub.broadcast(participant_id, action_to_json(action))
        await _broadcast_phase(context, sse_hub, participant_id)
        return AckResponse()

    # ------------------------------------------------------------------ events

    @app.get("/api/s/{session_id}/p/{participant_id}/events")
    async def get_events(
        session_id: Annotated[str, PathParam(pattern=_SESSION_ID_PATTERN)],
        participant_id: Annotated[str, PathParam(pattern=_PARTICIPANT_ID_PATTERN)],
    ) -> StreamingResponse:
        context = await _require_context(registry, session_id)
        _require_participant(context, participant_id)

        async def event_stream() -> AsyncIterator[bytes]:
            async with sse_hub.subscribe(participant_id) as queue:
                yield b"event: ready\ndata: {}\n\n"
                while True:
                    event = await queue.get()
                    yield f"data: {json.dumps(event)}\n\n".encode("utf-8")

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Admin REST endpoints get mounted here. Imported lazily to keep
    # `circle.web.app` importable without `circle.web.admin` (handy in
    # tests that only exercise the participant-facing routes).
    from . import admin as _admin

    _admin.mount(app, registry=registry)

    return app


# ---------------------------------------------------------------------------
# Placeholder HTML for the case when web/dist isn't built yet. Lets curl
# verify the backend works end-to-end without a Vite build.

_PLACEHOLDER_HTML = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Tejido — {{SESSION_ID}}</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 480px; margin: 4em auto;
           padding: 0 1em; color: #222; }
    h1 { font-size: 1.4em; margin-bottom: 0.4em; }
    label { display: block; margin: 1em 0 0.3em; }
    input[type=text] { width: 100%; padding: 0.6em; font-size: 1em;
                       border: 1px solid #aaa; border-radius: 4px; }
    button { margin-top: 1em; padding: 0.6em 1.2em; font-size: 1em;
             background: #222; color: white; border: 0; border-radius: 4px;
             cursor: pointer; }
    .error { color: #b00020; margin-top: 0.5em; min-height: 1.2em; }
    .ok    { color: #006400; margin-top: 0.5em; }
    pre    { background: #f4f4f4; padding: 1em; border-radius: 4px;
             overflow-x: auto; font-size: 0.85em; }
  </style>
</head>
<body>
  <h1>Tejido — session {{SESSION_ID}}</h1>
  <p>Frontend not built. <code>cd web &amp;&amp; npm run build</code>.</p>
  <form id="join-form">
    <label for="name">What should we call you?</label>
    <input id="name" type="text" autocomplete="off" required />
    <button type="submit">Join</button>
    <div class="error" id="error"></div>
    <div class="ok"    id="ok"></div>
  </form>
  <pre id="state" hidden></pre>
  <script>
    const SESSION_ID = "{{SESSION_ID}}";
    document.getElementById("join-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = document.getElementById("name").value;
      const err = document.getElementById("error");
      const ok  = document.getElementById("ok");
      err.textContent = ""; ok.textContent = "";
      const r = await fetch(`/api/s/${SESSION_ID}/join`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name}),
      });
      const data = await r.json();
      if (!r.ok) { err.textContent = (data.detail && data.detail.error) || "Join failed."; return; }
      ok.textContent = `Joined as ${data.display_name} (id ${data.participant_id})`;
      const s = await fetch(`/api/s/${SESSION_ID}/p/${data.participant_id}/state`).then(r => r.json());
      const pre = document.getElementById("state");
      pre.hidden = false;
      pre.textContent = JSON.stringify(s, null, 2);
    });
  </script>
</body>
</html>
"""
