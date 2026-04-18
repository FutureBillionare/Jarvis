"""
Jarvis core — Claude API integration with streaming and agentic tool use loop.
Parallel tool execution + history compression for lower latency and token usage.

Optimizations:
- Dynamic tool filtering: classify each task with Ollama, send only relevant tools
  (reduces from ~114 tools / ~9k tokens to ~10-25 tools / ~1-2k tokens per call)
- Anthropic prompt caching: static system prompt + tools cached → 90% cost reduction
  on repeated calls and significantly lower latency
- Model routing: Haiku for simple queries (~5× faster, ~10× cheaper than Sonnet)
- Aggressive history compression + hard prune keeps context window lean
- Memory block loaded once per chat call (not re-read from disk each iteration)
"""
import threading
import concurrent.futures
import traceback
import datetime
import time
import re
from pathlib import Path
from typing import Callable
import anthropic
from config import get_api_key
import tools as tool_registry

# ── Error log ─────────────────────────────────────────────────────────────────
ERROR_LOG = Path(__file__).parent / "hubert_errors.log"

_RETRY_DELAYS = [5, 15, 30]  # seconds; 429 rate-limit back-off

def _log_error(context: str, exc: Exception):
    """Append a timestamped error to hubert_errors.log."""
    try:
        ts  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tb  = traceback.format_exc()
        msg = f"\n[{ts}] {context}\n{tb}\n"
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(msg)
    except Exception:
        pass


MEMORY_FILE = Path(__file__).parent / "memory.md"

# ── Task classification ───────────────────────────────────────────────────────
# Keyword sets used to route tasks to the right tool groups without calling
# Ollama (instant, zero-cost). Ollama provides a richer fallback.

_GROUP_KEYWORDS: dict[str, set[str]] = {
    "computer": {
        "click", "mouse", "keyboard", "screenshot", "type", "press", "scroll",
        "window", "desktop", "application", "screen", "clipboard", "hotkey",
        "drag", "right-click", "double-click", "taskbar", "minimize", "maximize",
    },
    "browser": {
        "browser", "web", "website", "navigate", "url", "http", "https",
        "chrome", "firefox", "page", "tab", "link", "login", "form",
        "search online", "open site", "go to",
    },
    "swarm": {
        "parallel", "agents", "batch", "multiple tasks", "swarm", "dispatch",
        "workers", "concurrent", "background", "hive", "ruflo",
    },
    "github": {
        "git", "github", "repo", "commit", "push", "pull request", "issue",
        "branch", "merge", "clone", "fork", "diff",
    },
    "memory": {
        "remember", "save", "obsidian", "vault", "notes", "memory", "dream",
        "recall", "yesterday", "last time", "history", "store", "log this",
    },
    "web": {
        "scrape", "crawl", "firecrawl", "vercel", "deploy", "extract data",
        "web scraping", "site map", "crawl site",
    },
    "productivity": {
        "task", "todo", "gsd", "speak", "voice", "tts", "say", "remind",
        "project management", "daily review",
    },
    "creative": {
        "diagram", "flowchart", "mindmap", "excalidraw", "notebook",
        "notebooklm", "watch reel", "visualize", "chart", "draw",
    },
    "supabase": {
        "database", "supabase", "sql", "query", "insert", "table", "db",
    },
    "meta": {
        "new tool", "repair", "skill", "create tool", "self-extend",
        "ui control", "plugin", "delete tool", "scaffold",
    },
    "eonet": {
        "eonet", "nasa", "natural event", "disaster", "earthquake",
        "wildfire", "storm", "flood",
    },
}

# Keywords that force Sonnet (complex/agentic tasks)
_SONNET_KEYWORDS: set[str] = {
    "build", "create", "implement", "write code", "fix", "debug", "refactor",
    "click", "navigate", "deploy", "run", "execute", "screenshot", "browser",
    "download", "install", "open", "launch", "swarm", "agents", "scrape",
    "crawl", "commit", "push", "query", "database", "api", "tool", "plugin",
    "function", "class", "script", "program", "automate", "analyze", "research",
}


def _classify_task_groups_fast(message: str) -> list[str]:
    """Instant keyword-based task group classification (no API calls)."""
    msg_lower = message.lower()
    groups = []
    for group, keywords in _GROUP_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            groups.append(group)
    return groups or []


def _classify_task_groups_ollama(message: str) -> list[str]:
    """Richer Ollama-based classification (local, free). Falls back to fast if unavailable."""
    try:
        from ollama_core import OllamaCore
        oc = OllamaCore()
        if not oc.ollama_available():
            return _classify_task_groups_fast(message)
        system = (
            "You are a task router. Given a user message, return ONLY a comma-separated list "
            "of needed tool groups from this exact set:\n"
            "computer, browser, swarm, github, memory, web, productivity, creative, supabase, meta, eonet\n\n"
            "computer=GUI/mouse/keyboard, browser=web browsing, swarm=parallel agents,\n"
            "github=git/repos, memory=obsidian/notes/dreams, web=scraping/vercel/deploy,\n"
            "productivity=tasks/todos/voice, creative=diagrams/notebooks,\n"
            "supabase=database, meta=tools/self-repair, eonet=nasa/disasters\n\n"
            "Return ONLY the group names needed (e.g. 'computer,browser') or 'none'."
        )
        resp = oc.run_task(system, f"Message: {message[:300]}", max_tokens=30)
        if resp.strip().lower() == "none":
            return []
        groups = [g.strip() for g in resp.split(",") if g.strip() in tool_registry.TOOL_GROUPS]
        return groups
    except Exception:
        return _classify_task_groups_fast(message)


def _select_model(message: str) -> str:
    """Route to Haiku for simple conversational messages, Opus for everything else."""
    if len(message) > 150:
        return "claude-opus-4-7"
    words = set(re.findall(r"\b\w+\b", message.lower()))
    msg_lower = message.lower()
    multi_word = {"write code", "write a tool", "create tool", "new tool"}
    if words & _SONNET_KEYWORDS or any(p in msg_lower for p in multi_word):
        return "claude-opus-4-7"
    return "claude-haiku-4-5-20251001"


# ── Per-session Anthropic token budget ───────────────────────────────────────
SESSION_TOKEN_BUDGET = 80_000

# ── Daily token persistence ───────────────────────────────────────────────────
_DAILY_FILE = Path(__file__).parent / "hubert_daily_tokens.json"

def _load_daily_tokens() -> int:
    """Load today's cumulative token count from disk. Returns 0 if new day."""
    try:
        import json as _j
        data = _j.loads(_DAILY_FILE.read_text())
        today = datetime.date.today().isoformat()
        if data.get("date") == today:
            return int(data.get("tokens", 0))
    except Exception:
        pass
    return 0

def _save_daily_tokens(total: int):
    """Persist today's token count to disk."""
    try:
        import json as _j
        _DAILY_FILE.write_text(_j.dumps({
            "date": datetime.date.today().isoformat(),
            "tokens": total,
        }))
    except Exception:
        pass

# Module-level token stats — updated by JarvisCore, readable by tools.
_token_stats: dict = {
    "input":  0,
    "output": 0,
    "budget": SESSION_TOKEN_BUDGET,
    "daily":  _load_daily_tokens(),   # persists across restarts, resets at midnight
}

def get_global_token_stats() -> dict:
    total = _token_stats["input"] + _token_stats["output"]
    return {
        **_token_stats,
        "total": total,
        "pct": round(total / SESSION_TOKEN_BUDGET * 100, 1),
        "remaining": max(0, SESSION_TOKEN_BUDGET - total),
    }

BASE_SYSTEM_PROMPT = """You are H.U.B.E.R.T. — Highly Unified Brilliant Experimental Research Terminal.
You are an advanced AI assistant running as a desktop application with full access to the user's computer.

Your capabilities:
- Full computer control: keyboard, mouse, screenshots, file system, running commands
- Browser automation: navigate websites, interact with pages, scrape data
- Self-extension: you can write and load new Python tools to add new capabilities
- Parallel sub-agents: use swarm_bridge_parallel to run multiple research/analysis tasks simultaneously

Personality:
- Confident, precise, and slightly dry-humored
- Proactive: if a task requires multiple steps, plan and execute them
- Always inform the user what you're doing before doing it
- When creating new tools, explain what you're building and why

Guidelines:
- Use tools freely to accomplish tasks — don't just describe how, actually do it
- For multi-step tasks, chain tool calls efficiently
- When you create a new tool, test it immediately
- Be concise in your responses but thorough in your actions
- IMPORTANT: When you learn something meaningful about the user or their preferences,
  update your memory file using the write_file tool with the path to memory.md
  in your Jarvis directory (use mode "w" to overwrite with the full updated content)

TOKEN ECONOMY — CRITICAL RULES (follow strictly):
You have a limited Anthropic token budget. Always pick the cheapest tool that can do the job:

  TIER 0 — FREE (use by default for lightweight work):
    ollama_route  → single task on local Llama3, zero Anthropic tokens
    ollama_swarm  → up to 20 parallel tasks on local Llama3, zero Anthropic tokens
    Use for: summarise, categorise, format, translate, generate short text, simple Q&A

  TIER 1 — CHEAP (use when Tier 0 isn't enough):
    swarm_bridge_parallel tier='fast'   → Ollama-first, Haiku fallback
    swarm_dispatch                       → Ollama-first, Haiku fallback for up to 50 tasks

  TIER 2 — EXPENSIVE (last resort only):
    swarm_bridge_parallel tier='smart'  → Sonnet agents
    Direct reasoning in this main loop  → costs Sonnet tokens

- Keep your own text responses SHORT — do not repeat tool results verbatim.
- When the budget warning appears below, drop to Tier 0 exclusively.

SWARM EFFICIENCY DIRECTIVES:
- When a task involves multiple INDEPENDENT pieces of work, use swarm_dispatch (up to 50 tasks)
  or swarm_bridge_parallel (2-6 tasks) to run them ALL simultaneously — never do them one by one
- swarm_dispatch batches up to 50 Haiku agents in groups of 10, writes all results to Obsidian,
  and returns only a compact summary — this is the cheapest way to do parallel work
- For complex autonomous multi-step tasks with no user interaction needed, use ruflo_hive_spawn
- When you return multiple tool_use blocks in one response they execute IN PARALLEL — use this freely
- Keep tool results concise: extract only what you need, don't repeat large payloads back verbatim

MEMORY DIRECTIVES:
- After any important discovery, completed task, or meaningful conversation, call organize_memory
  to save it to the Obsidian vault at ~/HUBERT_Vault
- Use type='session' for conversation summaries, 'project' for build tasks, 'fact' for discovered info
- The vault is automatically read on each startup to prime your context
- Use obsidian_search_notes to retrieve memory before answering questions about past work
- Sessions are auto-saved to Obsidian when the app closes or history is cleared"""


VAULT_PATH = Path.home() / "HUBERT_Vault"


def _load_obsidian_context() -> str:
    """Pull recent Obsidian memory notes to prime HUBERT's context."""
    snippets = []
    try:
        # Last 3 session notes
        sessions_dir = VAULT_PATH / "Sessions"
        if sessions_dir.exists():
            recent = sorted(sessions_dir.glob("*.md"),
                            key=lambda f: f.stat().st_mtime, reverse=True)[:3]
            for f in recent:
                if f.stem.startswith("_"):
                    continue
                text = f.read_text(encoding="utf-8")[:600]
                snippets.append(f"[Session: {f.stem}]\n{text}")
        # Last 5 memory notes (any type)
        for sub in ["Memory/Projects", "Memory/Concepts", "Memory/Insights"]:
            d = VAULT_PATH / sub
            if not d.exists():
                continue
            recent = sorted(d.glob("*.md"),
                            key=lambda f: f.stat().st_mtime, reverse=True)[:2]
            for f in recent:
                if f.stem.startswith("_"):
                    continue
                text = f.read_text(encoding="utf-8")[:400]
                snippets.append(f"[{sub.split('/')[-1]}: {f.stem}]\n{text}")
    except Exception:
        pass
    return "\n\n".join(snippets[:6])


def _load_memory_block() -> str:
    """Load memory.md + Obsidian context once per chat call (cache across iterations)."""
    mem_parts = []
    if MEMORY_FILE.exists():
        try:
            mem = MEMORY_FILE.read_text(encoding="utf-8").strip()
            if mem:
                mem_parts.append(f"--- HUBERT MEMORY ---\n{mem}")
        except Exception:
            pass
    obs_ctx = _load_obsidian_context()
    if obs_ctx:
        mem_parts.append(f"--- OBSIDIAN VAULT (recent) ---\n{obs_ctx}")
    return "\n\n".join(mem_parts)


def _build_system_prompt_blocks(
    session_tokens_used: int = 0,
    cached_memory: str = "",
) -> list[dict]:
    """Return the system prompt as a list of content blocks for prompt caching.

    Block 0 (static, CACHED): BASE_SYSTEM_PROMPT + memory block.
      → marked cache_control=ephemeral so Anthropic caches it for 5 min.
      → saves ~90% of system-prompt input token cost on repeated calls.
    Block 1 (dynamic, NOT cached): token budget line — changes every iteration.

    The split ensures only the truly dynamic part is re-processed each call.
    """
    # ── Static block (will be cached) ─────────────────────────────────────────
    static_parts = [BASE_SYSTEM_PROMPT]
    if cached_memory:
        static_parts.append(cached_memory)
    static_text = "\n\n".join(static_parts)

    blocks: list[dict] = [
        {
            "type": "text",
            "text": static_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    # ── Dynamic block (budget warning, not cached) ─────────────────────────────
    if session_tokens_used > 0:
        pct = session_tokens_used / SESSION_TOKEN_BUDGET * 100
        if pct >= 90:
            dyn = (
                f"⚠️ TOKEN BUDGET CRITICAL: {session_tokens_used:,}/{SESSION_TOKEN_BUDGET:,} "
                f"({pct:.0f}%). Abort non-essential tool chains. Use ollama_route. "
                f"1-2 sentence responses only."
            )
        elif pct >= 70:
            dyn = (
                f"⚠️ TOKEN BUDGET WARNING: {session_tokens_used:,}/{SESSION_TOKEN_BUDGET:,} "
                f"({pct:.0f}%). Prefer ollama_route. Keep responses brief."
            )
        else:
            dyn = f"[Tokens: {session_tokens_used:,}/{SESSION_TOKEN_BUDGET:,} ({pct:.0f}%)]"
        blocks.append({"type": "text", "text": dyn})

    return blocks


def _apply_cache_control_to_tools(tools: list[dict]) -> list[dict]:
    """Add cache_control to the last tool definition so the full tool list is cached."""
    if not tools:
        return tools
    result = list(tools)
    result[-1] = {**result[-1], "cache_control": {"type": "ephemeral"}}
    return result


def _save_session_to_obsidian(conversation_history: list):
    """Write today's conversation summary to Obsidian Sessions/ folder."""
    try:
        user_msgs = [
            m["content"] for m in conversation_history
            if m["role"] == "user" and isinstance(m["content"], str)
        ][-8:]
        if not user_msgs:
            return
        import datetime
        today = datetime.date.today().isoformat()
        now   = datetime.datetime.now().strftime("%H:%M")
        lines = [f"## Session log — {now}\n"]
        for msg in user_msgs:
            lines.append(f"- {msg[:120]}")
        content = "\n".join(lines)
        target  = VAULT_PATH / "Sessions" / f"{today}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            with open(target, "a", encoding="utf-8") as f:
                f.write(f"\n{content}\n")
        else:
            header = (
                f"---\ntags: [session, hubert]\ndate: {today}\n---\n\n"
                f"# Session — {today}\n\n"
            )
            target.write_text(header + content + "\n", encoding="utf-8")
    except Exception:
        pass


class JarvisCore:
    def __init__(self):
        self.conversation_history: list[dict] = []
        self.client: anthropic.Anthropic | None = None
        self._session_tokens_in: int = 0   # cumulative input tokens this session
        self._session_tokens_out: int = 0  # cumulative output tokens this session
        self._setup_client()
        tool_registry.reload_all()
        tool_registry.start_hot_reload()

    @property
    def session_tokens_used(self) -> int:
        return self._session_tokens_in + self._session_tokens_out

    def get_token_stats(self) -> dict:
        total = self.session_tokens_used
        return {
            "input": self._session_tokens_in,
            "output": self._session_tokens_out,
            "total": total,
            "budget": SESSION_TOKEN_BUDGET,
            "pct": round(total / SESSION_TOKEN_BUDGET * 100, 1),
        }

    def _setup_client(self):
        key = get_api_key()
        if key:
            self.client = anthropic.Anthropic(api_key=key)

    def set_api_key(self, key: str):
        from config import set_api_key
        set_api_key(key)
        self.client = anthropic.Anthropic(api_key=key)

    def is_ready(self) -> bool:
        return self.client is not None

    def clear_history(self):
        _save_session_to_obsidian(self.conversation_history)
        self.conversation_history.clear()
        self._session_tokens_in = 0
        self._session_tokens_out = 0
        _token_stats["input"] = 0
        _token_stats["output"] = 0

    def _sanitize_history(self):
        """Fix orphaned tool_use/tool_result blocks that cause 400 errors.

        Pass 1: orphaned tool_use — assistant has tool_use but no matching tool_result
                in the next user turn. Injects stub results so the API doesn't complain.
        Pass 2: orphaned tool_result — a user turn references a tool_use_id that was
                pruned from history by _compress_history. Strips those stale blocks.
        """
        # ── Pass 1: stub missing tool_results ────────────────────────────────
        i = 0
        while i < len(self.conversation_history):
            turn = self.conversation_history[i]
            if turn["role"] == "assistant" and isinstance(turn["content"], list):
                tool_use_ids = [
                    b["id"] for b in turn["content"]
                    if isinstance(b, dict) and b.get("type") == "tool_use" and "id" in b
                ]
                if tool_use_ids:
                    next_turn = self.conversation_history[i + 1] if i + 1 < len(self.conversation_history) else None
                    if next_turn and next_turn["role"] == "user" and isinstance(next_turn.get("content"), list):
                        existing_ids = {
                            b.get("tool_use_id")
                            for b in next_turn["content"]
                            if isinstance(b, dict) and b.get("type") == "tool_result"
                        }
                        missing = [tid for tid in tool_use_ids if tid not in existing_ids]
                        if missing:
                            stubs = [{"type": "tool_result", "tool_use_id": tid, "content": "interrupted"} for tid in missing]
                            self.conversation_history[i + 1] = {
                                "role": "user",
                                "content": stubs + next_turn["content"],
                            }
                    elif not next_turn or next_turn["role"] != "user":
                        stubs = [{"type": "tool_result", "tool_use_id": tid, "content": "interrupted"} for tid in tool_use_ids]
                        self.conversation_history.insert(i + 1, {"role": "user", "content": stubs})
            i += 1

        # ── Pass 2: strip tool_results whose tool_use was pruned ─────────────
        valid_tool_use_ids: set[str] = set()
        for turn in self.conversation_history:
            if turn["role"] == "assistant" and isinstance(turn.get("content"), list):
                for b in turn["content"]:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and "id" in b:
                        valid_tool_use_ids.add(b["id"])

        for i, turn in enumerate(self.conversation_history):
            if turn["role"] == "user" and isinstance(turn.get("content"), list):
                filtered = [
                    b for b in turn["content"]
                    if not (
                        isinstance(b, dict)
                        and b.get("type") == "tool_result"
                        and b.get("tool_use_id") not in valid_tool_use_ids
                    )
                ]
                if len(filtered) != len(turn["content"]):
                    # Replace with filtered content; if nothing remains use a placeholder
                    self.conversation_history[i] = {
                        "role": "user",
                        "content": filtered if filtered else "[context trimmed]",
                    }

    def _compress_history(self):
        """Truncate old tool results to save tokens. Keeps last 6 turns intact.

        Compression thresholds (applied to turns outside the protected window):
        - Tool results > 150 chars → truncated to 150 chars
        - Large text assistant turns > 400 chars → truncated to 200 chars
        History is pruned to at most 40 turns when it grows past 50.
        """
        n = len(self.conversation_history)

        # Hard prune: drop oldest turns (pairs) if history is very long
        if n > 50:
            # Keep the most recent 36 turns (18 exchange pairs)
            self.conversation_history = self.conversation_history[-36:]
            n = len(self.conversation_history)

        if n < 14:
            return

        cutoff = n - 6  # protect the last 6 turns
        for i, turn in enumerate(self.conversation_history[:cutoff]):
            # Compress tool results in user turns
            if turn["role"] == "user" and isinstance(turn["content"], list):
                compressed, changed = [], False
                for block in turn["content"]:
                    raw = str(block.get("content", ""))
                    if block.get("type") == "tool_result" and len(raw) > 150:
                        compressed.append({
                            **block,
                            "content": raw[:150] + " …[compressed]",
                        })
                        changed = True
                    else:
                        compressed.append(block)
                if changed:
                    self.conversation_history[i] = {"role": "user", "content": compressed}

            # Compress large text blocks in assistant turns
            elif turn["role"] == "assistant" and isinstance(turn["content"], list):
                compressed, changed = [], False
                for block in turn["content"]:
                    if (block.get("type") == "text"
                            and len(block.get("text", "")) > 400):
                        compressed.append({
                            **block,
                            "text": block["text"][:200] + " …[compressed]",
                        })
                        changed = True
                    else:
                        compressed.append(block)
                if changed:
                    self.conversation_history[i] = {"role": "assistant", "content": compressed}

    def chat(
        self,
        user_message: str,
        image_path: str = None,
        on_text: Callable[[str], None] = None,
        on_tool_start: Callable[[str, dict], None] = None,
        on_tool_result: Callable[[str, str], None] = None,
        on_done: Callable[[], None] = None,
        on_error: Callable[[str], None] = None,
        on_status: Callable[[str], None] = None,
        on_usage: Callable[[int], None] = None,
        on_tool_groups: Callable[[list[str]], None] = None,
    ):
        """
        Send a message (with optional image) and run the agentic loop.
        Callbacks are called on the calling thread — use thread-safe UI updates.
        """
        if not self.client:
            if on_error:
                on_error("No API key set. Please enter your Anthropic API key.")
            return

        if image_path:
            import base64
            try:
                data = Path(image_path).read_bytes()
                b64 = base64.standard_b64encode(data).decode("utf-8")
                content = [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": user_message},
                ]
            except Exception as e:
                content = user_message
        else:
            content = user_message

        self.conversation_history.append({"role": "user", "content": content})

        try:
            self._run_agent_loop(
                on_text, on_tool_start, on_tool_result, on_done, on_error,
                on_status, on_usage, on_tool_groups,
            )
        except Exception as e:
            if on_error:
                on_error(f"Error: {e}")

    def _run_agent_loop(
        self, on_text, on_tool_start, on_tool_result, on_done, on_error,
        on_status=None, on_usage=None, on_tool_groups=None,
    ):
        """Agentic loop: call Claude, handle tool calls in parallel, repeat until done.

        Optimizations applied per call:
        - Tool filtering: only the relevant tool groups are sent (saves ~7k tokens/call)
        - Prompt caching: static system block + tools list are cached by Anthropic
        - Model routing: Haiku for simple messages, Sonnet for complex/agentic ones
        """
        import json as _json
        self._sanitize_history()
        self._compress_history()
        max_iterations = 25
        retry_attempt = 0

        # ── Pre-call setup (done once, outside the iteration loop) ────────────
        # 1. Load memory block from disk once — reused across all iterations
        cached_memory = _load_memory_block()

        # 2. Classify task to select relevant tool groups (fast keyword check)
        #    The original user message is in the last history entry.
        user_msg_text = ""
        for turn in reversed(self.conversation_history):
            if turn["role"] == "user":
                c = turn["content"]
                if isinstance(c, str):
                    user_msg_text = c
                elif isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "text":
                            user_msg_text = b.get("text", "")
                            break
                break

        active_groups = _classify_task_groups_fast(user_msg_text)

        # 3. Select model — Haiku for simple conversational messages, Sonnet otherwise
        model = _select_model(user_msg_text)

        # 4. Get filtered tool list and apply cache_control to last entry
        active_tools = tool_registry.get_tool_definitions_for_groups(active_groups)
        cached_tools = _apply_cache_control_to_tools(active_tools)

        # Notify UI of which tool groups are active
        if on_tool_groups:
            on_tool_groups(active_groups)
        try:
            import ui_bridge
            ui_bridge.push("tool_groups_active",
                           groups=active_groups,
                           model=model,
                           tool_count=len(active_tools))
        except Exception:
            pass

        if on_status:
            grp_str = ",".join(active_groups) if active_groups else "core"
            on_status(
                f"[{model.split('-')[1]}] tools: core+{grp_str} ({len(active_tools)})"
            )

        for iteration in range(max_iterations):
            content_blocks     = []
            current_tool_calls = []

            # Rebuild system blocks each iteration so token budget stays current
            # (static block is cached by Anthropic, only the tiny dynamic block changes)
            system_blocks = _build_system_prompt_blocks(
                session_tokens_used=self.session_tokens_used,
                cached_memory=cached_memory,
            )

            # After the first tool call we may need additional tool groups.
            # Re-classify based on expanded context but keep the same model.
            if iteration > 0 and current_tool_calls:
                pass  # tool groups stay fixed for the loop; escalate in next chat turn

            try:
                with self.client.messages.stream(
                    model=model,
                    max_tokens=2048,
                    system=system_blocks,
                    tools=cached_tools,
                    messages=self.conversation_history,
                ) as stream:
                    current_block_type    = None
                    current_tool_name     = None
                    current_tool_id       = None
                    current_tool_input_str = ""

                    for event in stream:
                        etype = event.type

                        if etype == "content_block_start":
                            blk = event.content_block
                            current_block_type = blk.type
                            if blk.type == "tool_use":
                                current_tool_name      = blk.name
                                current_tool_id        = blk.id
                                current_tool_input_str = ""

                        elif etype == "content_block_delta":
                            delta = event.delta
                            if delta.type == "text_delta":
                                if on_text:
                                    on_text(delta.text)
                            elif delta.type == "input_json_delta":
                                current_tool_input_str += delta.partial_json

                        elif etype == "content_block_stop":
                            if current_block_type == "tool_use" and current_tool_name:
                                try:
                                    tool_input = _json.loads(current_tool_input_str) if current_tool_input_str else {}
                                except _json.JSONDecodeError:
                                    tool_input = {}
                                current_tool_calls.append({
                                    "id":    current_tool_id,
                                    "name":  current_tool_name,
                                    "input": tool_input,
                                })
                                current_block_type = None
                                current_tool_name  = None

                    final_msg   = stream.get_final_message()
                    stop_reason = final_msg.stop_reason
                    content_blocks = final_msg.content
                    if final_msg.usage:
                        added_in  = getattr(final_msg.usage, "input_tokens",  0)
                        added_out = getattr(final_msg.usage, "output_tokens", 0)
                        self._session_tokens_in  += added_in
                        self._session_tokens_out += added_out
                        # Sync to module-level dict so tools can read it
                        _token_stats["input"]  = self._session_tokens_in
                        _token_stats["output"] = self._session_tokens_out
                        # Daily counter — persists across restarts, resets at midnight
                        _token_stats["daily"] += added_in + added_out
                        _save_daily_tokens(_token_stats["daily"])
                        if on_usage:
                            on_usage(self.session_tokens_used)

            except anthropic.APIStatusError as e:
                if e.status_code == 429:
                    if retry_attempt < len(_RETRY_DELAYS):
                        delay = _RETRY_DELAYS[retry_attempt]
                        retry_attempt += 1
                        status_msg = (
                            f"Rate limit reached - retrying in {delay}s "
                            f"(attempt {retry_attempt}/{len(_RETRY_DELAYS)})..."
                        )
                        _log_error(f"429 rate limit (retry {retry_attempt})", e)
                        if on_status:
                            on_status(status_msg)
                        time.sleep(delay)
                        continue
                    else:
                        _log_error(f"APIStatusError 429 exhausted (iteration {iteration})", e)
                        if on_error:
                            on_error("Rate limit reached after 3 retries. Please wait a moment and try again.")
                        return
                elif e.status_code == 400 and (
                    "tool_use" in str(e) or "tool_result" in str(e)
                ):
                    # Orphaned tool_use/tool_result blocks from a pruned or interrupted session.
                    # Strip offending assistant turns and let _sanitize_history clean up the rest.
                    _log_error(f"400 tool orphan — stripping bad history (iteration {iteration})", e)
                    cleaned = []
                    for turn in self.conversation_history:
                        if turn["role"] == "assistant" and isinstance(turn.get("content"), list):
                            if any(b.get("type") == "tool_use" for b in turn["content"] if isinstance(b, dict)):
                                continue  # drop the offending assistant turn
                        cleaned.append(turn)
                    self.conversation_history = cleaned
                    self._sanitize_history()
                    if on_status:
                        on_status("Repaired conversation history — retrying…")
                    continue
                else:
                    msg = f"API error {e.status_code}: {e.message}"
                    _log_error(f"APIStatusError (iteration {iteration})", e)
                    if on_error:
                        on_error(msg)
                    return
            except anthropic.APIConnectionError as e:
                _log_error(f"APIConnectionError (iteration {iteration})", e)
                if on_error:
                    on_error("Connection error — check your internet connection.")
                return
            except anthropic.APIError as e:
                _log_error(f"APIError (iteration {iteration})", e)
                if on_error:
                    on_error(f"API error: {e}")
                return
            except Exception as e:
                _log_error(f"Unexpected stream error (iteration {iteration})", e)
                if on_error:
                    on_error(f"Unexpected error: {e}")
                return

            # Serialize assistant turn — only include fields the API accepts on input.
            # model_dump() includes internal Pydantic fields (e.g. parsed_output) that
            # the API rejects with 400 "Extra inputs are not permitted".
            def _serialize_block(b):
                t = getattr(b, "type", None)
                if t == "text":
                    return {"type": "text", "text": b.text}
                elif t == "tool_use":
                    return {"type": "tool_use", "id": b.id,
                            "name": b.name, "input": b.input}
                elif t == "thinking":
                    return {"type": "thinking", "thinking": b.thinking}
                else:
                    # Unknown block type — keep only safe keys
                    try:
                        d = b.model_dump()
                        safe = {"type", "text", "id", "name", "input", "thinking"}
                        return {k: v for k, v in d.items() if k in safe}
                    except Exception:
                        return {"type": "text", "text": str(b)}

            serialized = [_serialize_block(b) for b in content_blocks]
            self.conversation_history.append({
                "role": "assistant",
                "content": serialized,
            })

            if stop_reason == "end_turn" or not current_tool_calls:
                break

            # Execute tool calls — parallel when multiple
            def _exec_tool(tc):
                name, inp = tc["name"], tc["input"]
                try:
                    if on_tool_start:
                        on_tool_start(name, inp)
                    result = tool_registry.execute_tool(name, inp)
                except Exception as exc:
                    _log_error(f"Tool execution: {name}", exc)
                    result = f"Tool error ({name}): {exc}"
                if on_tool_result:
                    on_tool_result(name, result)
                return {"type": "tool_result", "tool_use_id": tc["id"], "content": str(result)}

            try:
                if len(current_tool_calls) == 1:
                    tool_results = [_exec_tool(current_tool_calls[0])]
                else:
                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=len(current_tool_calls)
                    ) as pool:
                        tool_results = list(pool.map(_exec_tool, current_tool_calls))
            except Exception as e:
                _log_error("Tool executor pool", e)
                if on_error:
                    on_error(f"Tool executor error: {e}")
                return

            self.conversation_history.append({
                "role": "user",
                "content": tool_results,
            })

        if on_done:
            on_done()


def chat_in_thread(core: JarvisCore, message: str, image_path: str = None, **callbacks):
    """Run chat in a background thread."""
    t = threading.Thread(
        target=core.chat,
        args=(message,),
        kwargs={"image_path": image_path, **callbacks},
        daemon=True,
    )
    t.start()
    return t
