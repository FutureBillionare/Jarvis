"""
ui_bridge.py — Thread-safe command bus from HUBERT tools to the live UI.

Any thread (tool, background worker) calls push() to enqueue a command.
The UI main thread drains the queue every 25ms via pop_all().
"""
import queue as _q

_queue: _q.Queue = _q.Queue()


def push(cmd: str, **kwargs):
    """Push a UI command from any thread."""
    _queue.put({"cmd": cmd, **kwargs})


def pop_all() -> list:
    """Drain all pending commands. Must be called from the UI thread."""
    items = []
    try:
        while True:
            items.append(_queue.get_nowait())
    except _q.Empty:
        pass
    return items
