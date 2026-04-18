"""
Popup Server — FastAPI + WebSocket backend for the internship workflow UI.

Listens on port 8877.
  GET  /         → serves popup.html
  WS   /ws       → streams live workflow events to the browser
  POST /run      → triggers the workflow (used by scheduler & HUBERT tool)
  GET  /status   → returns current run state as JSON
"""

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

log = logging.getLogger(__name__)

_BASE = Path(__file__).parent
_HTML = _BASE / "popup.html"
_PORT = 8877

app = FastAPI(title="HUBERT Internship Workflow")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ── Connection Manager ────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._active: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._active.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._active.discard(ws)

    async def broadcast(self, data: dict):
        msg = json.dumps(data)
        dead = set()
        for ws in list(self._active):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            await self.disconnect(ws)


manager = ConnectionManager()

# ── Run State ─────────────────────────────────────────────────────────────────

_run_state = {
    "running": False,
    "result": None,
    "error": None,
}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def serve_ui():
    return FileResponse(str(_HTML), media_type="text/html")


@app.get("/status")
def get_status():
    return JSONResponse(_run_state)


@app.post("/run")
async def trigger_run():
    if _run_state["running"]:
        return JSONResponse({"status": "already_running"})

    asyncio.create_task(_run_workflow_async())
    return JSONResponse({"status": "started"})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()   # keep alive
    except WebSocketDisconnect:
        await manager.disconnect(ws)


# ── Workflow Runner ────────────────────────────────────────────────────────────

def _make_status_cb():
    """Returns a thread-safe status callback that queues events for the event loop."""
    loop = asyncio.get_event_loop()

    def cb(phase: str, message: str, count: int = 0):
        payload = {"phase": phase, "message": message, "count": count}
        asyncio.run_coroutine_threadsafe(manager.broadcast(payload), loop)

    return cb


async def _run_workflow_async():
    _run_state["running"] = True
    _run_state["error"] = None
    _run_state["result"] = None

    await manager.broadcast({"phase": "start", "message": "HUBERT Internship Workflow starting...", "count": 0})

    try:
        # Import here to avoid circular imports at startup
        import sys
        sys.path.insert(0, str(_BASE.parent))
        from internship_workflow.orchestrator import WorkflowOrchestrator

        loop = asyncio.get_event_loop()

        def cb(phase: str, message: str, count: int = 0):
            payload = {"phase": phase, "message": message, "count": count}
            asyncio.run_coroutine_threadsafe(manager.broadcast(payload), loop)

        def run_in_thread():
            orch = WorkflowOrchestrator(status_cb=cb)
            return orch.run()

        result = await asyncio.to_thread(run_in_thread)
        _run_state["result"] = result

        # Broadcast final summary
        applied = result.get("applied_listings", [])
        summary = {
            "phase": "done",
            "message": (
                f"Done. Found {result['found_count']}, "
                f"new {result['new_count']}, "
                f"applied {result['applied_count']}."
            ),
            "count": result["applied_count"],
            "applied_listings": [
                {"title": l["title"], "company": l["company"], "location": l["location"]}
                for l in applied
            ],
        }
        await manager.broadcast(summary)

    except Exception as e:
        log.exception("Workflow run error")
        _run_state["error"] = str(e)
        await manager.broadcast({"phase": "error", "message": str(e), "count": 0})

    finally:
        _run_state["running"] = False


# ── Entry Point ───────────────────────────────────────────────────────────────

def start_server(host="127.0.0.1", port=_PORT, open_browser=False):
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    if open_browser:
        import threading, webbrowser, time
        def _open():
            time.sleep(1.2)
            webbrowser.open(f"http://{host}:{port}")
        threading.Thread(target=_open, daemon=True).start()

    server.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_server(open_browser=True)
