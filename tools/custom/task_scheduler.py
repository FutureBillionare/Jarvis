"""
Tool: task_scheduler
Description: Persistent task scheduler for HUBERT. Stores tasks in scheduled_tasks.json,
logs every execution to Obsidian, and checks for missed tasks on startup.
"""
import os
import json
import datetime
import subprocess
from pathlib import Path

TASKS_FILE = Path(__file__).parent.parent.parent / "scheduled_tasks.json"
VAULT_PATH  = Path(os.environ.get("OBSIDIAN_VAULT_PATH", Path.home() / "HUBERT_Vault"))
LOG_NOTE    = VAULT_PATH / "Scheduler" / "HUBERT_Task_Log.md"


# ── Storage helpers ────────────────────────────────────────────────────────────

def _load() -> dict:
    if TASKS_FILE.exists():
        try:
            return json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"tasks": []}


def _save(data: dict):
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Obsidian logging ───────────────────────────────────────────────────────────

def _log_to_obsidian(task_name: str, status: str, detail: str = ""):
    try:
        LOG_NOTE.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        icon = "✓" if status == "ok" else "✗"
        line = f"- {time_str} {icon} **{task_name}** — {status}"
        if detail:
            line += f": {detail}"

        # Ensure today's section exists
        existing = LOG_NOTE.read_text(encoding="utf-8") if LOG_NOTE.exists() else ""
        header = f"## {date_str}"
        if header not in existing:
            existing = existing.rstrip() + f"\n\n{header}\n"

        existing = existing.rstrip() + "\n" + line + "\n"
        LOG_NOTE.write_text(existing, encoding="utf-8")
    except Exception as e:
        pass  # never crash HUBERT over logging


# ── Due-check logic ────────────────────────────────────────────────────────────

def _is_due(task: dict) -> bool:
    """Return True if the task should run now (missed or on-time)."""
    if not task.get("enabled", True):
        return False

    hour   = task.get("hour", 12)
    minute = task.get("minute", 0)
    now    = datetime.datetime.now()

    # Today's scheduled datetime
    scheduled_today = now.replace(hour=hour, minute=minute,
                                  second=0, microsecond=0)

    # Has the scheduled window passed today?
    if now < scheduled_today:
        return False

    # Check last_run
    last_run_str = task.get("last_run")
    if not last_run_str:
        return True  # never run → run now

    try:
        last_run = datetime.datetime.fromisoformat(last_run_str)
    except Exception:
        return True

    # If last_run is before today's scheduled time → due
    return last_run < scheduled_today


# ── Action runners ─────────────────────────────────────────────────────────────

def _run_git_push(action: dict) -> str:
    """Commit any unstaged changes and push to GitHub."""
    path = action.get("path", str(Path(__file__).parent.parent.parent))
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cwd = path
        # Stage all tracked modifications
        subprocess.run(["git", "add", "-u"], cwd=cwd, capture_output=True, timeout=30)
        # Check if anything is staged
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=cwd, capture_output=True, timeout=10
        )
        if result.returncode != 0:
            # There are staged changes — commit them
            subprocess.run(
                ["git", "commit", "-m", f"sync: DESKTOP-BTF54EI @ {ts}"],
                cwd=cwd, capture_output=True, timeout=30
            )
        # Push
        push = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=cwd, capture_output=True, text=True, timeout=60
        )
        if push.returncode == 0:
            return "git push OK"
        else:
            err = push.stderr.strip()[:200]
            return f"git push failed: {err}"
    except Exception as e:
        return f"error: {e}"


def _run_shell(action: dict) -> str:
    cmd = action.get("command", "")
    if not cmd:
        return "no command specified"
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=120
        )
        out = (result.stdout + result.stderr).strip()[:300]
        return out or "ok"
    except Exception as e:
        return f"error: {e}"


def _execute_task(task: dict) -> str:
    action = task.get("action", {})
    atype  = action.get("type", "")

    if atype == "git_push":
        return _run_git_push(action)
    elif atype == "shell":
        return _run_shell(action)
    else:
        return f"unknown action type: {atype}"


# ── Public scheduler API ───────────────────────────────────────────────────────

def run_due_tasks(source: str = "scheduled") -> list[dict]:
    """Check all tasks and run any that are due. Returns list of results."""
    data    = _load()
    results = []
    changed = False

    for task in data["tasks"]:
        if not _is_due(task):
            continue

        detail = _execute_task(task)
        status = "ok" if ("OK" in detail or detail == "ok") else "error"
        _log_to_obsidian(task["name"], status, detail)

        task["last_run"] = datetime.datetime.now().isoformat()
        changed = True

        results.append({
            "id":     task["id"],
            "name":   task["name"],
            "status": status,
            "detail": detail,
        })

    if changed:
        _save(data)

    return results


# ── HUBERT tool handlers ───────────────────────────────────────────────────────

def run_list_tasks(params: dict) -> str:
    data  = _load()
    tasks = data.get("tasks", [])
    if not tasks:
        return "No scheduled tasks."

    now  = datetime.datetime.now()
    lines = [f"Scheduled tasks ({len(tasks)} total):\n"]
    for t in tasks:
        hour, minute  = t.get("hour", 12), t.get("minute", 0)
        last_run_str  = t.get("last_run", "never")
        enabled_str   = "enabled" if t.get("enabled", True) else "DISABLED"
        due_str       = " ← DUE NOW" if _is_due(t) else ""
        lines.append(
            f"  [{t['id']}] {t['name']}\n"
            f"    Schedule: daily {hour:02d}:{minute:02d}  |  {enabled_str}\n"
            f"    Last run: {last_run_str}{due_str}\n"
            f"    Action:   {t.get('action', {}).get('type', 'unknown')}\n"
        )
    return "\n".join(lines)


def run_add_task(params: dict) -> str:
    data  = _load()
    tasks = data.get("tasks", [])

    task_id = params["id"]
    # Update if exists
    for t in tasks:
        if t["id"] == task_id:
            t.update({
                "name":    params.get("name", t["name"]),
                "hour":    params.get("hour", t["hour"]),
                "minute":  params.get("minute", t["minute"]),
                "action":  params.get("action", t["action"]),
                "enabled": params.get("enabled", t.get("enabled", True)),
            })
            _save(data)
            return f"Task '{task_id}' updated."

    tasks.append({
        "id":       task_id,
        "name":     params["name"],
        "hour":     params.get("hour", 12),
        "minute":   params.get("minute", 0),
        "action":   params.get("action", {}),
        "last_run": None,
        "enabled":  params.get("enabled", True),
    })
    data["tasks"] = tasks
    _save(data)
    return f"Task '{task_id}' added — runs daily at {params.get('hour',12):02d}:{params.get('minute',0):02d}."


def run_remove_task(params: dict) -> str:
    data  = _load()
    before = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if t["id"] != params["id"]]
    if len(data["tasks"]) == before:
        return f"No task with id '{params['id']}' found."
    _save(data)
    return f"Task '{params['id']}' removed."


def run_check_now(params: dict) -> str:
    results = run_due_tasks(source="manual")
    if not results:
        return "No tasks were due."
    lines = [f"Ran {len(results)} task(s):"]
    for r in results:
        lines.append(f"  {r['name']}: {r['status']} — {r['detail']}")
    return "\n".join(lines)


def run_get_log(params: dict) -> str:
    if not LOG_NOTE.exists():
        return "No task execution log found yet."
    text = LOG_NOTE.read_text(encoding="utf-8")
    # Return last 3000 chars
    if len(text) > 3000:
        text = "…(truncated)\n" + text[-3000:]
    return text


# ── Tool definitions ───────────────────────────────────────────────────────────

TOOLS = [
    (
        {
            "name": "scheduler_list_tasks",
            "description": "List all scheduled tasks, their schedules, and last run times.",
            "input_schema": {"type": "object", "properties": {}},
        },
        run_list_tasks,
    ),
    (
        {
            "name": "scheduler_add_task",
            "description": (
                "Add or update a scheduled task. "
                "action types: 'git_push' (commit+push a git repo), 'shell' (run a command). "
                "Schedule is daily at hour:minute (24h, local time)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "id":      {"type": "string", "description": "Unique task ID (snake_case)"},
                    "name":    {"type": "string", "description": "Human-readable name"},
                    "hour":    {"type": "integer", "description": "Hour (0-23)"},
                    "minute":  {"type": "integer", "description": "Minute (0-59)"},
                    "action":  {
                        "type": "object",
                        "description": "Action object: {type: 'git_push', path: '...'} or {type: 'shell', command: '...'}",
                    },
                    "enabled": {"type": "boolean", "description": "Whether task is active"},
                },
                "required": ["id", "name"],
            },
        },
        run_add_task,
    ),
    (
        {
            "name": "scheduler_remove_task",
            "description": "Remove a scheduled task by ID.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Task ID to remove"},
                },
                "required": ["id"],
            },
        },
        run_remove_task,
    ),
    (
        {
            "name": "scheduler_check_now",
            "description": "Manually trigger a check — runs any tasks that are currently due.",
            "input_schema": {"type": "object", "properties": {}},
        },
        run_check_now,
    ),
    (
        {
            "name": "scheduler_get_log",
            "description": "Get the task execution log from Obsidian.",
            "input_schema": {"type": "object", "properties": {}},
        },
        run_get_log,
    ),
]
