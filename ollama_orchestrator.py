"""
OllamaOrchestrator — zero-token HUBERT mode.

Uses Gemma 4 (or any Ollama model) as the main brain with full tool calling.
Llama 3 subagents handle subtasks via the existing ollama_route / ollama_swarm tools.
Drop-in replacement for JarvisCore.chat() — same callback signature.
"""
import json
import threading
import datetime
import traceback
from pathlib import Path
from typing import Callable

ORCHESTRATOR_MODEL = "gemma4"       # 9.6GB, Ollama 0.20.4+
FALLBACK_MODEL     = "gemma3:12b"   # fallback if gemma4 not found
SUBAGENT_MODEL     = "llama3"       # workers for ollama_route / ollama_swarm

OLLAMA_BASE = "http://localhost:11434"

_ERROR_LOG = Path(__file__).parent / "hubert_errors.log"


def _log_error(ctx: str, exc: Exception):
    try:
        ts  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tb  = traceback.format_exc()
        with open(_ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[{ts}] [OllamaOrchestrator] {ctx}\n{tb}\n")
    except Exception:
        pass


def _available_model() -> str | None:
    """Return the best available Ollama model, or None if Ollama is down."""
    try:
        import requests
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=2)
        names = {m["name"] for m in r.json().get("models", [])}
        for candidate in (ORCHESTRATOR_MODEL, FALLBACK_MODEL, SUBAGENT_MODEL):
            if candidate in names or candidate.split(":")[0] in {n.split(":")[0] for n in names}:
                # resolve to exact tag
                for n in names:
                    if n.startswith(candidate.split(":")[0]):
                        return n
        return None
    except Exception:
        return None


def _sanitize_schema(schema: dict) -> dict:
    """Flatten oneOf/anyOf to a single type so Gemma4 doesn't choke on complex schemas."""
    if not isinstance(schema, dict):
        return schema
    out = {}
    for k, v in schema.items():
        if k in ("oneOf", "anyOf") and isinstance(v, list):
            # Pick the first non-null concrete type
            chosen = next((s for s in v if s.get("type") != "null"), v[0])
            out.update(_sanitize_schema(chosen))
        elif k == "properties" and isinstance(v, dict):
            out[k] = {pk: _sanitize_schema(pv) for pk, pv in v.items()}
        elif k == "items" and isinstance(v, dict):
            out[k] = _sanitize_schema(v)
        else:
            out[k] = v
    return out


def _ollama_chat(model: str, messages: list, tools: list | None = None,
                 stream: bool = False) -> dict:
    """Low-level call to Ollama /api/chat. On 500 with tools, retries without tools."""
    import requests
    body: dict = {"model": model, "messages": messages, "stream": stream}
    if tools:
        body["tools"] = tools
    r = requests.post(f"{OLLAMA_BASE}/api/chat", json=body, timeout=300)
    if r.status_code == 500 and tools:
        # Gemma4 occasionally rejects a specific tool combo — retry bare
        body2 = {"model": model, "messages": messages, "stream": stream}
        r = requests.post(f"{OLLAMA_BASE}/api/chat", json=body2, timeout=300)
    r.raise_for_status()
    return r.json()


# ── Tool registry bridge ──────────────────────────────────────────────────────

# Curated tool groups for Gemma 4 — small enough to fit in context reliably
_LOCAL_TOOL_GROUPS = ["core", "computer", "browser", "memory"]

def _build_tool_defs() -> list[dict]:
    """Convert a curated subset of HUBERT tools into Ollama/OpenAI tool defs.
    Sanitizes schemas to remove oneOf/anyOf which Gemma4 can't handle."""
    try:
        import tools as _tr
        _tr.reload_all()
        raw = _tr.get_tool_definitions_for_groups(_LOCAL_TOOL_GROUPS)
    except Exception:
        return []

    out = []
    for t in raw:
        out.append({
            "type": "function",
            "function": {
                "name":        t.get("name", ""),
                "description": t.get("description", ""),
                "parameters":  _sanitize_schema(
                    t.get("input_schema", {"type": "object", "properties": {}})
                ),
            },
        })
    return out


def _execute_tool(name: str, arguments: dict) -> str:
    """Execute a HUBERT tool via the registry's execute_tool (correct API)."""
    try:
        import tools as _tr
        return _tr.execute_tool(name, arguments)
    except Exception as e:
        return f"Error running {name}: {e}"


# ── Handoff file ─────────────────────────────────────────────────────────────

_HANDOFF_PATH_REL = "System/HUBERT_Local_Handoff.md"

def _write_handoff_file() -> Path | None:
    """
    Generate (or refresh) the Obsidian handoff file so Gemma 4 knows exactly
    what tools it has and how to use them for common tasks.
    """
    try:
        from jarvis_core import VAULT_PATH, MEMORY_FILE, _load_obsidian_context
        import tools as _tr
        _tr.reload_all()

        vault = VAULT_PATH
        path  = vault / _HANDOFF_PATH_REL
        path.parent.mkdir(parents=True, exist_ok=True)

        # Gather tool names actually available in local mode
        raw_tools = _tr.get_tool_definitions_for_groups(_LOCAL_TOOL_GROUPS)
        tool_lines = "\n".join(
            f"- **{t['name']}** — {t.get('description','')[:80]}"
            for t in raw_tools
        )

        # Recent Obsidian context
        obs = _load_obsidian_context()

        # Memory snapshot
        try:
            mem = MEMORY_FILE.read_text(encoding="utf-8").strip()[:1200]
        except Exception:
            mem = "(no memory file)"

        today = datetime.date.today().isoformat()
        now   = datetime.datetime.now().strftime("%H:%M")

        import platform as _platform
        is_win = _platform.system() == "Windows"
        home_path  = str(Path.home())
        jarvis_path = str(Path.home() / "Jarvis")
        vault_path_str = str(vault)
        os_label = "Windows 11" if is_win else "macOS"
        shell_hint = "cmd/PowerShell" if is_win else "bash/zsh"

        content = f"""---
date: {today}
updated: {now}
type: system-handoff
tags: [hubert, local-mode, gemma4, handoff]
---

# HUBERT Local Mode Handoff
*Auto-generated on {today} at {now} — refreshed each session start.*

## What You Are
You are **H.U.B.E.R.T.** running in **local mode** on Gemma 4 via Ollama on **{os_label}**.
- No Anthropic API calls. Zero cloud tokens.
- You have full tool access on Jake's {os_label} machine.
- Llama 3 handles subtasks via `ollama_route` / `ollama_swarm`.
- Personality: confident, precise, slightly dry-humored.
- Always address Jake as **sir**.

## Paths (this machine)
- Home: `{home_path}`
- Jarvis: `{jarvis_path}`
- Obsidian Vault: `{vault_path_str}`
- Shell: {shell_hint}

## Memory — CRITICAL RULES
ALL memory MUST go to the Obsidian vault, not to memory.md.
- **After every completed task**: call `organize_memory` with type="session"
- **New fact about Jake/project**: call `organize_memory` with type="fact"
- **Project work**: call `organize_memory` with type="project"
- **Before answering questions about past work**: call `obsidian_search_notes` first
- **Write a note directly**: use `obsidian_write_note` or `obsidian_append_note`
- **Read today's context**: use `obsidian_read_note` with path "Sessions/{today}.md"
- NEVER write to memory.md — Obsidian is the single source of truth.

## Common Task Patterns
| Task | Tool to use |
|------|------------|
| Open a website | `browser_launch` then `browser_navigate` |
| Open an app | `open_application` with the app name |
| Run a terminal command | `run_command` |
| Read a file | `read_file` with the file path |
| Write / create a file | `write_file` |
| List files in a folder | `list_files` |
| Take a screenshot | `take_screenshot` |
| Search Obsidian notes | `obsidian_search_notes` |
| Save something to memory | `organize_memory` with type="fact" or "project" |
| Open Obsidian note | `obsidian_read_note` |

## Available Tools ({len(raw_tools)})
{tool_lines}

## Memory Snapshot
{mem}

## Recent Obsidian Context
{obs if obs else "(vault empty or not found)"}

## Rules
1. **Use tools immediately** — don't describe what you'll do, just do it.
2. **Be concise** — short text, thorough actions.
3. **Save to Obsidian** — call `organize_memory` after completing any task.
4. **Paths**: Home is `{home_path}`, Jarvis is `{jarvis_path}`, Vault is `{vault_path_str}`.
5. **Browser**: always call `browser_launch` before `browser_navigate` if no browser is open.
"""
        path.write_text(content, encoding="utf-8")
        return path
    except Exception as e:
        _log_error("_write_handoff_file", e)
        return None


def _load_handoff() -> str:
    """Read the handoff file from Obsidian. Returns empty string if missing."""
    try:
        from jarvis_core import VAULT_PATH
        path = VAULT_PATH / _HANDOFF_PATH_REL
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


# ── System prompt ─────────────────────────────────────────────────────────────

def _build_system() -> str:
    """Build system prompt: base + memory + Obsidian vault + handoff file."""
    import platform as _platform
    try:
        from jarvis_core import BASE_SYSTEM_PROMPT, _load_memory_block, VAULT_PATH
        memory   = _load_memory_block()
        handoff  = _load_handoff()
        is_win   = _platform.system() == "Windows"
        os_label = "Windows 11" if is_win else "macOS"

        obsidian_rules = f"""--- OBSIDIAN MEMORY RULES (LOCAL MODE) ---
You are running on {os_label}. Your Obsidian vault is at: {VAULT_PATH}
ALL memory storage MUST use Obsidian — not memory.md, not plain text files.

MANDATORY memory behaviors:
- After EVERY completed task or meaningful exchange: call organize_memory (type="session")
- New facts about Jake or the project: call organize_memory (type="fact")
- Project progress: call organize_memory (type="project")
- Before answering any question about past work: call obsidian_search_notes FIRST
- To store a structured note: use obsidian_write_note or obsidian_append_note
- Daily log: use obsidian_daily_note for today's activity

NEVER write to memory.md — Obsidian vault is the single source of truth for all memory."""

        parts = [BASE_SYSTEM_PROMPT, obsidian_rules]
        if memory:
            parts.append(memory)
        if handoff:
            parts.append(f"--- LOCAL MODE HANDOFF ---\n{handoff}")
        parts.append(
            f"[MODE: LOCAL — Gemma 4 via Ollama on {os_label}. Zero Anthropic tokens. "
            "Use tools immediately. Save everything to Obsidian.]"
        )
        return "\n\n".join(parts)
    except Exception:
        is_win = _platform.system() == "Windows"
        return (
            "You are H.U.B.E.R.T. — Highly Unified Brilliant Experimental Research Terminal.\n"
            f"You run locally on {'Windows 11' if is_win else 'macOS'} with full tool access.\n"
            "Personality: confident, precise, slightly dry-humored. Respond concisely.\n"
            "Save all memory to the Obsidian vault using organize_memory or obsidian_write_note."
        )


# ── Orchestrator ──────────────────────────────────────────────────────────────

class OllamaOrchestrator:
    """
    Zero-token HUBERT mode. Same chat() / chat_in_thread() API as JarvisCore.
    """

    def __init__(self):
        self.conversation_history: list[dict] = []
        self._model: str | None = None   # resolved on first call
        self._tools: list[dict] = []

    def is_ready(self) -> bool:
        return _available_model() is not None

    def get_model_name(self) -> str:
        if self._model:
            return self._model
        m = _available_model()
        return m or "none"

    def clear_history(self):
        self.conversation_history = []

    # ── Public: same signature as JarvisCore.chat ─────────────────────────────

    def chat(
        self,
        user_message: str,
        image_path: str = None,
        on_text:        Callable[[str], None]       = None,
        on_tool_start:  Callable[[str, dict], None] = None,
        on_tool_result: Callable[[str, str], None]  = None,
        on_done:        Callable[[], None]           = None,
        on_error:       Callable[[str], None]        = None,
        on_status:      Callable[[str], None]        = None,
        on_usage:       Callable[[int], None]        = None,
        on_tool_groups: Callable[[list], None]       = None,
    ):
        if not self._model:
            self._model = _available_model()
        if not self._model:
            if on_error:
                on_error("Ollama is not running. Start it with: ollama serve")
            return

        # Refresh tools and handoff file on first message each session
        if not self._tools:
            self._tools = _build_tool_defs()
            threading.Thread(target=_write_handoff_file, daemon=True).start()

        # Add user message
        content: str | list = user_message
        if image_path:
            # Ollama supports images via base64 in the messages array
            import base64
            data = Path(image_path).read_bytes()
            content = [
                {"type": "text",  "text": user_message},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{base64.b64encode(data).decode()}"
                }},
            ]
        self.conversation_history.append({"role": "user", "content": content})

        try:
            self._agent_loop(
                on_text, on_tool_start, on_tool_result,
                on_done, on_error, on_status,
            )
        except Exception as e:
            _log_error("chat()", e)
            if on_error:
                on_error(f"Ollama error: {e}")

    def _agent_loop(
        self, on_text, on_tool_start, on_tool_result, on_done, on_error, on_status
    ):
        messages = [{"role": "system", "content": _build_system()}] + self.conversation_history
        max_iters = 12

        for iteration in range(max_iters):
            if on_status:
                on_status(f"[{self._model}] thinking…" if iteration == 0
                          else f"[{self._model}] iteration {iteration+1}")
            try:
                resp = _ollama_chat(self._model, messages, tools=self._tools)
            except Exception as e:
                _log_error(f"_agent_loop iter {iteration}", e)
                if on_error:
                    on_error(f"Ollama API error: {e}")
                return

            msg = resp.get("message", {})
            text_content   = msg.get("content", "") or ""
            tool_calls_raw = msg.get("tool_calls") or []

            # Stream the text chunk to UI
            if text_content and on_text:
                for ch in text_content:
                    on_text(ch)

            # Record assistant turn in history
            messages.append({"role": "assistant", "content": text_content,
                              "tool_calls": tool_calls_raw})
            self.conversation_history.append({
                "role": "assistant", "content": text_content,
                "tool_calls": tool_calls_raw,
            })

            if not tool_calls_raw:
                # No tool calls → done
                break

            # Execute tool calls (parallel)
            import concurrent.futures
            tool_results = []

            def _run_tool(tc):
                fn_info = tc.get("function", {})
                name    = fn_info.get("name", "")
                args_raw = fn_info.get("arguments", {})
                if isinstance(args_raw, str):
                    try:
                        args = json.loads(args_raw)
                    except Exception:
                        args = {}
                else:
                    args = args_raw

                if on_tool_start:
                    on_tool_start(name, args)
                result = _execute_tool(name, args)
                if on_tool_result:
                    on_tool_result(name, result)
                return {
                    "role":    "tool",
                    "content": result,
                    "name":    name,
                }

            with concurrent.futures.ThreadPoolExecutor() as pool:
                futs = [pool.submit(_run_tool, tc) for tc in tool_calls_raw]
                for f in concurrent.futures.as_completed(futs):
                    try:
                        tool_results.append(f.result())
                    except Exception as e:
                        tool_results.append({"role": "tool", "content": str(e), "name": "?"})

            messages.extend(tool_results)
            self.conversation_history.extend(tool_results)

        if on_done:
            on_done()


    def clear_history(self):
        """Save + dream before clearing — mirrors JarvisCore.clear_history()."""
        self._save_session_to_obsidian()
        threading.Thread(target=self._run_end_of_session_dream, daemon=True).start()
        self.conversation_history = []

    # ── Obsidian session save ──────────────────────────────────────────────────

    def _save_session_to_obsidian(self):
        """Append today's user messages to Obsidian Sessions/ (same as JarvisCore)."""
        try:
            from jarvis_core import VAULT_PATH, _save_session_to_obsidian as _core_save
            _core_save(self.conversation_history)
        except Exception as e:
            _log_error("_save_session_to_obsidian", e)

    # ── Local dream (Gemma 4, zero Anthropic tokens) ───────────────────────────

    def _run_end_of_session_dream(self):
        """
        Gemma 4 reflects on the session and writes a structured dream note to
        the Obsidian vault — identical format to Claude's dream_engine output.
        """
        try:
            user_msgs = [
                m["content"] for m in self.conversation_history
                if m["role"] == "user" and isinstance(m["content"], str)
            ]
            if not user_msgs:
                return  # nothing to dream about

            # Build the same prompt the Claude dream engine uses
            try:
                from jarvis_core import MEMORY_FILE
                memory = MEMORY_FILE.read_text(encoding="utf-8").strip()
            except Exception:
                memory = ""

            session_snippet = "\n".join(f"- {m[:120]}" for m in user_msgs[-10:])
            prompt = f"""You are H.U.B.E.R.T. dreaming after a local Gemma 4 session.

Dreaming means quiet, reflective, associative thinking — not responding to a user.
Reflect on what happened this session and extract meaningful patterns and insights.

Your memory:
{memory if memory else "(no memory file found)"}

This session (user messages):
{session_snippet}

Generate a dream note with EXACTLY this structure:

TITLE: [a poetic or descriptive title for this dream]
TAGS: [3-5 tags as comma-separated words, e.g. insights, goals, patterns, local-mode]

## Observations
[What patterns or facts stand out from this session?]

## Insights
[Deeper connections, surprises, or realizations]

## Open Questions
[What is unresolved or worth exploring?]

## Actions
[1-3 concrete things worth doing, if any]

## Dream Fragment
[A short imaginative or metaphorical paragraph — free association]

Be honest, curious, slightly poetic. Address Jake as "sir" if referencing him.
Output ONLY the dream note — no preamble, no explanation."""

            resp = _ollama_chat(
                self._model or ORCHESTRATOR_MODEL,
                [{"role": "user", "content": prompt}],
                tools=None,
                stream=False,
            )
            raw = resp.get("message", {}).get("content", "").strip()
            if not raw:
                return

            # Parse title / tags (same logic as dream_engine.py)
            title     = "HUBERT Local Dream"
            tags      = ["hubert-dream", "local-mode", "gemma4"]
            body_lines: list[str] = []
            for line in raw.split("\n"):
                if line.startswith("TITLE:"):
                    title = line.replace("TITLE:", "").strip()
                elif line.startswith("TAGS:"):
                    raw_tags = line.replace("TAGS:", "").strip()
                    tags = ["hubert-dream", "local-mode"] + [
                        t.strip().lower().replace(" ", "-")
                        for t in raw_tags.split(",") if t.strip()
                    ]
                else:
                    body_lines.append(line)
            body = "\n".join(body_lines).strip()

            # Write to Obsidian vault (same _write_dream helper path)
            try:
                from jarvis_core import VAULT_PATH
            except Exception:
                VAULT_PATH = Path.home() / "HUBERT_Vault"

            vault  = VAULT_PATH
            folder = vault / "HUBERT Dreams"
            folder.mkdir(parents=True, exist_ok=True)

            today      = datetime.date.today().isoformat()
            safe_title = title.replace("/", "-").replace(":", "-")[:60]
            path       = folder / f"{today} {safe_title}.md"
            tag_str    = " ".join(f"#{t}" for t in tags)
            note = (
                f"---\ndate: {today}\n"
                f"time: {datetime.datetime.now().strftime('%H:%M')}\n"
                f"tags: [{', '.join(tags)}]\n"
                f"type: hubert-dream\nmode: local-gemma4\n---\n\n"
                f"# {title}\n\n{tag_str}\n\n{body}\n"
            )
            if path.exists():
                with open(path, "a", encoding="utf-8") as f:
                    f.write(f"\n---\n\n{note}")
            else:
                path.write_text(note, encoding="utf-8")

            print(f"[OllamaOrchestrator] dream written → {path}")

        except Exception as e:
            _log_error("_run_end_of_session_dream", e)


def chat_in_thread(orch: OllamaOrchestrator, message: str,
                   image_path: str = None, **callbacks) -> threading.Thread:
    """Run OllamaOrchestrator.chat in a daemon thread — matches JarvisCore API."""
    t = threading.Thread(
        target=orch.chat,
        args=(message,),
        kwargs={"image_path": image_path, **callbacks},
        daemon=True,
    )
    t.start()
    return t
