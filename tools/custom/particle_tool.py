"""
Tool: particle_tool
Description: Launch HUBERT's AI Particle Simulator — opens a browser-based
Three.js WebGL particle system where you describe any effect in plain English
and Claude generates real-time physics-based particles instantly.
"""
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

_BASE = Path(__file__).parent.parent.parent
_SERVER = _BASE / "particle_server.py"
_PORT = 7575
_server_proc: subprocess.Popen | None = None
_lock = threading.Lock()


def _is_running() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"http://localhost:{_PORT}/", timeout=1)
        return True
    except Exception:
        return False


def run_launch_particles(params: dict) -> str:
    global _server_proc
    with _lock:
        if _is_running():
            webbrowser.open(f"http://localhost:{_PORT}")
            return f"Particle Simulator already running — opened http://localhost:{_PORT}"

        _server_proc = subprocess.Popen(
            [sys.executable, str(_SERVER)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    import time
    for _ in range(20):
        time.sleep(0.5)
        if _is_running():
            webbrowser.open(f"http://localhost:{_PORT}")
            return (
                "HUBERT Particle Simulator launched — http://localhost:7575\n"
                "Type any description (e.g. 'blue galaxy spiral') and press Generate. "
                "Use the preset buttons for instant effects, or tweak sliders in real-time."
            )

    return "Particle server started but not yet responding — try http://localhost:7575 in a moment."


def run_stop_particles(params: dict) -> str:
    global _server_proc
    with _lock:
        if _server_proc and _server_proc.poll() is None:
            _server_proc.terminate()
            _server_proc = None
            return "Particle Simulator server stopped."
        return "Particle Simulator is not running."


TOOLS = [
    (
        {
            "name": "launch_particle_simulator",
            "description": (
                "Launch the HUBERT AI Particle Simulator in the browser. "
                "Opens a Three.js WebGL particle system where the user can type any "
                "natural language description (e.g. 'red fire explosion', 'galaxy spiral', "
                "'blue ocean waves') and Claude instantly generates a matching real-time "
                "particle physics simulation with interactive mouse controls and presets. "
                "Trigger phrases: 'open the particle simulator', 'launch particles', "
                "'open particle sim', 'particle simulator'."
            ),
            "input_schema": {"type": "object", "properties": {}},
        },
        run_launch_particles,
    ),
    (
        {
            "name": "stop_particle_simulator",
            "description": "Stop the HUBERT Particle Simulator server.",
            "input_schema": {"type": "object", "properties": {}},
        },
        run_stop_particles,
    ),
]
