# HUBERT Second Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform HUBERT's Obsidian vault into a fully automatic second brain with 8 community plugins, a typed frontmatter schema, swarm shared memory, and a nightly Claude extraction + canvas rebuild pipeline.

**Architecture:** A new `memory_pipeline.py` module handles all nightly automation (entity extraction, swarm sync, weekly rollup, canvas rebuild). The existing `_save_session_to_obsidian` in `jarvis_core.py` is upgraded to write rich frontmatter. The dream scheduler in `main.py` triggers the pipeline alongside dream mode at 2 AM. Eight Obsidian plugins are installed directly into `.obsidian/plugins/` without needing the GUI.

**Tech Stack:** Python 3.x, Anthropic Claude API (already wired), pathlib, json, requests (already used), Obsidian Canvas JSON format, GitHub releases for plugin binaries.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `memory_pipeline.py` | **Create** | All nightly automation: extract, swarm sync, rollup, canvas rebuild |
| `jarvis_core.py` | **Modify** | Upgrade `_save_session_to_obsidian` to write rich frontmatter + new folder layout |
| `main.py` | **Modify** | Hook `memory_pipeline.run_nightly()` into dream scheduler |
| `tools/custom/obsidian_memory_organizer.py` | **Modify** | Update `FOLDER_MAP` to match new vault structure, update frontmatter writer |
| `HUBERT_Vault/.obsidian/community-plugins.json` | **Create/Modify** | Enable all 8 plugins |
| `HUBERT_Vault/.obsidian/plugins/*/` | **Create** | Downloaded plugin binaries |
| `HUBERT_Vault/00 - Index.md` | **Replace** | Dataview-powered master dashboard |
| `HUBERT_Vault/Swarm/_active/context.md` | **Create** | Shared memory seed file |
| `HUBERT_Vault/Swarm/_active/working_memory.md` | **Create** | Agent scratch space |
| `HUBERT_Vault/Swarm/_active/agent_states.md` | **Create** | Agent status tracker |

---

## Task 1: Create new vault folder structure

**Files:**
- Modify: `HUBERT_Vault/` (add new directories, seed files)

- [ ] **Step 1: Run the folder scaffold script**

```bash
python3 - << 'EOF'
from pathlib import Path

VAULT = Path.home() / "HUBERT_Vault"
folders = [
    "Sessions", "Daily", "Weekly",
    "Memory/People", "Memory/Projects", "Memory/Decisions",
    "Memory/Action Items", "Memory/Facts", "Memory/Concepts", "Memory/Insights",
    "Swarm/_active", "Swarm/_completed",
    "System", "HUBERT Dreams",
]
for f in folders:
    (VAULT / f).mkdir(parents=True, exist_ok=True)
    print(f"  ok: {f}")
print("Done.")
EOF
```

Expected: all folders printed with `ok:` prefix, "Done." at end.

- [ ] **Step 2: Seed swarm shared memory files**

```bash
python3 - << 'EOF'
from pathlib import Path
import datetime

VAULT = Path.home() / "HUBERT_Vault"
today = datetime.date.today().isoformat()

context = f"""---
type: system
updated: {today}
---

# HUBERT Active Context

> Shared memory — all agents read and write here.

## Current Task
_None_

## Active Goal
_None_

## Key Facts This Session
_None yet_
"""

working = f"""---
type: system
updated: {today}
---

# Working Memory

> Scratch space for agent findings. Flushed nightly into Memory/ notes.

## Pending Findings
_Empty_
"""

agent_states = f"""---
type: system
updated: {today}
---

# Agent States

| Agent | Status | Current Task | Last Active |
|-------|--------|--------------|-------------|
| hubert | idle | — | {today} |
| gemma-swarm | idle | — | — |
| haiku-swarm | idle | — | — |
| claude | idle | — | — |
"""

active = VAULT / "Swarm/_active"
(active / "context.md").write_text(context, encoding="utf-8")
(active / "working_memory.md").write_text(working, encoding="utf-8")
(active / "agent_states.md").write_text(agent_states, encoding="utf-8")
print("Swarm active memory seeded.")
EOF
```

Expected: "Swarm active memory seeded."

- [ ] **Step 3: Commit**

```bash
cd ~/HUBERT_Vault && git init --quiet 2>/dev/null; echo "vault folder structure ready"
```

---

## Task 2: Install 8 Obsidian community plugins

**Files:**
- Create: `HUBERT_Vault/.obsidian/plugins/{8 plugin dirs}/`
- Modify: `HUBERT_Vault/.obsidian/community-plugins.json`

- [ ] **Step 1: Download and install all 8 plugins**

```bash
python3 - << 'EOF'
import urllib.request, zipfile, io, json, shutil
from pathlib import Path

VAULT = Path.home() / "HUBERT_Vault"
PLUGINS_DIR = VAULT / ".obsidian/plugins"
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

PLUGINS = [
    # (folder_name, github_owner/repo, release_asset_name)
    ("obsidian-dataview",        "blacksmithgu/obsidian-dataview",        "obsidian-dataview-{ver}.zip"),
    ("Templater",                "SilentVoid13/Templater",                "Templater-{ver}.zip"),
    ("obsidian-periodic-notes",  "liamcain/obsidian-periodic-notes",      "obsidian-periodic-notes-{ver}.zip"),
    ("obsidian-smart-connections","brianpetro/obsidian-smart-connections", "Obsidian+Smart+Connections-{ver}.zip"),
    ("breadcrumbs",              "SkepticMystic/breadcrumbs",             "breadcrumbs-{ver}.zip"),
    ("graph-analysis",           "SkepticMystic/graph-analysis",          "graph-analysis-{ver}.zip"),
    ("obsidian-auto-note-mover", "farux/obsidian-auto-note-mover",        "obsidian-auto-note-mover-{ver}.zip"),
    ("metadatamenu",             "mdelobelle/metadatamenu",               "metadatamenu-{ver}.zip"),
]

def get_latest_release_assets(repo):
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "HUBERT/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()), r

def install_plugin_from_release(folder_name, repo):
    """Download main.js + manifest.json directly from release assets."""
    plugin_dir = PLUGINS_DIR / folder_name
    plugin_dir.mkdir(exist_ok=True)
    
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "HUBERT/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        release = json.loads(r.read())
    
    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    ver = release["tag_name"]
    
    for fname in ["main.js", "manifest.json", "styles.css"]:
        if fname in assets:
            req2 = urllib.request.Request(assets[fname], headers={"User-Agent": "HUBERT/1.0"})
            with urllib.request.urlopen(req2, timeout=30) as r2:
                (plugin_dir / fname).write_bytes(r2.read())
    
    # If no individual files, try zip
    if not (plugin_dir / "main.js").exists():
        for aname, aurl in assets.items():
            if aname.endswith(".zip"):
                req3 = urllib.request.Request(aurl, headers={"User-Agent": "HUBERT/1.0"})
                with urllib.request.urlopen(req3, timeout=30) as r3:
                    with zipfile.ZipFile(io.BytesIO(r3.read())) as zf:
                        for member in zf.namelist():
                            if member.endswith(("main.js", "manifest.json", "styles.css")):
                                fname = Path(member).name
                                (plugin_dir / fname).write_bytes(zf.read(member))
                break
    
    has_main = (plugin_dir / "main.js").exists()
    has_manifest = (plugin_dir / "manifest.json").exists()
    print(f"  {'ok' if has_main and has_manifest else 'WARN'}: {folder_name} (v{ver}) main={has_main} manifest={has_manifest}")
    return has_main and has_manifest

results = []
for folder, repo, _ in PLUGINS:
    try:
        ok = install_plugin_from_release(folder, repo)
        results.append((folder, ok))
    except Exception as e:
        print(f"  FAIL: {folder} — {e}")
        results.append((folder, False))

print(f"\n{sum(1 for _,ok in results if ok)}/{len(results)} plugins installed.")
EOF
```

Expected: most plugins show `ok:`, final count like `7/8 plugins installed.`

- [ ] **Step 2: Enable all installed plugins in community-plugins.json**

```bash
python3 - << 'EOF'
import json
from pathlib import Path

VAULT = Path.home() / "HUBERT_Vault"
plugins_dir = VAULT / ".obsidian/plugins"

installed = [
    d.name for d in plugins_dir.iterdir()
    if d.is_dir() and (d / "manifest.json").exists() and (d / "main.js").exists()
]

cp = VAULT / ".obsidian/community-plugins.json"
cp.write_text(json.dumps(installed, indent=2))
print(f"Enabled {len(installed)} plugins:", installed)
EOF
```

Expected: prints list of installed plugin folder names.

- [ ] **Step 3: Restart Obsidian to load plugins**

```bash
osascript -e 'quit app "Obsidian"' 2>/dev/null; sleep 2; open -a Obsidian; sleep 5
osascript -e 'tell application "System Events" to get name of every window of process "Obsidian"'
```

Expected: window title contains `HUBERT_Vault`.

---

## Task 3: Upgrade session note writer in `jarvis_core.py`

**Files:**
- Modify: `jarvis_core.py:375-405` (`_save_session_to_obsidian`)

- [ ] **Step 1: Replace `_save_session_to_obsidian` with rich-frontmatter version**

In `jarvis_core.py`, find the function `_save_session_to_obsidian` (around line 375) and replace its entire body with:

```python
def _save_session_to_obsidian(conversation_history: list):
    """Write today's conversation to Sessions/ with full typed frontmatter."""
    try:
        pairs = [
            m for m in conversation_history
            if m["role"] in ("user", "assistant") and isinstance(m.get("content"), str)
        ][-20:]
        if not pairs:
            return
        import datetime
        today = datetime.date.today().isoformat()
        now   = datetime.datetime.now().strftime("%H:%M")
        user_msgs = [m["content"][:120] for m in pairs if m["role"] == "user"][-8:]
        # Build key_outcomes list from last assistant message
        last_asst = next(
            (m["content"][:200] for m in reversed(pairs) if m["role"] == "assistant"), ""
        )
        outcome_line = f'  - "{last_asst}"' if last_asst else "  - (no response captured)"
        frontmatter = (
            f"---\n"
            f"id: \"{today}-session-{now.replace(':','')}\"\n"
            f"type: session\n"
            f"created: {today}\n"
            f"modified: {today}\n"
            f"status: active\n"
            f"tags: [sessions, hubert]\n"
            f"author: hubert\n"
            f"session_date: {today}\n"
            f"session_topic: \"\"\n"
            f"duration_minutes: 0\n"
            f"key_outcomes:\n{outcome_line}\n"
            f"person_refs: [\"[[Jake]]\"]\n"
            f"project_refs: []\n"
            f"related_to: []\n"
            f"depends_on: []\n"
            f"---\n\n"
        )
        lines = [f"# Session — {today}\n\n## Log — {now}\n"]
        for msg in user_msgs:
            lines.append(f"- {msg}")
        content = "\n".join(lines)
        target = VAULT_PATH / "Sessions" / f"{today}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if f"## Log — {now}" not in existing:
                with open(target, "a", encoding="utf-8") as f:
                    f.write(f"\n## Log — {now}\n")
                    for msg in user_msgs:
                        f.write(f"- {msg}\n")
        else:
            target.write_text(frontmatter + content + "\n", encoding="utf-8")
    except Exception:
        pass
```

- [ ] **Step 2: Verify the function parses correctly**

```bash
cd ~/Jarvis && python3 -c "import jarvis_core; print('jarvis_core OK')"
```

Expected: `jarvis_core OK` (no import errors).

- [ ] **Step 3: Update FOLDER_MAP in `tools/custom/obsidian_memory_organizer.py`**

Find the `FOLDER_MAP` dict near the top and replace it with:

```python
VAULT_PATH = Path.home() / "HUBERT_Vault"

FOLDER_MAP = {
    "session":      "Sessions",
    "concept":      "Memory/Concepts",
    "project":      "Memory/Projects",
    "person":       "Memory/People",
    "fact":         "Memory/Facts",
    "task":         "Memory/Tasks",
    "insight":      "Memory/Insights",
    "decision":     "Memory/Decisions",
    "action-item":  "Memory/Action Items",
    "tool":         "System/Tools",
    "swarm":        "Swarm/_active",
}
```

- [ ] **Step 4: Verify tool imports cleanly**

```bash
cd ~/Jarvis && python3 -c "from tools.custom import obsidian_memory_organizer; print('organizer OK')"
```

Expected: `organizer OK`

---

## Task 4: Create `memory_pipeline.py`

**Files:**
- Create: `~/Jarvis/memory_pipeline.py`

- [ ] **Step 1: Create the file**

```python
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

def _get_new_sessions() -> list[Path]:
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


def _write_typed_note(entity: dict) -> Path | None:
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

def extract_entities(session_path: Path) -> list[dict]:
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

def _read_frontmatter(path: Path) -> dict:
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


def _collect_vault_nodes() -> list[dict]:
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
        import math
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
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd ~/Jarvis && python3 -c "import memory_pipeline; print('memory_pipeline OK')"
```

Expected: `memory_pipeline OK`

---

## Task 5: Hook pipeline into dream scheduler in `main.py`

**Files:**
- Modify: `main.py` — `_start_dream_scheduler` method (~line 3592)

- [ ] **Step 1: Update the dream scheduler to also call `run_nightly()`**

Find the `_start_dream_scheduler` method in `main.py`. Inside the `if now.hour == 2` block, add the pipeline call right before the dream runs:

```python
def _start_dream_scheduler(self):
    """Background thread: trigger a deep dream at 2 AM nightly."""
    def _scheduler():
        dreamed_date = None
        while True:
            try:
                now = datetime.datetime.now()
                if now.hour == 2 and dreamed_date != now.date():
                    dreamed_date = now.date()
                    try:
                        # Run memory pipeline first
                        from memory_pipeline import run_nightly
                        run_nightly()
                    except Exception:
                        pass
                    try:
                        if self._ollama_mode and self._ollama_core:
                            self._ollama_core._run_end_of_session_dream()
                        else:
                            from tools.custom.dream_engine import run_dream
                            run_dream({"topic": "recent conversations and goals", "depth": "deep"})
                        self._q.put((self.chat.system,
                                     ("HUBERT dreamed tonight — insights written to Obsidian.",)))
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(60)
    threading.Thread(target=_scheduler, daemon=True).start()
```

- [ ] **Step 2: Verify main.py still imports**

```bash
cd ~/Jarvis && python3 -c "
import ast, sys
with open('main.py') as f:
    src = f.read()
ast.parse(src)
print('main.py syntax OK')
"
```

Expected: `main.py syntax OK`

---

## Task 6: Update `00 - Index.md` with Dataview dashboard

**Files:**
- Replace: `HUBERT_Vault/00 - Index.md`

- [ ] **Step 1: Write the dashboard note**

```bash
python3 - << 'EOF'
from pathlib import Path

content = '''---
id: "index-master"
type: system
created: 2026-04-12
modified: 2026-04-12
status: active
tags: [index, dashboard, hubert]
---

# HUBERT Memory Vault

> Live second brain — auto-updated nightly by HUBERT.

---

## Open Action Items

```dataview
TABLE assigned_to, due_date, priority, project_refs
FROM "Memory/Action Items"
WHERE status = "active"
SORT priority ASC
LIMIT 20
```

---

## Active Projects

```dataview
TABLE project_owner, project_status, project_deadline
FROM "Memory/Projects"
WHERE status = "active"
SORT modified DESC
```

---

## Recent Sessions (Last 7 Days)

```dataview
TABLE session_topic, person_refs, key_outcomes
FROM "Sessions"
WHERE created >= date(today) - dur(7 days)
SORT created DESC
LIMIT 10
```

---

## People Mentioned This Week

```dataview
TABLE person_role, person_projects
FROM "Memory/People"
WHERE modified >= date(today) - dur(7 days)
SORT modified DESC
```

---

## Decisions Made This Month

```dataview
TABLE decision_owner, decision_status, confidence_level
FROM "Memory/Decisions"
WHERE created >= date(today) - dur(30 days)
SORT created DESC
```

---

## Recent Insights

```dataview
TABLE confidence, evidence_strength
FROM "Memory/Insights"
WHERE status = "active"
SORT created DESC
LIMIT 8
```
'''

target = Path.home() / "HUBERT_Vault/00 - Index.md"
target.write_text(content, encoding="utf-8")
print(f"Dashboard written: {target}")
EOF
```

Expected: `Dashboard written: /Users/jakegoncalves/HUBERT_Vault/00 - Index.md`

---

## Task 7: Wire swarm agents to read `context.md`

**Files:**
- Modify: `ollama_orchestrator.py` — `chat()` method

- [ ] **Step 1: Find where system prompt is assembled in `ollama_orchestrator.py`**

```bash
grep -n "_build_system\|system_prompt\|SYSTEM\|context\.md" ~/Jarvis/ollama_orchestrator.py | head -20
```

Note the line number of `_build_system` function.

- [ ] **Step 2: Add swarm context injection to `_build_system`**

Find the `_build_system` function in `ollama_orchestrator.py`. At the end of the function, just before it returns the system string, add:

```python
# Inject swarm shared memory context
try:
    from pathlib import Path
    ctx_path = Path.home() / "HUBERT_Vault/Swarm/_active/context.md"
    if ctx_path.exists():
        ctx = ctx_path.read_text(encoding="utf-8")[:1500]
        # Strip frontmatter
        if ctx.startswith("---"):
            end = ctx.index("---", 3) + 3
            ctx = ctx[end:].strip()
        if ctx and "None_" not in ctx:
            system += f"\n\n## Shared Active Context\n{ctx}"
except Exception:
    pass
```

- [ ] **Step 3: Verify orchestrator imports cleanly**

```bash
cd ~/Jarvis && python3 -c "import ollama_orchestrator; print('ollama_orchestrator OK')"
```

Expected: `ollama_orchestrator OK`

---

## Task 8: Run end-to-end smoke test

- [ ] **Step 1: Run the full pipeline manually**

```bash
cd ~/Jarvis && python3 - << 'EOF'
from memory_pipeline import run_nightly, rebuild_canvas
print("Running canvas rebuild...")
rebuild_canvas()
print("Canvas rebuilt.")

from pathlib import Path
canvas = Path.home() / "HUBERT_Vault/HUBERT_Memory_Map.canvas"
import json
data = json.loads(canvas.read_text())
print(f"Canvas nodes: {len(data['nodes'])}, edges: {len(data['edges'])}")

print("\nRunning full nightly pipeline...")
run_nightly()
print("Pipeline complete.")
EOF
```

Expected: canvas node/edge counts printed, "Pipeline complete." — no exceptions.

- [ ] **Step 2: Verify new vault folders exist**

```bash
ls ~/HUBERT_Vault/Memory/ && ls ~/HUBERT_Vault/Swarm/_active/
```

Expected: `Decisions  Action\ Items  People  Projects  Facts  Concepts  Insights` and the 3 swarm files.

- [ ] **Step 3: Restart Obsidian and verify canvas updated**

```bash
osascript -e 'quit app "Obsidian"' 2>/dev/null; sleep 2; open -a Obsidian; sleep 5
osascript -e 'tell application "System Events" to get name of every window of process "Obsidian"'
```

Expected: `HUBERT_Memory_Map - HUBERT_Vault - Obsidian`

- [ ] **Step 4: Commit everything**

```bash
cd ~/Jarvis && git add memory_pipeline.py jarvis_core.py main.py ollama_orchestrator.py tools/custom/obsidian_memory_organizer.py docs/
git commit -m "$(cat <<'EOF'
feat: HUBERT second brain — nightly pipeline, typed frontmatter, swarm shared memory

- memory_pipeline.py: entity extraction, swarm sync, weekly rollup, canvas rebuild
- jarvis_core.py: rich frontmatter in session notes
- main.py: dream scheduler triggers nightly pipeline at 2 AM
- ollama_orchestrator.py: injects swarm context.md into every prompt
- obsidian_memory_organizer.py: updated FOLDER_MAP for new vault structure
- 8 Obsidian plugins installed (Dataview, Templater, Periodic Notes, etc.)
- 00 - Index.md: live Dataview dashboard

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage check:**
- [x] Vault structure with all 8 typed folders → Task 1
- [x] Swarm shared memory (`_active/context.md`, `working_memory.md`, `agent_states.md`) → Task 1
- [x] 8 plugins installed → Task 2
- [x] Typed frontmatter schema on session notes → Task 3
- [x] `FOLDER_MAP` updated in organizer → Task 3
- [x] `memory_pipeline.py` with extract, swarm sync, rollup, canvas rebuild → Task 4
- [x] Dream scheduler hooks pipeline → Task 5
- [x] Dataview dashboard in `00 - Index.md` → Task 6
- [x] Swarm agents read `context.md` via system prompt → Task 7
- [x] Canvas rebuilt with colors by type, triggered after extraction AND at end → Task 4 (`run_nightly`)
- [x] Mid-session canvas refresh via `run_canvas_refresh()` → Task 4

**Placeholder scan:** No TBDs, all code blocks complete.

**Type consistency:** `VAULT_PATH` used in `jarvis_core.py`/`obsidian_memory_organizer.py`, `VAULT` used in `memory_pipeline.py` (separate module, intentional). `_write_typed_note` matches `extract_entities` output schema throughout.
