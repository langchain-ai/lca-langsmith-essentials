"""Starlette app that serves the LangSlice customer UI.

Registered as a custom route in ``langgraph.json`` via ``http.app``, so
``uv run langgraph dev`` serves Studio, the LangGraph API, and this UI from one
process on one port:

    http://127.0.0.1:2024/          <- this UI
    http://127.0.0.1:2024/docs      <- the API the UI talks to

Routes live under ``/ui/`` so they cannot shadow a real LangGraph API route
(``/threads``, ``/runs``, ...). Custom routes are matched *before* the platform's
own, and ``/`` is the one platform route that is explicitly shadowable.

The order panel reads ``database.ORDERS`` directly rather than over HTTP: order
state is process-local, and this app runs in the same process as the graph. That
is also the point of the panel - it shows what the tools actually did, next to
what the agent said they did.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

import database as db
from agent import MODEL_NAME
from ui.agent_client import create_client, create_thread, get_history, stream_response
from ui.deployment import get_deployment_url

UI_DIR = Path(__file__).parent

#: New on every server start. The browser stores it next to its conversation
#: list and throws the list away when it changes, so restarting
#: ``uv run langgraph dev`` starts a fresh conversation instead of resuming a
#: half-finished one - which LangSmith would otherwise log as a new thread
#: picking up mid-order. In-process order state (``database.ORDERS``) is gone
#: after a restart anyway; only the checkpointed transcript survives.
SERVER_ID = uuid.uuid4().hex

# One client per server URL. The URL is derived per request (see deployment.py),
# but in practice there is exactly one, so this is a cache of size 1.
_clients: dict[str, object] = {}


def _client(request: Request):
    url = get_deployment_url(request)
    if url not in _clients:
        _clients[url] = create_client(url)
    return _clients[url]


def _tracing_enabled() -> bool:
    return os.getenv("LANGSMITH_TRACING", "").strip().lower() in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Page + session
# ---------------------------------------------------------------------------


async def index(request: Request) -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


async def robot(request: Request) -> FileResponse:
    """The mascot in the page header. Under ``/ui/`` like the rest, so it cannot
    shadow a platform route."""
    return FileResponse(UI_DIR / "robot.png", media_type="image/png")


async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def config(request: Request) -> JSONResponse:
    """Everything the sidebar's Session block needs, resolved server side."""
    return JSONResponse(
        {
            "server_id": SERVER_ID,
            "model": MODEL_NAME,
            "tracing": _tracing_enabled(),
            "project": os.getenv("LANGSMITH_PROJECT", "default"),
        }
    )


async def new_thread(request: Request) -> JSONResponse:
    thread_id = await create_thread(_client(request))
    return JSONResponse({"thread_id": thread_id})


async def history(request: Request) -> JSONResponse:
    """Replay a thread's transcript, so a page reload is not a lost conversation."""
    thread_id = request.query_params.get("thread_id")
    if not thread_id:
        return JSONResponse({"error": "thread_id is required"}, status_code=400)
    try:
        messages = await get_history(_client(request), thread_id)
    except Exception as exc:  # noqa: BLE001 - a stale thread id is the common case
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=404)
    return JSONResponse({"messages": messages})


# ---------------------------------------------------------------------------
# Order panel
# ---------------------------------------------------------------------------


async def order(request: Request) -> JSONResponse:
    thread_id = request.query_params.get("thread_id")
    if not thread_id:
        return JSONResponse({"error": "thread_id is required"}, status_code=400)
    current = db.get_order(thread_id)
    if current is None:
        return JSONResponse({"order": None})
    return JSONResponse({"order": db.order_summary(current)})


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


async def chat(request: Request) -> StreamingResponse:
    """Stream one turn as newline-delimited JSON events.

    NDJSON rather than raw text because a turn can fail *after* it has already
    streamed prose and already mutated the order. Framing the stream lets the
    page show the partial reply and the failure together, instead of the reply
    just stopping mid-sentence.
    """
    body = await request.json()
    message = (body.get("message") or "").strip()
    thread_id = body.get("thread_id")

    async def events():
        if not message or not thread_id:
            yield json.dumps({"type": "error", "message": "message and thread_id are required"}) + "\n"
            return
        try:
            async for token in stream_response(_client(request), thread_id, message):
                yield json.dumps({"type": "token", "text": token}) + "\n"
        except Exception as exc:  # noqa: BLE001 - surfaced to the tester, not swallowed
            yield json.dumps({"type": "error", "message": f"{type(exc).__name__}: {exc}"}) + "\n"
            return
        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


app = Starlette(
    routes=[
        Route("/", index, methods=["GET"]),
        Route("/healthz", healthz, methods=["GET"]),
        Route("/ui/robot.png", robot, methods=["GET"]),
        Route("/ui/config", config, methods=["GET"]),
        Route("/ui/thread", new_thread, methods=["POST"]),
        Route("/ui/history", history, methods=["GET"]),
        Route("/ui/order", order, methods=["GET"]),
        Route("/ui/chat", chat, methods=["POST"]),
    ]
)
