"""
Dynamic tool registry. Loads built-in tools and any custom tools.
Includes a hot-reload watcher — new files dropped into tools/custom/
are picked up automatically without restarting HUBERT.
"""
import importlib
import importlib.util
import threading
import time
from pathlib import Path
from typing import Callable

_tool_definitions: list[dict] = []
_tool_handlers: dict[str, Callable] = {}

# Callbacks fired when a new tool is hot-loaded: (tool_name) -> None
_on_new_tool_callbacks: list[Callable[[str], None]] = []

# ── Tool groups ──────────────────────────────────────────────────────────────
# Maps logical group name → list of tool names in that group.
# "core" is always included. All other groups are loaded on demand.
TOOL_GROUPS: dict[str, list[str]] = {
    "core": [
        "run_command", "take_screenshot", "read_file", "write_file",
        "list_files", "get_system_info", "ollama_route", "ollama_swarm",
        "token_stats", "write_new_tool", "list_tools",
    ],
    "computer": [
        "open_application", "click_at", "move_mouse", "type_text",
        "press_key", "scroll", "get_clipboard", "set_clipboard",
        "list_processes", "get_screen_size",
    ],
    "browser": [
        "browser_launch", "browser_navigate", "browser_click",
        "browser_type", "browser_get_text", "browser_get_page_content",
        "browser_find_elements", "browser_screenshot", "browser_execute_js",
        "browser_back", "browser_forward", "browser_current_url",
        "browser_wait_for", "browser_select", "browser_press_key",
        "browser_scroll", "browser_close",
    ],
    "swarm": [
        "ollama_swarm", "swarm_dispatch", "swarm_bridge_parallel",
        "ruflo_hive_spawn", "ruflo_agent_spawn", "ruflo_swarm_status",
        "ruflo_swarm_metrics", "ruflo_memory_store", "ruflo_memory_search",
        "ruflo_memory_stats", "ruflo_mcp_tools", "ruflo_agent_list",
        "ruflo_hive_status", "ruflo_status", "ruflo_hooks_intelligence",
    ],
    "github": [
        "github_list_repos", "github_get_repo", "github_list_issues",
        "github_create_issue", "github_list_prs", "github_create_pr",
        "github_git_status", "github_commit_push",
    ],
    "memory": [
        "organize_memory", "obsidian_read_note", "obsidian_write_note",
        "obsidian_append_note", "obsidian_search_notes", "obsidian_list_notes",
        "obsidian_daily_note", "hubert_dream", "hubert_dream_on_topic",
        "hubert_list_dreams", "hubert_read_dream", "hubert_dream_summary",
    ],
    "web": [
        "firecrawl_scrape", "firecrawl_crawl", "firecrawl_extract",
        "firecrawl_map_site", "vercel_list_projects", "vercel_list_deployments",
        "vercel_get_deployment", "vercel_deploy", "vercel_list_env",
    ],
    "productivity": [
        "gsd_add_task", "gsd_list_tasks", "gsd_complete_task",
        "gsd_delete_task", "gsd_add_project", "gsd_daily_review",
        "edge_tts_speak",
        "create_document", "reformat_document", "combine_documents", "open_google_doc",
    ],
    "creative": [
        "excalidraw_flowchart", "excalidraw_mindmap", "excalidraw_open",
        "excalidraw_list", "excalidraw_blank", "notebooklm_open",
        "notebooklm_list_notebooks", "notebooklm_open_notebook",
        "notebooklm_add_source", "notebooklm_ask", "watch_reel",
    ],
    "supabase": [
        "supabase_query", "supabase_insert", "supabase_update",
        "supabase_delete", "supabase_rpc",
    ],
    "meta": [
        "delete_custom_tool", "show_tool_code", "self_repair",
        "skill_list_templates", "skill_create", "skill_scaffold",
        "superpowers_workflow", "ui_control",
    ],
    "eonet": [
        "eonet_events", "eonet_event_detail", "eonet_categories",
    ],
    "google": [
        "google_auth",
        "gmail_send", "gmail_read", "gmail_get_message",
        "gdrive_list", "gdrive_upload", "gdrive_share",
        "gcal_list", "gcal_create", "gcal_delete",
        "search_console", "analytics",
    ],
}

# Tool name → group membership index for fast lookup
_tool_to_group: dict[str, str] = {}
for _g, _names in TOOL_GROUPS.items():
    for _n in _names:
        _tool_to_group[_n] = _g


def get_tool_definitions_for_groups(groups: list[str]) -> list[dict]:
    """Return only the tool definitions belonging to the requested groups.

    "core" is always added. Any tool not in any known group is excluded.
    """
    wanted: set[str] = set(TOOL_GROUPS.get("core", []))
    for g in groups:
        wanted.update(TOOL_GROUPS.get(g, []))
    return [d for d in _tool_definitions if d["name"] in wanted]


def register_tool(definition: dict, handler: Callable):
    name = definition["name"]
    for i, t in enumerate(_tool_definitions):
        if t["name"] == name:
            _tool_definitions[i] = definition
            _tool_handlers[name] = handler
            return
    _tool_definitions.append(definition)
    _tool_handlers[name] = handler


def get_tool_definitions() -> list[dict]:
    return list(_tool_definitions)


def get_handler(name: str) -> Callable | None:
    return _tool_handlers.get(name)


def execute_tool(name: str, params: dict) -> str:
    handler = get_handler(name)
    if not handler:
        return f"Error: tool '{name}' not found."
    try:
        result = handler(params)
        return str(result) if result is not None else "Done."
    except Exception as e:
        return f"Tool error: {e}"


def load_module_tools(module):
    """Load tools exported from a module (TOOLS list of (definition, handler) tuples)."""
    tools = getattr(module, "TOOLS", [])
    for definition, handler in tools:
        register_tool(definition, handler)


def load_single_custom_file(py_file: Path) -> list[str]:
    """Load one custom tool file. Returns list of tool names loaded."""
    if py_file.name.startswith("_"):
        return []
    try:
        spec = importlib.util.spec_from_file_location(
            f"tools.custom.{py_file.stem}", py_file
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        names = []
        for definition, handler in getattr(mod, "TOOLS", []):
            register_tool(definition, handler)
            names.append(definition["name"])
        return names
    except Exception as e:
        print(f"[HUBERT] Failed to load custom tool {py_file.name}: {e}")
        return []


def load_custom_tools():
    """Load all custom tools from the custom/ directory."""
    custom_dir = Path(__file__).parent / "custom"
    custom_dir.mkdir(exist_ok=True)
    for py_file in custom_dir.glob("*.py"):
        load_single_custom_file(py_file)


def reload_all():
    """Reload all tools from scratch."""
    _tool_definitions.clear()
    _tool_handlers.clear()
    from tools import computer, browser, self_extend
    for mod in [computer, browser, self_extend]:
        load_module_tools(mod)
    load_custom_tools()


def on_new_tool(callback: Callable[[str], None]):
    """Register a callback fired when a new tool is hot-loaded."""
    _on_new_tool_callbacks.append(callback)


def start_hot_reload(interval: float = 2.5):
    """
    Start a background thread that watches tools/custom/ for new .py files
    and loads them automatically. Safe to call multiple times (only starts once).
    """
    if getattr(start_hot_reload, "_started", False):
        return
    start_hot_reload._started = True

    custom_dir = Path(__file__).parent / "custom"

    def _watch():
        known: set[Path] = set(custom_dir.glob("*.py"))
        known_mtimes: dict[Path, float] = {
            f: f.stat().st_mtime for f in known
        }
        while True:
            time.sleep(interval)
            try:
                current = set(custom_dir.glob("*.py"))
                # New files
                for f in current - known:
                    names = load_single_custom_file(f)
                    for name in names:
                        for cb in _on_new_tool_callbacks:
                            try:
                                cb(name)
                            except Exception:
                                pass
                # Modified existing files (Claude Code may overwrite)
                for f in current & known:
                    try:
                        mtime = f.stat().st_mtime
                        if mtime != known_mtimes.get(f):
                            names = load_single_custom_file(f)
                            known_mtimes[f] = mtime
                            for name in names:
                                for cb in _on_new_tool_callbacks:
                                    try:
                                        cb(name)
                                    except Exception:
                                        pass
                    except Exception:
                        pass
                known = current
                known_mtimes = {f: known_mtimes.get(f, f.stat().st_mtime)
                                for f in current}
            except Exception:
                pass

    t = threading.Thread(target=_watch, daemon=True, name="hubert-tool-watcher")
    t.start()
