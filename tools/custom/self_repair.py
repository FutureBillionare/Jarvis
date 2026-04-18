"""
Tool: self_repair
Description: Run HUBERT self-diagnostics. Checks API key, network, tool
integrity, Ollama, required packages, and recent error log entries.
Returns a formatted diagnostic report.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

TOOL_DEFINITION = {
    "name": "self_repair",
    "description": (
        "Run HUBERT self-diagnostics and return a status report. "
        "Checks: API key present, network reachable, all tools load without errors, "
        "Ollama availability, required Python packages, recent error log entries. "
        "Use when HUBERT seems broken, slow, or when the user asks about system health."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "verbose": {
                "type": "boolean",
                "description": "Include full error log snippets (default: false)",
            }
        },
        "required": [],
    },
}


def _can_import(mod_name: str) -> bool:
    try:
        __import__(mod_name)
        return True
    except ImportError:
        return False


def run(params: dict) -> str:
    import importlib.util
    import datetime
    try:
        import requests as _requests
        _requests_ok = True
    except ImportError:
        _requests = None
        _requests_ok = False
    from config import get_api_key

    verbose = params.get("verbose", False)
    lines = ["HUBERT Self-Diagnostics", "=" * 26]

    # 1. API key
    try:
        key = get_api_key()
        lines.append(f"{'✓' if key else '✗'} API key: {'present' if key else 'MISSING'}")
    except Exception as e:
        lines.append(f"✗ API key check failed: {e}")

    # 2. Network
    if _requests_ok:
        try:
            _requests.head("https://api.anthropic.com", timeout=3)
            lines.append("✓ Network: reachable")
        except Exception:
            lines.append("✗ Network: UNREACHABLE")
    else:
        lines.append("⚠ Network: requests not installed")

    # 3. Tools
    tools_dir = Path(__file__).parent
    this_file = Path(__file__).name
    errors = []
    for f in sorted(tools_dir.glob("*.py")):
        if f.name == this_file:
            continue
        try:
            spec = importlib.util.spec_from_file_location(f.stem, f)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as e:
            errors.append(f"{f.name}: {e}")
    if errors:
        for err in errors:
            lines.append(f"✗ Tool load: {err}")
    else:
        lines.append("✓ Tools: all load OK")

    # 4. Ollama
    try:
        from ollama_core import OllamaCore
        lines.append(
            "✓ Ollama: online" if OllamaCore().ollama_available()
            else "⚠ Ollama: offline"
        )
    except Exception:
        lines.append("⚠ Ollama: unavailable")

    # 5. Packages
    pkg_checks = {
        "cv2": "opencv-python", "sounddevice": "sounddevice",
        "edge_tts": "edge-tts", "psutil": "psutil", "PIL": "Pillow",
    }
    missing = [pkg for mod, pkg in pkg_checks.items() if not _can_import(mod)]
    if missing:
        lines.append(f"⚠ Missing packages: {', '.join(missing)}")
    else:
        lines.append("✓ Packages: all present")

    # 6. Error log
    log_path = Path(__file__).parent.parent.parent / "hubert_errors.log"
    try:
        if log_path.exists():
            log_lines = log_path.read_text(
                encoding="utf-8", errors="replace").splitlines()
            cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
            recent = []
            for line in log_lines:
                if line.startswith("[") and len(line) > 20:
                    try:
                        ts = datetime.datetime.strptime(line[1:20],
                                                        "%Y-%m-%d %H:%M:%S")
                        if ts > cutoff:
                            recent.append(line)
                    except ValueError:
                        pass
            count = len(recent)
            if count == 0:
                lines.append("✓ Error log: no errors in 24h")
            else:
                lines.append(f"⚠ Error log: {count} error(s) in 24h")
                snippets = recent[-5:] if verbose else recent[-3:]
                for entry in snippets:
                    lines.append(f"  {entry[:120 if verbose else 80]}")
        else:
            lines.append("✓ Error log: not found (no errors yet)")
    except Exception as e:
        lines.append(f"⚠ Error log: read failed ({e})")

    return "\n".join(lines)


TOOLS = [(TOOL_DEFINITION, run)]
