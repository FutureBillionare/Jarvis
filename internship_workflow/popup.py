"""
Internship Workflow Popup Launcher — opens the workflow UI in a native pywebview window.

Usage:
    python popup.py          # start server + open window
    popup.launch()           # from another thread

Pattern mirrors cad_popup.py.
"""

import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

_BASE = Path(__file__).parent
_SERVER_MODULE = "internship_workflow.popup_server"
_PORT = 8877
_URL = f"http://localhost:{_PORT}"


def _is_running() -> bool:
    try:
        urllib.request.urlopen(_URL, timeout=1)
        return True
    except Exception:
        return False


def _ensure_server():
    if _is_running():
        return True

    # Launch popup_server as a subprocess
    jarvis_root = str(_BASE.parent)
    subprocess.Popen(
        [sys.executable, "-m", _SERVER_MODULE],
        cwd=jarvis_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        time.sleep(0.5)
        if _is_running():
            return True
    return False


def launch():
    """Start server and open native window. Blocks until window is closed."""
    ok = _ensure_server()
    if not ok:
        print("[internship popup] Server failed to start — opening in browser.")

    try:
        import webview
        webview.create_window(
            "HUBERT — Internship Workflow",
            _URL,
            width=1100,
            height=720,
            resizable=True,
            min_size=(800, 560),
        )
        webview.start()
    except ImportError:
        import webbrowser
        webbrowser.open(_URL)
        print(f"[internship popup] pywebview not installed — opened in browser: {_URL}")


def trigger_run():
    """POST /run to kick off the workflow (non-blocking)."""
    import urllib.request
    try:
        req = urllib.request.Request(
            f"{_URL}/run",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.read().decode()
    except Exception as e:
        return str(e)


if __name__ == "__main__":
    launch()
