"""
Tool: obsidian_memory_organizer
Description: Organize HUBERT's memory into structured Obsidian vault notes.
Handles sessions, concepts, projects, people, facts, and tasks.
Generates wiki-links, frontmatter, tags, and keeps a live index per section.

For project notes: automatically extracts topic keywords and stitches
bidirectional wikilinks to every related session and swarm note in the vault.
"""
import os, re, datetime
from pathlib import Path

VAULT_PATH = Path(os.environ.get("OBSIDIAN_VAULT_PATH", r"C:\Users\Jake\HUBERT_Vault"))

FOLDER_MAP = {
    "session":  "Sessions",
    "concept":  "Memory/Concepts",
    "project":  "Memory/Projects",
    "person":   "Memory/People",
    "fact":     "Memory/Facts",
    "task":     "Memory/Tasks",
    "insight":  "Memory/Insights",
    "tool":     "System/Tools",
}


# ── Vault structure helpers ───────────────────────────────────────────────────

def _ensure_vault():
    for folder in FOLDER_MAP.values():
        (VAULT_PATH / folder).mkdir(parents=True, exist_ok=True)
    for extra in ["Swarm/Research", "Swarm/Analysis", "Swarm/General",
                  "Swarm/Memory", "Swarm/Tasks", "System"]:
        (VAULT_PATH / extra).mkdir(parents=True, exist_ok=True)
    index = VAULT_PATH / "00 - Index.md"
    if not index.exists():
        index.write_text(
            "# HUBERT Memory Vault\n\n"
            "> Organized knowledge base for H.U.B.E.R.T.\n\n"
            "## Sections\n"
            "- [[Sessions/_index|Sessions]] — Daily conversation logs\n"
            "- [[Memory/Concepts/_index|Concepts]] — Key concepts & knowledge\n"
            "- [[Memory/Projects/_index|Projects]] — Active & completed projects\n"
            "- [[Memory/People/_index|People]] — People & relationships\n"
            "- [[Memory/Facts/_index|Facts]] — Extracted facts & data\n"
            "- [[Memory/Tasks/_index|Tasks]] — Tasks & follow-ups\n"
            "- [[Memory/Insights/_index|Insights]] — Key insights & learnings\n"
            "- [[Swarm/_summary|Swarm]] — Sub-agent research & analysis\n"
            "- [[System/|System]] — Tool registry & HUBERT config\n",
            encoding="utf-8",
        )


def _update_section_index(folder: str, title: str, snippet: str = ""):
    try:
        idx_path = VAULT_PATH / folder / "_index.md"
        entry = f"- [[{title}]]"
        if snippet:
            entry += f" — {snippet[:80]}"
        entry += "\n"
        if idx_path.exists():
            existing = idx_path.read_text(encoding="utf-8")
            if f"[[{title}]]" not in existing:
                with open(idx_path, "a", encoding="utf-8") as f:
                    f.write(entry)
        else:
            section_name = folder.split("/")[-1].title()
            idx_path.write_text(f"# {section_name} Index\n\n{entry}", encoding="utf-8")
    except Exception:
        pass


def _auto_detect_type(content: str) -> str:
    c = content.lower()
    if any(w in c for w in ["session", "today we", "we worked on", "last session"]):
        return "session"
    if any(w in c for w in ["project:", "building", "implemented", "deploy"]):
        return "project"
    if any(w in c for w in ["jake said", "jake wants", "jake is", "the user"]):
        return "person"
    if any(w in c for w in ["task:", "todo:", "need to", "follow up", "remind"]):
        return "task"
    if any(w in c for w in ["insight:", "learned", "discovered", "realized"]):
        return "insight"
    if any(w in c for w in ["tool:", "capability", "new skill", "tool added"]):
        return "tool"
    return "fact"


# ── Keyword extraction ────────────────────────────────────────────────────────

def _extract_keywords(title: str, content: str, tags: list) -> list[str]:
    """Extract topic keywords from title, tags, and content.

    Tries Ollama first for rich extraction; falls back to heuristic if unavailable.
    Returns lowercase keyword strings.
    """
    # Start with tags and title words as guaranteed keywords
    base = set(tags)
    title_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", title.lower()))
    base.update(title_words)

    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from ollama_core import OllamaCore
        oc = OllamaCore()
        if oc.ollama_available():
            prompt = (
                f"Extract 8-12 topic keywords from this project note. "
                f"Return ONLY a comma-separated list of lowercase keywords, no explanation.\n\n"
                f"Title: {title}\n\nContent (first 600 chars):\n{content[:600]}"
            )
            resp = oc.run_task(
                "You are a keyword extractor. Return only comma-separated lowercase keywords.",
                prompt,
                max_tokens=60,
            )
            ollama_kws = {k.strip().lower() for k in resp.split(",") if len(k.strip()) > 2}
            base.update(ollama_kws)
    except Exception:
        pass

    # Also mine frequent nouns from content (simple heuristic)
    words = re.findall(r"\b[a-zA-Z]{5,}\b", content.lower())
    stopwords = {
        "about", "above", "after", "again", "against", "their", "there", "these",
        "which", "while", "where", "would", "should", "could", "being", "having",
        "using", "based", "first", "every", "other", "since", "those", "within",
        "through", "between", "during", "before", "under", "across", "platform",
        "function", "return", "import", "class", "print", "value", "string",
    }
    from collections import Counter
    counts = Counter(w for w in words if w not in stopwords)
    base.update(w for w, c in counts.most_common(15) if c >= 2)

    return [k for k in base if len(k) > 2]


# ── Auto-weave: bidirectional linking ─────────────────────────────────────────

def _append_related_link(note_path: Path, link_target: str, annotation: str = ""):
    """Add a [[link_target]] to note_path's ## Related section (idempotent)."""
    try:
        text = note_path.read_text(encoding="utf-8")
        link_str = f"[[{link_target}]]"
        if link_str in text:
            return  # already linked
        entry = f"- {link_str}"
        if annotation:
            entry += f" — {annotation}"
        if "## Related" in text:
            # Insert after the ## Related heading
            text = text.replace("## Related\n", f"## Related\n{entry}\n", 1)
        else:
            text = text.rstrip("\n") + f"\n\n## Related\n{entry}\n"
        note_path.write_text(text, encoding="utf-8")
    except Exception:
        pass


def _add_tags_to_note(note_path: Path, new_tags: list[str]):
    """Merge new_tags into an existing note's YAML frontmatter tags array (idempotent)."""
    try:
        text = note_path.read_text(encoding="utf-8")
        match = re.search(r"^tags:\s*\[([^\]]*)\]", text, re.MULTILINE)
        if not match:
            return
        existing_tags = {t.strip().strip('"') for t in match.group(1).split(",") if t.strip()}
        merged = existing_tags | set(new_tags)
        if merged == existing_tags:
            return  # nothing new
        tag_str = ", ".join(sorted(merged))
        text = text[:match.start()] + f"tags: [{tag_str}]" + text[match.end():]
        note_path.write_text(text, encoding="utf-8")
    except Exception:
        pass


def _score_note(note_path: Path, keywords: list[str]) -> int:
    """Return how many keywords appear in note_path's text (case-insensitive)."""
    try:
        text = note_path.read_text(encoding="utf-8", errors="ignore").lower()
        return sum(1 for kw in keywords if kw in text)
    except Exception:
        return 0


def _vault_relative(path: Path) -> str:
    """Return the vault-relative path without .md extension, for use in [[wikilinks]]."""
    try:
        rel = path.relative_to(VAULT_PATH)
        return str(rel.with_suffix("")).replace("\\", "/")
    except Exception:
        return path.stem


def auto_weave_project(project_title: str, project_path: Path,
                        keywords: list[str], tags: list[str]) -> dict:
    """
    After a project note is saved, scan the vault and stitch wikilinks.

    Returns a summary dict:
      {"sessions_linked": [...], "swarm_linked": [...], "tags_propagated": [...]}
    """
    MIN_SCORE = 2          # how many keywords a note must match to get linked
    PROJECT_LINK = _vault_relative(project_path)

    sessions_linked: list[str] = []
    swarm_linked:    list[str] = []
    proj_backlinks:  list[str] = []   # links to add to the project note

    # ── Scan Sessions ─────────────────────────────────────────────────────────
    sessions_dir = VAULT_PATH / "Sessions"
    if sessions_dir.exists():
        for note in sorted(sessions_dir.glob("*.md")):
            if note.stem.startswith("_"):
                continue
            score = _score_note(note, keywords)
            if score >= MIN_SCORE:
                # Link session → project
                _append_related_link(note, PROJECT_LINK,
                                     f"related project ({score} keyword matches)")
                # Add project tags to session note
                _add_tags_to_note(note, tags)
                sessions_linked.append(note.stem)
                proj_backlinks.append((_vault_relative(note), f"session — {note.stem}"))

    # ── Scan Swarm summaries ──────────────────────────────────────────────────
    for swarm_dir in (VAULT_PATH / "Swarm").rglob("*.md"):
        if not swarm_dir.stem.startswith("_summary"):
            continue
        score = _score_note(swarm_dir, keywords)
        if score >= MIN_SCORE:
            _append_related_link(swarm_dir, PROJECT_LINK,
                                 f"related project ({score} keyword matches)")
            _add_tags_to_note(swarm_dir, tags)
            swarm_linked.append(swarm_dir.stem)
            proj_backlinks.append((_vault_relative(swarm_dir),
                                   f"swarm research — {swarm_dir.parent.name}"))

    # ── Tag individual swarm agent files too ──────────────────────────────────
    for swarm_file in (VAULT_PATH / "Swarm").rglob("*.md"):
        if swarm_file.stem.startswith("_"):
            continue
        score = _score_note(swarm_file, keywords)
        if score >= MIN_SCORE:
            _add_tags_to_note(swarm_file, tags)

    # ── Write backlinks into the project note ────────────────────────────────
    if proj_backlinks:
        proj_text = project_path.read_text(encoding="utf-8")
        new_links = []
        for link_target, annotation in proj_backlinks:
            if f"[[{link_target}]]" not in proj_text:
                new_links.append((link_target, annotation))
        if new_links:
            section = "\n## Auto-Linked Notes\n"
            for link_target, annotation in new_links:
                section += f"- [[{link_target}]] — {annotation}\n"
            if "## Auto-Linked Notes" in proj_text:
                # Append to existing section
                proj_text = proj_text.replace(
                    "## Auto-Linked Notes\n",
                    "## Auto-Linked Notes\n" + "".join(
                        f"- [[{lt}]] — {a}\n" for lt, a in new_links
                        if f"[[{lt}]]" not in proj_text
                    ),
                )
            else:
                proj_text = proj_text.rstrip("\n") + section
            project_path.write_text(proj_text, encoding="utf-8")

    return {
        "sessions_linked": sessions_linked,
        "swarm_linked":    swarm_linked,
        "tags_propagated": tags,
    }


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOL_DEFINITION = {
    "name": "organize_memory",
    "description": (
        "Save and organize information into HUBERT's Obsidian memory vault. "
        "Automatically classifies content by type (session, concept, project, person, fact, task, insight). "
        "Writes structured notes with frontmatter, tags, and wiki-links. "
        "For PROJECT notes: automatically extracts topic keywords and stitches "
        "bidirectional wikilinks to every related session and swarm note in the vault. "
        "Updates section indexes so the vault stays navigable."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Content to save (conversation excerpt, findings, notes, tool output, etc.)",
            },
            "type": {
                "type": "string",
                "enum": ["session", "concept", "project", "person", "fact",
                         "task", "insight", "tool", "auto"],
                "description": "Memory type — use 'auto' to detect automatically",
            },
            "title": {
                "type": "string",
                "description": "Note title (auto-generated from content if omitted)",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional tags for this note",
            },
            "links": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Related note names to wiki-link (explicit overrides)",
            },
        },
        "required": ["content"],
    },
}


def run(params: dict) -> str:
    _ensure_vault()

    content  = params["content"]
    mem_type = params.get("type", "auto")
    title    = params.get("title", "")
    tags     = params.get("tags", [])
    links    = params.get("links", [])
    now      = datetime.datetime.now()

    if mem_type == "auto":
        mem_type = _auto_detect_type(content)

    folder = FOLDER_MAP.get(mem_type, "Memory/Facts")

    if not title:
        if mem_type == "session":
            title = now.strftime("%Y-%m-%d")
        else:
            words = content.strip().split()[:7]
            title = " ".join(words).strip(".,!?:;-").replace("/", "-")[:55]
            title = title.replace(":", " -")

    all_tags = [mem_type, "hubert"] + tags
    tag_str  = ", ".join(f'"{t}"' for t in all_tags)

    note_content = (
        f"---\n"
        f"type: {mem_type}\n"
        f"tags: [{tag_str}]\n"
        f"created: {now.strftime('%Y-%m-%d %H:%M')}\n"
        f"vault: HUBERT\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{content}\n"
    )
    if links:
        note_content += "\n## Related\n" + "\n".join(f"- [[{l}]]" for l in links) + "\n"

    target = VAULT_PATH / folder / f"{title}.md"

    # Session notes append if same-day note exists
    if mem_type == "session" and target.exists():
        with open(target, "a", encoding="utf-8") as f:
            f.write(f"\n---\n\n## {now.strftime('%H:%M')} Update\n\n{content}\n")
        return f"Session note updated → {target.relative_to(VAULT_PATH)}"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(note_content, encoding="utf-8")
    _update_section_index(folder, title, content[:80])

    result_msg = f"Memory saved → {target.relative_to(VAULT_PATH)}"

    # ── Auto-weave for project notes ──────────────────────────────────────────
    if mem_type == "project":
        keywords = _extract_keywords(title, content, tags)
        weave_result = auto_weave_project(title, target, keywords, all_tags)
        n_sess  = len(weave_result["sessions_linked"])
        n_swarm = len(weave_result["swarm_linked"])
        if n_sess or n_swarm:
            result_msg += (
                f"\nAuto-linked: {n_sess} session(s) + {n_swarm} swarm note(s)"
                f"\n  Sessions: {weave_result['sessions_linked']}"
                f"\n  Swarm: {weave_result['swarm_linked']}"
            )
        else:
            result_msg += "\nAuto-weave: no matching notes found yet."

    return result_msg


TOOLS = [(TOOL_DEFINITION, run)]
