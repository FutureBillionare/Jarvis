"""
Tool: claude_sync_status
Description: Check the status of the Claude config sync daemon — what's synced,
last sync time, pending changes, and skill inventory across machines.
"""

import subprocess
import json
from pathlib import Path
from datetime import datetime

SYNC_REPO = Path.home() / "claude-sync"
LOG_FILE  = SYNC_REPO / "sync.log"
SKILLS_DIR = Path.home() / ".claude" / "plugins" / "cache" / "local-antigravity" / "antigravity" / "1.0.0" / "skills"

TOOL_DEFINITION = {
    "name": "claude_sync_status",
    "description": (
        "Check the Claude config sync status. Shows last sync time, "
        "pending local changes, current skill inventory, and recent sync log. "
        "Use to verify both machines are in sync after adding new skills or plugins."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "One of: 'status' (default), 'force_push' (push local now), 'force_pull' (pull remote now), 'log' (last 20 log lines)"
            }
        },
        "required": []
    }
}


def _git(*args) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=SYNC_REPO,
                           capture_output=True, text=True)
        return r.stdout.strip()
    except Exception as e:
        return f"(git error: {e})"


def run(params: dict) -> str:
    action = params.get("action", "status").lower()

    if not SYNC_REPO.exists():
        return (
            "Sync repo not found at ~/claude-sync.\n"
            "Set it up first: the repo should be at C:/Users/Jake/claude-sync "
            "with a GitHub remote configured."
        )

    if action == "log":
        if not LOG_FILE.exists():
            return "No sync log found yet."
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        return "\n".join(lines[-20:])

    if action == "force_push":
        try:
            subprocess.run(["git", "add", "-A"], cwd=SYNC_REPO, check=True)
            msg = f"manual push @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            subprocess.run(["git", "commit", "-m", msg], cwd=SYNC_REPO)
            subprocess.run(["git", "push", "origin", "main"], cwd=SYNC_REPO, check=True)
            return "Force push complete."
        except Exception as e:
            return f"Force push failed: {e}"

    if action == "force_pull":
        try:
            subprocess.run(["git", "pull", "--rebase", "origin", "main"],
                           cwd=SYNC_REPO, check=True)
            return "Force pull complete. Restart Claude Code to reload plugins."
        except Exception as e:
            return f"Force pull failed: {e}"

    # Default: status
    lines = []

    # Git status
    status = _git("status", "--porcelain")
    last_commit = _git("log", "-1", "--format=%cr — %s")
    remote = _git("remote", "-v")
    has_remote = "origin" in remote

    lines.append("── Claude Config Sync Status ──")
    lines.append(f"Repo:        {SYNC_REPO}")
    lines.append(f"GitHub:      {'connected' if has_remote else 'NOT connected (local only)'}")
    lines.append(f"Last commit: {last_commit or 'none'}")

    if status:
        lines.append(f"Pending:     {len(status.splitlines())} uncommitted change(s)")
        for l in status.splitlines()[:5]:
            lines.append(f"             {l}")
    else:
        lines.append("Pending:     clean (nothing uncommitted)")

    # Skill inventory
    lines.append("")
    lines.append("── Installed Skills ──")
    if SKILLS_DIR.exists():
        skills = sorted(d.name for d in SKILLS_DIR.iterdir() if d.is_dir())
        for s in skills:
            lines.append(f"  ✓ {s}")
        lines.append(f"Total: {len(skills)} skills")
    else:
        lines.append("  (skills dir not found)")

    # Recent log
    lines.append("")
    lines.append("── Recent Sync Activity ──")
    if LOG_FILE.exists():
        recent = LOG_FILE.read_text(encoding="utf-8").splitlines()[-5:]
        lines.extend(recent)
    else:
        lines.append("  (no log yet — daemon may not be running)")

    return "\n".join(lines)


TOOLS = [(TOOL_DEFINITION, run)]
