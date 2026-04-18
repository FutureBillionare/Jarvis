"""
Tool: obsidian_vault
Description: Read, write, search, and manage notes in an Obsidian vault.
Set OBSIDIAN_VAULT_PATH environment variable to your vault folder.
"""
import os, re, datetime
from pathlib import Path


VAULT_DEFAULT = Path.home() / "HUBERT_Vault"

def _vault() -> Path:
    p = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    return Path(p) if p else VAULT_DEFAULT


def run_read_note(params):
    name  = params["name"]
    vault = _vault()
    # Search for the file
    matches = list(vault.rglob(f"{name}.md")) + list(vault.rglob(f"*{name}*.md"))
    if not matches:
        return f"No note found matching '{name}'."
    content = matches[0].read_text(encoding="utf-8")
    if len(content) > 6000:
        content = content[:6000] + "\n…(truncated)"
    return f"# {matches[0].stem}\nPath: {matches[0]}\n\n{content}"


def run_write_note(params):
    name    = params["name"]
    content = params["content"]
    folder  = params.get("folder", "")
    vault   = _vault()
    target  = vault / folder / f"{name}.md" if folder else vault / f"{name}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if params.get("append") else "w"
    with open(target, mode, encoding="utf-8") as f:
        if params.get("append"):
            f.write(f"\n{content}")
        else:
            f.write(content)
    return f"Note {'appended' if params.get('append') else 'written'}: {target}"


def run_append_note(params):
    return run_write_note({**params, "append": True})


def run_search_notes(params):
    query    = params["query"].lower()
    vault    = _vault()
    max_res  = params.get("max_results", 10)
    results  = []
    for md in vault.rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
            if query in text.lower() or query in md.stem.lower():
                # Get snippet
                idx = text.lower().find(query)
                snippet = text[max(0, idx-60):idx+120].replace("\n", " ")
                results.append((md, snippet))
                if len(results) >= max_res:
                    break
        except Exception:
            pass
    if not results:
        return f"No notes found matching '{query}'."
    lines = [f"Found {len(results)} notes:"]
    for path, snippet in results:
        lines.append(f"\n  📄 {path.stem}")
        lines.append(f"     …{snippet}…")
    return "\n".join(lines)


def run_list_notes(params):
    vault  = _vault()
    folder = params.get("folder", "")
    base   = vault / folder if folder else vault
    notes  = sorted(base.rglob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    limit  = params.get("limit", 30)
    lines  = [f"Notes in vault ({len(notes)} total, showing {min(limit, len(notes))}):\n"]
    for n in notes[:limit]:
        rel = n.relative_to(vault)
        mtime = datetime.datetime.fromtimestamp(n.stat().st_mtime).strftime("%Y-%m-%d")
        lines.append(f"  {mtime}  {rel}")
    return "\n".join(lines)


def run_create_daily_note(params):
    today   = datetime.date.today().isoformat()
    vault   = _vault()
    folder  = params.get("folder", "Daily Notes")
    content = params.get("template",
        f"# {today}\n\n## Tasks\n- \n\n## Notes\n\n## Reflection\n")
    target  = vault / folder / f"{today}.md"
    if target.exists():
        return f"Daily note for {today} already exists: {target}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Daily note created: {target}"


TOOLS = [
    ({"name": "obsidian_read_note",
      "description": "Read a note from the Obsidian vault by name.",
      "input_schema": {"type": "object", "properties": {
          "name": {"type": "string", "description": "Note name (without .md)"}
      }, "required": ["name"]}}, run_read_note),

    ({"name": "obsidian_write_note",
      "description": "Create or overwrite a note in the Obsidian vault.",
      "input_schema": {"type": "object", "properties": {
          "name":    {"type": "string"},
          "content": {"type": "string", "description": "Markdown content"},
          "folder":  {"type": "string", "description": "Subfolder path (optional)"},
      }, "required": ["name", "content"]}}, run_write_note),

    ({"name": "obsidian_append_note",
      "description": "Append content to an existing Obsidian note.",
      "input_schema": {"type": "object", "properties": {
          "name":    {"type": "string"},
          "content": {"type": "string"},
      }, "required": ["name", "content"]}}, run_append_note),

    ({"name": "obsidian_search_notes",
      "description": "Search across all notes in the Obsidian vault by keyword.",
      "input_schema": {"type": "object", "properties": {
          "query":       {"type": "string"},
          "max_results": {"type": "integer", "description": "Default 10"},
      }, "required": ["query"]}}, run_search_notes),

    ({"name": "obsidian_list_notes",
      "description": "List notes in the Obsidian vault, sorted by most recently modified.",
      "input_schema": {"type": "object", "properties": {
          "folder": {"type": "string", "description": "Subfolder to list (optional)"},
          "limit":  {"type": "integer", "description": "Max notes to show, default 30"},
      }}}, run_list_notes),

    ({"name": "obsidian_daily_note",
      "description": "Create today's daily note in the Obsidian vault.",
      "input_schema": {"type": "object", "properties": {
          "folder":   {"type": "string", "description": "Folder for daily notes, default 'Daily Notes'"},
          "template": {"type": "string", "description": "Custom markdown template"},
      }}}, run_create_daily_note),
]
