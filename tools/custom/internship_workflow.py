"""
Tool: internship_workflow
Description: Run the engineering internship automated workflow. Opens a visual
popup showing real-time progress (search → filter → apply → record), runs
the 30-minute research phase, applies to new internships, and returns a
summary of what was applied to. Trigger with: "run the internship getter".
"""

import json
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

_BASE   = Path(__file__).parent.parent
_POPUP  = _BASE / "internship_workflow" / "popup.py"
_PORT   = 8877
_URL    = f"http://localhost:{_PORT}"

TOOL_DEFINITION = {
    "name": "internship_workflow",
    "description": (
        "Run the engineering internship automated workflow. "
        "Opens a visual popup, searches the web for July-August engineering internships, "
        "cross-checks against already-applied, auto-fills applications, and records results "
        "to Google Sheets. Say 'run the internship getter' to trigger this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform: 'run' (default), 'status', 'list_applied'",
                "enum": ["run", "status", "list_applied"]
            }
        },
        "required": []
    }
}


def _is_server_running() -> bool:
    try:
        urllib.request.urlopen(_URL, timeout=2)
        return True
    except Exception:
        return False


def _ensure_server():
    if _is_server_running():
        return True
    subprocess.Popen(
        [sys.executable, "-m", "internship_workflow.popup_server"],
        cwd=str(_BASE),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        time.sleep(0.5)
        if _is_server_running():
            return True
    return False


def _open_popup():
    """Open pywebview window in a background thread."""
    try:
        import webview
        def _run():
            webview.create_window(
                "HUBERT — Internship Workflow",
                _URL,
                width=1100,
                height=720,
                resizable=True,
                min_size=(800, 560),
            )
            webview.start()
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return True
    except ImportError:
        import webbrowser
        webbrowser.open(_URL)
        return False


def _post_run() -> dict:
    try:
        req = urllib.request.Request(f"{_URL}/run", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}


def _get_status() -> dict:
    try:
        with urllib.request.urlopen(f"{_URL}/status", timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}


def _poll_for_completion(timeout_s: int = 7200) -> dict:
    """Poll /status every 10s until run completes or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(10)
        status = _get_status()
        if not status.get("running", True):
            return status
    return {"error": "Workflow timed out"}


def run(params: dict) -> str:
    action = params.get("action", "run")

    if action == "status":
        status = _get_status()
        if status.get("error"):
            return f"Server not running. Start with action='run'."
        running = status.get("running", False)
        result = status.get("result")
        if running:
            return "Workflow is currently running."
        if result:
            applied = result.get("applied_count", 0)
            found   = result.get("found_count", 0)
            return f"Last run: found={found}, applied={applied}."
        return "Server is up. No run completed yet."

    if action == "list_applied":
        import sys
        sys.path.insert(0, str(_BASE))
        from internship_workflow.storage import InternshipStorage
        storage = InternshipStorage()
        applied = storage.get_all_applied()
        if not applied:
            return "No internships have been applied to yet."
        lines = ["Applied Internships:"]
        for i, item in enumerate(applied[-20:], 1):
            title   = item.get("Title", item.get("title", "Unknown"))
            company = item.get("Company", item.get("company", "Unknown"))
            loc     = item.get("Location", item.get("location", ""))
            date    = item.get("Applied At", item.get("applied_at", ""))[:10]
            lines.append(f"  {i}. {title} @ {company} ({loc}) — {date}")
        return "\n".join(lines)

    # action == "run"
    # 1. Ensure server is running
    server_ok = _ensure_server()
    if not server_ok:
        return "Failed to start internship workflow server. Check logs."

    # 2. Open visual popup
    has_webview = _open_popup()
    popup_msg = "Popup opened." if has_webview else "Browser tab opened (pywebview not installed)."

    # 3. Trigger the run
    trigger = _post_run()
    if trigger.get("status") == "already_running":
        return f"{popup_msg} Workflow is already running — check the popup for live progress."
    if trigger.get("error"):
        return f"Server error: {trigger['error']}"

    # 4. Poll for completion
    status = _poll_for_completion()
    if status.get("error"):
        return f"Workflow error: {status['error']}"

    result = status.get("result", {})
    applied_listings = result.get("applied_listings", [])

    lines = [
        f"Internship workflow complete.",
        f"  Found:   {result.get('found_count', 0)} listings",
        f"  New:     {result.get('new_count', 0)} not-yet-applied",
        f"  Applied: {result.get('applied_count', 0)}",
        "",
    ]

    if applied_listings:
        lines.append("Applied to:")
        for item in applied_listings:
            lines.append(f"  • {item['title']} @ {item['company']} ({item.get('location', '')})")
    else:
        lines.append("No new internships were applied to this run.")

    lines.append("")
    lines.append("Results saved to 'Internships Applied' Google Sheet.")

    return "\n".join(lines)


TOOLS = [(TOOL_DEFINITION, run)]
