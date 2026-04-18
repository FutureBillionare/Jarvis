"""
Tool: vault_weave
Description: Re-run auto-linking on any existing Obsidian vault note.
Extracts keywords, scans the vault for related notes, and stitches
bidirectional wikilinks + consistent tags. Run this on old notes or
whenever you want to retroactively connect a note to new content.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

VAULT_PATH = Path.home() / "HUBERT_Vault"

TOOL_DEFINITION = {
    "name": "vault_weave",
    "description": (
        "Re-run auto-linking on an existing Obsidian vault note. "
        "Finds the note by name, extracts its topic keywords, scans all sessions and swarm notes "
        "for matches, and stitches bidirectional wikilinks + consistent tags throughout the vault. "
        "Use this to retroactively connect old notes to new content, or to refresh links after "
        "new sessions/swarm batches are added."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "note_name": {
                "type": "string",
                "description": "Name of the note to weave (partial match OK, e.g. 'Prediction Market')",
            },
            "extra_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional tags to propagate to all linked notes",
            },
        },
        "required": ["note_name"],
    },
}


def run(params: dict) -> str:
    from tools.custom.obsidian_memory_organizer import (
        _extract_keywords, auto_weave_project
    )

    name       = params["note_name"]
    extra_tags = params.get("extra_tags", [])

    # Find the note
    matches = list(VAULT_PATH.rglob(f"{name}.md")) + list(VAULT_PATH.rglob(f"*{name}*.md"))
    if not matches:
        return f"No note found matching '{name}' in the vault."

    note_path = matches[0]
    text      = note_path.read_text(encoding="utf-8")

    # Extract title and existing tags from frontmatter
    import re
    title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else note_path.stem

    tag_match = re.search(r"^tags:\s*\[([^\]]*)\]", text, re.MULTILINE)
    existing_tags = []
    if tag_match:
        existing_tags = [t.strip().strip('"') for t in tag_match.group(1).split(",")
                         if t.strip()]

    all_tags = list(set(existing_tags + extra_tags))

    # Extract keywords and weave
    keywords = _extract_keywords(title, text, all_tags)
    result   = auto_weave_project(title, note_path, keywords, all_tags)

    n_sess  = len(result["sessions_linked"])
    n_swarm = len(result["swarm_linked"])

    return (
        f"Weave complete for: {note_path.relative_to(VAULT_PATH)}\n"
        f"Keywords used: {keywords[:10]}\n"
        f"Sessions linked: {n_sess} → {result['sessions_linked']}\n"
        f"Swarm summaries linked: {n_swarm} → {result['swarm_linked']}\n"
        f"Tags propagated: {all_tags}"
    )


TOOLS = [(TOOL_DEFINITION, run)]
