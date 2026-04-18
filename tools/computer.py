"""
Computer control tools — keyboard, mouse, files, processes, system info.
"""
import subprocess
import os
import shutil
import psutil
import platform
import pyperclip
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
    _PYAUTOGUI_OK = True
except Exception:
    pyautogui = None
    _PYAUTOGUI_OK = False

def _no_gui(name):
    return f"{name} unavailable — pyautogui failed to load on this platform."


def _run_command(p):
    cmd = p["command"]
    timeout = p.get("timeout", 30)
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )
    out = result.stdout.strip()
    err = result.stderr.strip()
    if out and err:
        return f"STDOUT:\n{out}\nSTDERR:\n{err}"
    return out or err or "(no output)"


def _open_application(p):
    app = p["app_name"]
    try:
        if platform.system() == "Windows":
            os.startfile(app)
        else:
            subprocess.Popen([app])
        return f"Opened {app}"
    except Exception as e:
        # Try with subprocess
        try:
            subprocess.Popen(app, shell=True)
            return f"Launched: {app}"
        except Exception as e2:
            return f"Error opening {app}: {e2}"


def _take_screenshot(p):
    if not _PYAUTOGUI_OK: return _no_gui("screenshot")
    import tempfile
    path = p.get("save_path", str(Path(tempfile.gettempdir()) / "jarvis_screenshot.png"))
    img = pyautogui.screenshot()
    img.save(path)
    return f"Screenshot saved to: {path}  (size: {img.size[0]}x{img.size[1]})"


def _click_at(p):
    if not _PYAUTOGUI_OK: return _no_gui("click_at")
    x, y = p["x"], p["y"]
    btn = p.get("button", "left")
    clicks = p.get("clicks", 1)
    pyautogui.click(x, y, clicks=clicks, button=btn)
    return f"Clicked {btn} at ({x}, {y}) × {clicks}"


def _move_mouse(p):
    if not _PYAUTOGUI_OK: return _no_gui("move_mouse")
    x, y = p["x"], p["y"]
    duration = p.get("duration", 0.2)
    pyautogui.moveTo(x, y, duration=duration)
    return f"Mouse moved to ({x}, {y})"


def _type_text(p):
    if not _PYAUTOGUI_OK: return _no_gui("type_text")
    text = p["text"]
    interval = p.get("interval", 0.02)
    pyautogui.typewrite(text, interval=interval)
    return f"Typed: {text[:60]}{'...' if len(text) > 60 else ''}"


def _press_key(p):
    if not _PYAUTOGUI_OK: return _no_gui("press_key")
    keys = p["keys"]
    if isinstance(keys, str):
        keys = [keys]
    pyautogui.hotkey(*keys)
    return f"Pressed: {'+'.join(keys)}"


def _scroll(p):
    if not _PYAUTOGUI_OK: return _no_gui("scroll")
    x = p.get("x", None)
    y = p.get("y", None)
    amount = p.get("amount", 3)
    if x is not None and y is not None:
        pyautogui.scroll(amount, x=x, y=y)
    else:
        pyautogui.scroll(amount)
    return f"Scrolled {amount} clicks"


def _get_clipboard(p):
    return pyperclip.paste() or "(clipboard is empty)"


def _set_clipboard(p):
    text = p["text"]
    pyperclip.copy(text)
    return f"Clipboard set to: {text[:80]}{'...' if len(text) > 80 else ''}"


def _list_files(p):
    path = p.get("path", ".")
    show_hidden = p.get("show_hidden", False)
    try:
        entries = list(Path(path).iterdir())
        if not show_hidden:
            entries = [e for e in entries if not e.name.startswith(".")]
        entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))
        lines = []
        for e in entries[:100]:
            tag = "[DIR] " if e.is_dir() else "      "
            lines.append(f"{tag}{e.name}")
        result = f"Contents of {path}:\n" + "\n".join(lines)
        if len(entries) > 100:
            result += f"\n... and {len(entries)-100} more"
        return result
    except Exception as e:
        return f"Error: {e}"


def _read_file(p):
    path = p["path"]
    max_chars = p.get("max_chars", 8000)
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n... (truncated, {len(content)} total chars)"
        return content
    except Exception as e:
        return f"Error reading {path}: {e}"


def _write_file(p):
    path = p["path"]
    content = p["content"]
    mode = p.get("mode", "w")
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, mode, encoding="utf-8") as f:
            f.write(content)
        return f"Written to {path} ({len(content)} chars)"
    except Exception as e:
        return f"Error writing {path}: {e}"


def _get_system_info(p):
    info = {
        "OS": platform.system() + " " + platform.release(),
        "CPU": platform.processor(),
        "CPU cores": psutil.cpu_count(logical=True),
        "CPU usage": f"{psutil.cpu_percent(interval=0.5)}%",
        "RAM total": f"{psutil.virtual_memory().total // (1024**3)} GB",
        "RAM used": f"{psutil.virtual_memory().percent}%",
        "Disk": f"{psutil.disk_usage('/').percent}% used",
        "Python": platform.python_version(),
    }
    return "\n".join(f"{k}: {v}" for k, v in info.items())


def _list_processes(p):
    name_filter = p.get("filter", "").lower()
    procs = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            if not name_filter or name_filter in proc.info["name"].lower():
                procs.append(
                    f"PID {proc.info['pid']:6d}  CPU:{proc.info['cpu_percent']:5.1f}%"
                    f"  MEM:{proc.info['memory_percent']:4.1f}%  {proc.info['name']}"
                )
        except Exception:
            pass
    procs = procs[:50]
    return "\n".join(procs) if procs else "No matching processes"


def _get_screen_size(p):
    if not _PYAUTOGUI_OK: return _no_gui("get_screen_size")
    size = pyautogui.size()
    return f"Screen: {size.width} × {size.height} pixels"


TOOLS = [
    (
        {
            "name": "run_command",
            "description": "Execute a shell command and return its output. Use for opening apps, file operations, running scripts, etc.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to run"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
                },
                "required": ["command"],
            },
        },
        _run_command,
    ),
    (
        {
            "name": "open_application",
            "description": "Open an application by name or path (e.g. 'notepad', 'chrome', 'C:/path/to/app.exe')",
            "input_schema": {
                "type": "object",
                "properties": {"app_name": {"type": "string", "description": "Application name or path"}},
                "required": ["app_name"],
            },
        },
        _open_application,
    ),
    (
        {
            "name": "take_screenshot",
            "description": "Capture the current screen and save it to a file",
            "input_schema": {
                "type": "object",
                "properties": {"save_path": {"type": "string", "description": "Optional path to save the screenshot"}},
            },
        },
        _take_screenshot,
    ),
    (
        {
            "name": "click_at",
            "description": "Click at specific screen coordinates",
            "input_schema": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "Mouse button"},
                    "clicks": {"type": "integer", "description": "Number of clicks (1 or 2 for double-click)"},
                },
                "required": ["x", "y"],
            },
        },
        _click_at,
    ),
    (
        {
            "name": "move_mouse",
            "description": "Move the mouse cursor to coordinates",
            "input_schema": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "duration": {"type": "number", "description": "Movement duration in seconds"},
                },
                "required": ["x", "y"],
            },
        },
        _move_mouse,
    ),
    (
        {
            "name": "type_text",
            "description": "Type text using the keyboard",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type (printable ASCII only)"},
                    "interval": {"type": "number", "description": "Delay between keystrokes in seconds"},
                },
                "required": ["text"],
            },
        },
        _type_text,
    ),
    (
        {
            "name": "press_key",
            "description": "Press keyboard keys or hotkey combinations (e.g. ['ctrl','c'], ['win'], ['alt','f4'])",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keys": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ],
                        "description": "Key or list of keys to press simultaneously",
                    }
                },
                "required": ["keys"],
            },
        },
        _press_key,
    ),
    (
        {
            "name": "scroll",
            "description": "Scroll the mouse wheel",
            "input_schema": {
                "type": "object",
                "properties": {
                    "amount": {"type": "integer", "description": "Positive = up, negative = down"},
                    "x": {"type": "integer", "description": "X coordinate (optional)"},
                    "y": {"type": "integer", "description": "Y coordinate (optional)"},
                },
                "required": ["amount"],
            },
        },
        _scroll,
    ),
    (
        {
            "name": "get_clipboard",
            "description": "Read the current clipboard contents",
            "input_schema": {"type": "object", "properties": {}},
        },
        _get_clipboard,
    ),
    (
        {
            "name": "set_clipboard",
            "description": "Set the clipboard contents",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
        _set_clipboard,
    ),
    (
        {
            "name": "list_files",
            "description": "List files and directories at a path",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default: current directory)"},
                    "show_hidden": {"type": "boolean"},
                },
            },
        },
        _list_files,
    ),
    (
        {
            "name": "read_file",
            "description": "Read the contents of a file",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer", "description": "Max characters to return (default 8000)"},
                },
                "required": ["path"],
            },
        },
        _read_file,
    ),
    (
        {
            "name": "write_file",
            "description": "Write content to a file",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "mode": {"type": "string", "enum": ["w", "a"], "description": "w=overwrite, a=append"},
                },
                "required": ["path", "content"],
            },
        },
        _write_file,
    ),
    (
        {
            "name": "get_system_info",
            "description": "Get OS, CPU, RAM, disk information",
            "input_schema": {"type": "object", "properties": {}},
        },
        _get_system_info,
    ),
    (
        {
            "name": "list_processes",
            "description": "List running processes",
            "input_schema": {
                "type": "object",
                "properties": {"filter": {"type": "string", "description": "Filter by name (optional)"}},
            },
        },
        _list_processes,
    ),
    (
        {
            "name": "get_screen_size",
            "description": "Get the screen resolution in pixels",
            "input_schema": {"type": "object", "properties": {}},
        },
        _get_screen_size,
    ),
]
