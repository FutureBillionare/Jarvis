"""
Alcohol Getter Popup Launcher — opens the UI in a native pywebview window.

Usage:
    python -m alcohol_workflow.popup   # start server + open window
    from alcohol_workflow.popup import launch; launch()
"""

import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

_BASE   = Path(__file__).parent
_PORT   = 8878
_URL    = f"http://localhost:{_PORT}"
_MODULE = "alcohol_workflow.popup_server"


def _is_running() -> bool:
    try:
        urllib.request.urlopen(_URL + "/status", timeout=1)
        return True
    except Exception:
        return False


def _ensure_server() -> bool:
    if _is_running():
        return True

    jarvis_root = str(_BASE.parent)
    subprocess.Popen(
        [sys.executable, "-m", _MODULE],
        cwd=jarvis_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):          # wait up to 20s for server + data fetch
        time.sleep(0.5)
        if _is_running():
            return True
    return False


def launch(block: bool = True):
    """Start server and open native window. Blocks until window is closed if block=True."""
    print("[HUBERT] Fetching your location and nearby spots...")
    ok = _ensure_server()
    if not ok:
        print("[HUBERT] Server failed to start — opening in browser instead.")

    try:
        import webview

        api = _PyWebViewAPI()

        win = webview.create_window(
            "HUBERT — Alcohol Getter",
            _URL,
            width=1060,
            height=700,
            resizable=True,
            min_size=(760, 520),
            js_api=api,
        )
        if block:
            webview.start()
        else:
            t = threading.Thread(target=webview.start, daemon=True)
            t.start()

    except ImportError:
        print("[HUBERT] pywebview is not installed. Run: pip install pywebview")


class _PyWebViewAPI:
    """Exposed to JS via pywebview.api.* for the Satisfied button."""
    def close(self):
        import webview
        for w in webview.windows:
            w.destroy()


if __name__ == "__main__":
    launch()
