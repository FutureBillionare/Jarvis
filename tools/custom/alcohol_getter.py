"""
Tool: alcohol_getter
Description: Find nearby alcohol — identifies your location, shows the 5 nearest bars
and nearby stores (gas stations, convenience, liquor stores) that sell alcoholic beverages,
with Google Maps direction links and alcohol type descriptions.
Trigger phrases: "more alcohol", "alcohol please", "find me alcohol", "i need alcohol"

For adults 21+. No purchases are made.
"""

import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

_BASE  = Path(__file__).parent.parent
_PORT  = 8878
_URL   = f"http://localhost:{_PORT}"

TOOL_DEFINITION = {
    "name": "alcohol_getter",
    "description": (
        "Find nearby alcohol for adults 21+. "
        "Detects your device location, then shows the 5 nearest bars and nearby stores "
        "(gas stations, convenience stores, liquor stores) that sell alcohol. "
        "Opens a visual popup with Google Maps direction links and alcohol type info. "
        "No purchases are made. "
        "Trigger: 'more alcohol', 'alcohol please', 'find me alcohol', 'i need alcohol'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'run' (default) opens the popup; 'status' checks if server is running.",
                "enum": ["run", "status"]
            }
        },
        "required": []
    }
}


def _is_running() -> bool:
    try:
        urllib.request.urlopen(_URL + "/status", timeout=2)
        return True
    except Exception:
        return False


def _ensure_server() -> bool:
    if _is_running():
        return True
    subprocess.Popen(
        [sys.executable, "-m", "alcohol_workflow.popup_server"],
        cwd=str(_BASE),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        time.sleep(0.5)
        if _is_running():
            return True
    return False


def _open_popup() -> None:
    """Launch the popup as a detached subprocess so it owns the main thread."""
    subprocess.Popen(
        [sys.executable, "-m", "alcohol_workflow.popup"],
        cwd=str(_BASE),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # detach so it lives independently of the calling process
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                      | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def run(params: dict) -> str:
    action = params.get("action", "run")

    if action == "status":
        if _is_running():
            return "Alcohol Getter server is running at localhost:8878."
        return "Alcohol Getter server is not running."

    # action == "run"
    server_ok = _ensure_server()
    if not server_ok:
        return (
            "Failed to start the Alcohol Getter server. "
            f"Try running manually: python -m alcohol_workflow.popup"
        )

    _open_popup()
    return (
        "Alcohol Getter is open! Showing nearby bars and stores with directions. "
        "Click 'Satisfied' when you're done."
    )


TOOLS = [(TOOL_DEFINITION, run)]
