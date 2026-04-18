"""
Tool: gsd_framework
Description: Get S**t Done — personal task and project management framework.
Stores tasks locally in a JSON file. Supports projects, priorities, contexts, and daily review.
"""
import json, datetime
from pathlib import Path

GSD_FILE = Path(__file__).parent.parent.parent / "gsd_tasks.json"

PRIORITIES = {"high": 1, "medium": 2, "low": 3}


def _load():
    if GSD_FILE.exists():
        return json.loads(GSD_FILE.read_text(encoding="utf-8"))
    return {"tasks": [], "projects": [], "_next_id": 1}


def _save(data):
    GSD_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def run_add_task(params):
    data    = _load()
    task_id = data["_next_id"]
    data["_next_id"] += 1
    task = {
        "id":        task_id,
        "title":     params["title"],
        "project":   params.get("project", "Inbox"),
        "priority":  params.get("priority", "medium"),
        "context":   params.get("context", ""),
        "due":       params.get("due", ""),
        "notes":     params.get("notes", ""),
        "status":    "open",
        "created":   datetime.datetime.now().isoformat(),
        "completed": None,
    }
    data["tasks"].append(task)
    _save(data)
    return f"Task #{task_id} added: {task['title']}  [{task['priority']}]  [{task['project']}]"


def run_list_tasks(params):
    data     = _load()
    project  = params.get("project", "")
    priority = params.get("priority", "")
    status   = params.get("status", "open")
    context  = params.get("context", "")

    tasks = [t for t in data["tasks"] if t["status"] == status]
    if project:
        tasks = [t for t in tasks if project.lower() in t["project"].lower()]
    if priority:
        tasks = [t for t in tasks if t["priority"] == priority]
    if context:
        tasks = [t for t in tasks if context.lower() in t["context"].lower()]

    tasks.sort(key=lambda t: (PRIORITIES.get(t["priority"], 9), t["created"]))

    if not tasks:
        return f"No {status} tasks found."

    lines = [f"{'#':<5} {'PRI':<8} {'PROJECT':<20} {'TITLE'}"]
    lines.append("─" * 70)
    for t in tasks:
        due = f" (due {t['due']})" if t["due"] else ""
        lines.append(f"#{t['id']:<4} {t['priority']:<8} {t['project']:<20} {t['title']}{due}")
    return "\n".join(lines)


def run_complete_task(params):
    task_id = params["id"]
    data    = _load()
    for t in data["tasks"]:
        if t["id"] == task_id:
            t["status"]    = "done"
            t["completed"] = datetime.datetime.now().isoformat()
            _save(data)
            return f"Task #{task_id} completed: {t['title']}"
    return f"Task #{task_id} not found."


def run_delete_task(params):
    task_id = params["id"]
    data    = _load()
    before  = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]
    if len(data["tasks"]) < before:
        _save(data)
        return f"Task #{task_id} deleted."
    return f"Task #{task_id} not found."


def run_add_project(params):
    data = _load()
    proj = params["name"]
    if proj not in data["projects"]:
        data["projects"].append(proj)
        _save(data)
        return f"Project '{proj}' added."
    return f"Project '{proj}' already exists."


def run_daily_review(params):
    data  = _load()
    now   = datetime.datetime.now()
    today = now.date().isoformat()
    open_tasks  = [t for t in data["tasks"] if t["status"] == "open"]
    done_today  = [t for t in data["tasks"]
                   if t["status"] == "done" and t["completed"] and
                   t["completed"][:10] == today]
    overdue     = [t for t in open_tasks
                   if t["due"] and t["due"] < today]
    high_pri    = [t for t in open_tasks if t["priority"] == "high"]

    lines = [
        f"── GSD DAILY REVIEW  {now.strftime('%A, %B %d %Y')} ──",
        f"",
        f"✓  Completed today : {len(done_today)}",
        f"📋 Open tasks       : {len(open_tasks)}",
        f"🔴 High priority    : {len(high_pri)}",
        f"⚠  Overdue          : {len(overdue)}",
        "",
    ]
    if high_pri:
        lines.append("HIGH PRIORITY:")
        for t in high_pri[:5]:
            lines.append(f"  #{t['id']} {t['title']}  [{t['project']}]")
    if overdue:
        lines.append("\nOVERDUE:")
        for t in overdue[:5]:
            lines.append(f"  #{t['id']} {t['title']}  (due {t['due']})")
    return "\n".join(lines)


TOOLS = [
    ({"name": "gsd_add_task",
      "description": "Add a new task to the GSD task manager.",
      "input_schema": {"type": "object", "properties": {
          "title":    {"type": "string"},
          "project":  {"type": "string", "description": "Project name (default: Inbox)"},
          "priority": {"type": "string", "enum": ["high", "medium", "low"]},
          "context":  {"type": "string", "description": "Context tag e.g. @computer, @phone"},
          "due":      {"type": "string", "description": "Due date YYYY-MM-DD"},
          "notes":    {"type": "string"},
      }, "required": ["title"]}}, run_add_task),

    ({"name": "gsd_list_tasks",
      "description": "List tasks filtered by project, priority, status, or context.",
      "input_schema": {"type": "object", "properties": {
          "project":  {"type": "string"},
          "priority": {"type": "string", "enum": ["high", "medium", "low"]},
          "status":   {"type": "string", "enum": ["open", "done"], "description": "Default: open"},
          "context":  {"type": "string"},
      }}}, run_list_tasks),

    ({"name": "gsd_complete_task",
      "description": "Mark a GSD task as complete.",
      "input_schema": {"type": "object", "properties": {
          "id": {"type": "integer", "description": "Task ID number"}
      }, "required": ["id"]}}, run_complete_task),

    ({"name": "gsd_delete_task",
      "description": "Delete a task permanently.",
      "input_schema": {"type": "object", "properties": {
          "id": {"type": "integer"}
      }, "required": ["id"]}}, run_delete_task),

    ({"name": "gsd_add_project",
      "description": "Add a new project to the GSD system.",
      "input_schema": {"type": "object", "properties": {
          "name": {"type": "string"}
      }, "required": ["name"]}}, run_add_project),

    ({"name": "gsd_daily_review",
      "description": "Generate a daily GSD review showing high-priority, overdue, and completed tasks.",
      "input_schema": {"type": "object", "properties": {}}}, run_daily_review),
]
