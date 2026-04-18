"""Launch HUBERT CAD in a standalone native window (pywebview).
Run directly: python cad_popup.py
Or call launch() from another thread — it starts the server then opens a window.
"""
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

_BASE = Path(__file__).parent
_SERVER = _BASE / "cad_server.py"
_PORT = 7474
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
    subprocess.Popen(
        [sys.executable, str(_SERVER)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        time.sleep(0.5)
        if _is_running():
            return True
    return False


def launch():
    """Start server and open a native window. Blocks until window is closed."""
    _ensure_server()
    try:
        import webview
        webview.create_window(
            "HUBERT CAD",
            _URL,
            width=1440,
            height=920,
            resizable=True,
            min_size=(900, 600),
        )
        webview.start()
    except ImportError:
        import webbrowser
        webbrowser.open(_URL)
        print(f"pywebview not installed — opened in browser: {_URL}")


if __name__ == "__main__":
    launch()
