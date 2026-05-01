"""FastAPI app for the web adapter.

Routes:
  GET  /                                — redirects to the session URL
  GET  /s/{session_id}                  — minimal HTML page (placeholder
                                           until the React frontend lands)
  POST /api/s/{session_id}/join         — claim a name, get a participant_id
  GET  /api/p/{participant_id}/state    — current JSON state for the
                                           frontend to bootstrap from
  POST /api/p/{participant_id}/message  — submit free-text input
  POST /api/p/{participant_id}/callback — submit a button choice or command
  GET  /api/p/{participant_id}/events   — SSE stream of OutboundActions

Later commits add /audio.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path as PathParam
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..controller import conversation as conversation_controller
from ..controller.identity import (
    InvalidNameError,
    NameTakenError,
    claim_name,
)
from ..runtime import BotContext
from ..storage import load_participant
from .dispatch import InvalidCallbackError, dispatch_callback
from .render_action import action_to_json
from .sse import SSEHub

logger = logging.getLogger(__name__)


_SESSION_ID_PATTERN = r"^[a-zA-Z0-9_-]+$"
_PARTICIPANT_ID_PATTERN = r"^[a-zA-Z0-9_-]+$"


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


class MessageRequest(BaseModel):
    text: str = Field(..., description="Free-text input from the participant.")


class CallbackRequest(BaseModel):
    callback_data: str = Field(
        ...,
        description=(
            "Discrete event: button tap or command trigger. Mirrors the "
            "Telegram callback_data scheme — see circle.web.dispatch."
        ),
    )


class AckResponse(BaseModel):
    """Returned by /message and /callback once the controller has fully
    drained. Real-time output flows over the SSE stream — this is just an
    acknowledgement."""

    status: str = "ok"


class ErrorResponse(BaseModel):
    code: str
    error: str


def _ensure_session_match(context: BotContext, session_id: str) -> None:
    """Multi-session is out of scope for now — reject mismatched session IDs."""
    if session_id != context.config.session.session_id:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "session_not_found",
                "error": f"Unknown session {session_id!r}",
            },
        )


def create_app(context: BotContext) -> FastAPI:
    """Build a FastAPI app bound to the given runtime context.

    The app holds a reference to the BotContext via closure; routes use it
    to validate the session, claim names, and load participant state.
    The SSEHub is owned by the app and lives for the process lifetime.
    """
    app = FastAPI(
        title="Tejido — Web Adapter",
        description=(
            "AI-facilitated group deliberation. Web entry point for "
            "participants. The Telegram adapter shares the same backend."
        ),
    )
    sse_hub = SSEHub()
    # Expose the hub for tests / introspection (not part of the HTTP API).
    app.state.sse_hub = sse_hub
    app.state.context = context

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(
            url=f"/s/{context.config.session.session_id}",
            status_code=307,
        )

    @app.get("/s/{session_id}", response_class=HTMLResponse, include_in_schema=False)
    async def session_page(
        session_id: Annotated[str, PathParam(pattern=_SESSION_ID_PATTERN)],
    ) -> HTMLResponse:
        _ensure_session_match(context, session_id)
        return HTMLResponse(_PLACEHOLDER_HTML.replace("{{SESSION_ID}}", session_id))

    @app.post(
        "/api/s/{session_id}/join",
        response_model=JoinResponse,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid name"},
            404: {"model": ErrorResponse, "description": "Session not found"},
            409: {"model": ErrorResponse, "description": "Name already taken"},
        },
    )
    async def join(
        session_id: Annotated[str, PathParam(pattern=_SESSION_ID_PATTERN)],
        body: JoinRequest,
    ) -> JoinResponse:
        _ensure_session_match(context, session_id)

        try:
            participant_id, display_name = claim_name(
                context.config.data_dir, body.name
            )
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

        # Materialize the participant: writes the JSON file and registers
        # the entry in _index.json. Subsequent calls with this
        # participant_id will load instead of re-creating.
        async with context.lock_for(participant_id):
            context.load_or_create(participant_id, display_name)

        logger.info(
            "web join session=%s participant_id=%s display_name=%s",
            session_id,
            participant_id,
            display_name,
        )
        return JoinResponse(
            participant_id=participant_id, display_name=display_name
        )

    @app.get(
        "/api/p/{participant_id}/state",
        response_model=StateResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def get_state(
        participant_id: Annotated[str, PathParam(pattern=_PARTICIPANT_ID_PATTERN)],
    ) -> StateResponse:
        raw = load_participant(context.config.data_dir, participant_id)
        if raw is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "participant_not_found",
                    "error": "No participant with that id in this session",
                },
            )
        return StateResponse(**_state_for_response(raw))

    @app.post(
        "/api/p/{participant_id}/message",
        response_model=AckResponse,
        responses={404: {"model": ErrorResponse}},
    )
    async def post_message(
        participant_id: Annotated[str, PathParam(pattern=_PARTICIPANT_ID_PATTERN)],
        body: MessageRequest,
    ) -> AckResponse:
        display_name = _require_participant(context, participant_id)

        # Iterate the controller's async generator, broadcasting each
        # OutboundAction as an SSE event. The controller may take several
        # seconds (LLM call); the POST blocks until it completes, but the
        # frontend has been receiving events live during that wait.
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
        return AckResponse()

    @app.post(
        "/api/p/{participant_id}/callback",
        response_model=AckResponse,
        responses={
            400: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
        },
    )
    async def post_callback(
        participant_id: Annotated[str, PathParam(pattern=_PARTICIPANT_ID_PATTERN)],
        body: CallbackRequest,
    ) -> AckResponse:
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
        return AckResponse()

    @app.get("/api/p/{participant_id}/events")
    async def get_events(
        participant_id: Annotated[str, PathParam(pattern=_PARTICIPANT_ID_PATTERN)],
    ) -> StreamingResponse:
        # 404 a non-existent participant up front so the frontend doesn't
        # silently subscribe to events that will never arrive.
        _require_participant(context, participant_id)

        async def event_stream() -> AsyncIterator[bytes]:
            async with sse_hub.subscribe(participant_id) as queue:
                # Initial readiness ping so the client knows the stream is open.
                yield b"event: ready\ndata: {}\n\n"
                while True:
                    event = await queue.get()
                    yield f"data: {json.dumps(event)}\n\n".encode("utf-8")

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                # Disable proxy buffering so events flush in real time.
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app


def _require_participant(context: BotContext, participant_id: str) -> str:
    """Return the participant's display_name, or raise 404."""
    raw = load_participant(context.config.data_dir, participant_id)
    if raw is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "participant_not_found",
                "error": "No participant with that id in this session",
            },
        )
    return str(raw.get("participant_name", ""))


def _state_for_response(raw: dict) -> dict:
    """Pick a stable subset of the on-disk JSON for the state endpoint.

    Keeps the response shape independent of internal-only fields like
    `phase_entered_at` and `current_point_index` so the frontend never
    accidentally relies on them.
    """
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
    }


# ---------------------------------------------------------------------------
# Placeholder HTML — used for manual smoke testing until the React frontend
# lands in commit 4. Vanilla HTML/JS, ~50 lines. Wired to /join so you can
# exercise the backend in a browser without curl.

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
    button:hover { background: #444; }
    .error { color: #b00020; margin-top: 0.5em; min-height: 1.2em; }
    .ok    { color: #006400; margin-top: 0.5em; }
    pre    { background: #f4f4f4; padding: 1em; border-radius: 4px;
             overflow-x: auto; font-size: 0.85em; }
  </style>
</head>
<body>
  <h1>Tejido — session {{SESSION_ID}}</h1>
  <p>This is a smoke-test placeholder. The real chat UI ships in a later commit.</p>

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
      err.textContent = "";
      ok.textContent  = "";

      const r = await fetch(`/api/s/${SESSION_ID}/join`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name}),
      });
      const data = await r.json();
      if (!r.ok) {
        err.textContent = (data.detail && data.detail.error) || "Join failed.";
        return;
      }

      localStorage.setItem(`tejido:${SESSION_ID}:participant_id`, data.participant_id);
      ok.textContent = `Joined as ${data.display_name} (id ${data.participant_id})`;

      const s = await fetch(`/api/p/${data.participant_id}/state`).then(r => r.json());
      const pre = document.getElementById("state");
      pre.hidden = false;
      pre.textContent = JSON.stringify(s, null, 2);
    });
  </script>
</body>
</html>
"""
