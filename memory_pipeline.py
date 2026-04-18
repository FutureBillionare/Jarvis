# ~/Jarvis/memory_pipeline.py
"""
HUBERT Memory Pipeline — nightly second brain automation.

Runs at 2 AM via main.py dream scheduler.
Steps:
  1. Extract entities from new session notes (Claude)
  2. Sync swarm working_memory into vault
  3. Weekly rollup (Sundays)
  4. Rebuild canvas
"""
import json, datetime, threading
from pathlib import Path

VAULT = Path.home() / "HUBERT_Vault"
_LAST_RUN_FILE = Path(__file__).parent / ".memory_pipeline_last_run"

FOLDER_MAP = {
    "session":      "Sessions",
    "decision":     "Memory/Decisions",
    "action-item":  "Memory/Action Items",
    "fact":         "Memory/Facts",
    "person":       "Memory/People",
    "project":      "Memory/Projects",
    "concept":      "Memory/Concepts",
    "insight":      "Memory/Insights",
}

NODE_COLORS = {
    "session":      "5",   # purple
    "person":       "2",   # blue/green
    "project":      "3",   # green
    "decision":     "4",   # yellow
    "action-item":  "1",   # red
    "insight":      "6",   # teal
    "fact":         "4",
    "concept":      "3",
    "system":       "4",
    "dream":        "6",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.date.today().isoformat()

def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def _get_new_sessions() -> list:
    """Return session notes written since last pipeline run."""
    sessions_dir = VAULT / "Sessions"
    if not sessions_dir.exists():
        return []
    last_run = None
    if _LAST_RUN_FILE.exists():
        try:
            last_run = datetime.date.fromisoformat(_LAST_RUN_FILE.read_text().strip())
        except Exception:
            pass
    results = []
    for p in sorted(sessions_dir.glob("*.md")):
        if last_run is None or p.stem >= str(last_run):
            results.append(p)
    return results


def _write_typed_note(entity: dict):
    """Write a typed entity note into the correct vault folder."""
    try:
        note_type = entity.get("type", "fact")
        folder = FOLDER_MAP.get(note_type, "Memory/Facts")
        title = entity.get("title", "untitled").replace("/", "-").replace(":", "-")
        today = _today()
        note_id = entity.get("id", f"{today}-{note_type}-{title[:20].replace(' ', '-').lower()}")

        # Build type-specific frontmatter extras
        extras = ""
        if note_type == "decision":
            extras = (
                f"decision_owner: \"{entity.get('owner', 'Jake')}\"\n"
                f"decision_status: \"pending\"\n"
                f"confidence_level: {entity.get('confidence', 7)}\n"
            )
        elif note_type == "action-item":
            extras = (
                f"assigned_to: \"[[{entity.get('assigned_to', 'Jake')}]]\"\n"
                f"due_date: \"\"\n"
                f"priority: {entity.get('priority', 3)}\n"
                f"blocking: false\n"
            )
        elif note_type == "person":
            extras = (
                f"person_role: \"{entity.get('role', '')}\"\n"
                f"person_expertise: []\n"
                f"person_projects: []\n"
            )
        elif note_type == "fact":
            extras = (
                f"confidence: {entity.get('confidence', 7)}\n"
                f"evidence_strength: \"{entity.get('evidence', 'medium')}\"\n"
                f"reviewed: false\n"
            )

        person_refs = json.dumps(entity.get("person_refs", []))
        project_refs = json.dumps(entity.get("project_refs", []))

        frontmatter = (
            f"---\n"
            f"id: \"{note_id}\"\n"
            f"type: {note_type}\n"
            f"created: {today}\n"
            f"modified: {today}\n"
            f"status: active\n"
            f"tags: [{note_type}, hubert]\n"
            f"author: hubert\n"
            f"{extras}"
            f"person_refs: {person_refs}\n"
            f"project_refs: {project_refs}\n"
            f"related_to: []\n"
            f"depends_on: []\n"
            f"---\n\n"
        )
        body = f"# {title}\n\n{entity.get('body', entity.get('summary', ''))}\n"

        target_dir = VAULT / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_title = title[:60].replace(" ", "_")
        target = target_dir / f"{today}-{safe_title}.md"
        # Don't overwrite existing notes — append instead
        if target.exists():
            with open(target, "a", encoding="utf-8") as f:
                f.write(f"\n## Update — {_now_str()}\n{entity.get('body', '')}\n")
        else:
            target.write_text(frontmatter + body, encoding="utf-8")
        return target
    except Exception:
        return None


# ── Step 1: Entity extraction ─────────────────────────────────────────────────

EXTRACTION_PROMPT = """\
You are analyzing an HUBERT AI assistant session note. Extract all notable entities.

Return a JSON array of objects. Each object must have:
- "type": one of: decision, action-item, fact, person, insight
- "title": short title (max 60 chars)
- "summary": 1-2 sentence summary
- "body": full markdown body (2-5 sentences)
- "person_refs": list of people mentioned as "[[Name]]" strings
- "project_refs": list of projects mentioned as "[[ProjectName]]" strings

Only extract things worth remembering long-term. Skip greetings, trivial commands.
Return ONLY the JSON array, no other text.

Session note:
{content}
"""

def extract_entities(session_path) -> list:
    """Use Claude to extract typed entities from a session note."""
    try:
        import anthropic
        from config import get_api_key
        key = get_api_key()
        if not key:
            return []
        content = session_path.read_text(encoding="utf-8")[:6000]
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT.format(content=content)
            }]
        )
        raw = resp.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])
        return json.loads(raw)
    except Exception:
        return []


# ── Step 2: Swarm sync ────────────────────────────────────────────────────────

def sync_swarm_memory():
    """Merge working_memory.md findings into vault, then reset it."""
    try:
        wm_path = VAULT / "Swarm/_active/working_memory.md"
        if not wm_path.exists():
            return
        content = wm_path.read_text(encoding="utf-8")
        if "## Pending Findings\n_Empty_" in content or "Pending Findings" not in content:
            return  # Nothing to sync
        # Archive the working memory
        today = _today()
        archive_dir = VAULT / "Swarm/_completed"
        archive_dir.mkdir(exist_ok=True)
        archive_path = archive_dir / f"{today}-working-memory.md"
        archive_path.write_text(content, encoding="utf-8")
        # Reset working_memory
        wm_path.write_text(
            f"---\ntype: system\nupdated: {today}\n---\n\n"
            f"# Working Memory\n\n> Scratch space for agent findings. Flushed nightly.\n\n"
            f"## Pending Findings\n_Empty_\n",
            encoding="utf-8",
        )
    except Exception:
        pass


# ── Step 3: Weekly rollup ─────────────────────────────────────────────────────

ROLLUP_PROMPT = """\
Summarize this week's HUBERT session notes into a concise weekly digest.

Format as markdown with sections:
## Summary
(2-3 sentence overview)

## Decisions Made
(bullet list)

## Action Items Opened
(bullet list)

## People Mentioned
(bullet list)

## Key Insights
(bullet list)

Session notes:
{content}
"""

def build_weekly_rollup():
    """Claude summarizes the past week's sessions. Only runs on Sundays."""
    try:
        if datetime.date.today().weekday() != 6:  # 6 = Sunday
            return
        import anthropic
        from config import get_api_key
        key = get_api_key()
        if not key:
            return
        # Gather last 7 days of sessions
        sessions_dir = VAULT / "Sessions"
        cutoff = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        notes = []
        for p in sorted(sessions_dir.glob("*.md")):
            if p.stem >= cutoff:
                notes.append(p.read_text(encoding="utf-8")[:2000])
        if not notes:
            return
        combined = "\n\n---\n\n".join(notes)[:12000]
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": ROLLUP_PROMPT.format(content=combined)}]
        )
        summary = resp.content[0].text.strip()
        today = _today()
        weekly_dir = VAULT / "Weekly"
        weekly_dir.mkdir(exist_ok=True)
        # Get week start date (Monday)
        week_start = (datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())).isoformat()
        target = weekly_dir / f"{week_start}-weekly.md"
        frontmatter = (
            f"---\nid: \"{week_start}-weekly\"\ntype: session\n"
            f"created: {today}\nmodified: {today}\nstatus: active\n"
            f"tags: [weekly, hubert, rollup]\nauthor: hubert\n---\n\n"
        )
        target.write_text(frontmatter + f"# Week of {week_start}\n\n{summary}\n", encoding="utf-8")
    except Exception:
        pass


# ── Step 4: Canvas rebuild ────────────────────────────────────────────────────

def _read_frontmatter(path) -> dict:
    """Parse YAML frontmatter from a markdown file."""
    try:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return {}
        end = text.index("---", 3)
        fm_text = text[3:end].strip()
        result = {}
        for line in fm_text.splitlines():
            if ":" in line and not line.startswith(" ") and not line.startswith("-"):
                k, _, v = line.partition(":")
                result[k.strip()] = v.strip().strip('"')
        return result
    except Exception:
        return {}


def _collect_vault_nodes() -> list:
    """Scan vault for active notes to use as canvas nodes."""
    nodes = []
    for folder, type_name in [
        ("Memory/Projects", "project"),
        ("Memory/People", "person"),
        ("Memory/Decisions", "decision"),
        ("Memory/Insights", "insight"),
        ("Sessions", "session"),
        ("HUBERT Dreams", "dream"),
        ("System", "system"),
    ]:
        folder_path = VAULT / folder
        if not folder_path.exists():
            continue
        for md in sorted(folder_path.glob("*.md"))[-8:]:  # cap per folder
            fm = _read_frontmatter(md)
            if fm.get("status") == "archived":
                continue
            nodes.append({
                "path": str(md.relative_to(VAULT)),
                "title": md.stem.replace("_", " ").replace("-", " "),
                "type": fm.get("type", type_name),
                "status": fm.get("status", "active"),
            })
    return nodes


def rebuild_canvas():
    """Regenerate HUBERT_Memory_Map.canvas from live vault state."""
    try:
        import math
        nodes_data = _collect_vault_nodes()
        today = _today()

        canvas_nodes = []
        canvas_edges = []

        # Center node
        canvas_nodes.append({
            "id": "hubert-core",
            "type": "text",
            "text": (
                f"# HUBERT\n**Second Brain**\n\n"
                f"Updated: {today}\n"
                f"{len(nodes_data)} active notes"
            ),
            "x": -100, "y": -120, "width": 280, "height": 120,
            "color": "1"
        })

        # Arrange nodes in a circle around the center
        radius = 520
        for i, node in enumerate(nodes_data):
            angle = (2 * math.pi * i) / max(len(nodes_data), 1)
            x = int(-100 + radius * math.cos(angle)) - 140
            y = int(-120 + radius * math.sin(angle)) - 40
            node_id = f"node-{i}"
            color = NODE_COLORS.get(node["type"], "4")
            canvas_nodes.append({
                "id": node_id,
                "type": "file",
                "file": node["path"],
                "x": x, "y": y,
                "width": 280, "height": 80,
                "color": color,
            })
            canvas_edges.append({
                "id": f"edge-{i}",
                "fromNode": "hubert-core",
                "fromSide": "right" if x > -100 else "left",
                "toNode": node_id,
                "toSide": "left" if x > -100 else "right",
            })

        canvas_data = {"nodes": canvas_nodes, "edges": canvas_edges}
        canvas_path = VAULT / "HUBERT_Memory_Map.canvas"
        canvas_path.write_text(json.dumps(canvas_data, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_nightly():
    """Full nightly pipeline. Called by dream scheduler at 2 AM."""
    try:
        # Step 1: Extract entities from new sessions
        new_sessions = _get_new_sessions()
        for session_path in new_sessions:
            entities = extract_entities(session_path)
            for entity in entities:
                _write_typed_note(entity)
        # Canvas after extraction
        rebuild_canvas()

        # Step 2: Swarm sync
        sync_swarm_memory()

        # Step 3: Weekly rollup (Sundays only)
        build_weekly_rollup()

        # Step 4: Final canvas rebuild
        rebuild_canvas()

        # Mark last run
        _LAST_RUN_FILE.write_text(_today())
    except Exception:
        pass


def run_canvas_refresh():
    """Lightweight canvas refresh — safe to call mid-session."""
    threading.Thread(target=rebuild_canvas, daemon=True).start()
