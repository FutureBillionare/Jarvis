"""
Tool: cad_tool
Description: Launch HUBERT's text-to-3D CAD designer — opens a native popup window
where you can describe any 3D object in plain English and get an interactive
OpenSCAD model with approve/reject/export controls.
"""
import subprocess
import sys
import threading
from pathlib import Path

_BASE = Path(__file__).parent.parent.parent
_POPUP = _BASE / "cad_popup.py"
_SERVER = _BASE / "cad_server.py"
_PORT = 7474
_popup_proc: subprocess.Popen | None = None
_lock = threading.Lock()


def _is_running() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"http://localhost:{_PORT}/", timeout=1)
        return True
    except Exception:
        return False


def run_launch_cad(params: dict) -> str:
    global _popup_proc
    with _lock:
        # If window process already alive, just bring server up (window may have closed)
        if _popup_proc and _popup_proc.poll() is None:
            return "HUBERT CAD window is already open."

        # Launch cad_popup.py — it starts the server AND opens the native window
        _popup_proc = subprocess.Popen(
            [sys.executable, str(_POPUP)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    return (
        "HUBERT CAD popup launched — a native window will appear in a moment.\n"
        "Describe any 3D object (e.g. 'a drone body with motor mounts for brushless motors "
        "and a battery bay for a 3V cell') and press Generate. "
        "Approve, reject, or export STL when the model is ready."
    )


def run_stop_cad(params: dict) -> str:
    global _popup_proc
    with _lock:
        if _popup_proc and _popup_proc.poll() is None:
            _popup_proc.terminate()
            _popup_proc = None
            return "HUBERT CAD window closed and server stopped."
        return "HUBERT CAD is not running."


def run_cad_status(params: dict) -> str:
    running = _is_running()
    proc_alive = _popup_proc is not None and _popup_proc.poll() is None
    if running and proc_alive:
        return "HUBERT CAD is running — native window is open."
    elif running:
        return f"CAD server is running at http://localhost:{_PORT} (window may have closed)."
    else:
        return "HUBERT CAD is not running. Use launch_cad to start it."


TOOLS = [
    (
        {
            "name": "launch_cad",
            "description": (
                "Launch the HUBERT text-to-3D CAD designer in a native popup window. "
                "Starts a local server and opens the UI where the user can describe "
                "any 3D object in plain English — including complex engineering designs "
                "like drone bodies with motor mounts, battery bays, and FC stack patterns, "
                "mechanical parts, architectural forms, or any custom 3D shape. "
                "Supports orthographic drawing file attachments and live OpenSCAD preview. "
                "Trigger phrases: 'open the CAD tool', 'launch HUBERT CAD', 'open CAD', "
                "'design a 3D model', 'make a drone body', 'text to 3D'."
            ),
            "input_schema": {"type": "object", "properties": {}},
        },
        run_launch_cad,
    ),
    (
        {
            "name": "stop_cad",
            "description": "Stop the HUBERT CAD server.",
            "input_schema": {"type": "object", "properties": {}},
        },
        run_stop_cad,
    ),
    (
        {
            "name": "cad_status",
            "description": "Check whether the HUBERT CAD server is running.",
            "input_schema": {"type": "object", "properties": {}},
        },
        run_cad_status,
    ),
]
