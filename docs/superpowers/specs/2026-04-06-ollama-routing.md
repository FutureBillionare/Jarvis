# Ollama Local Subagent Routing + Rate Limit Retry

**Date:** 2026-04-06  
**Status:** Approved

## Overview

Two related improvements to HUBERT's backend:

1. **Ollama routing** — swarm sub-agents attempt tasks locally via llama3 first. llama3 self-assesses each task before trying; if it judges the task is out of scope, it escalates to Claude Haiku. Main HUBERT conversation is unaffected.
2. **Rate limit retry** — `jarvis_core.py` retries on HTTP 429 up to 3 times (5s / 15s / 30s) with non-fatal UI status messages during the wait, instead of surfacing a hard error.

---

## Architecture

### New file: `ollama_core.py`

Lives at `C:\Users\Jake\Jarvis\ollama_core.py` alongside `jarvis_core.py`.

```
OllamaCore
├── BASE_URL = "http://localhost:11434"
├── MODEL    = "llama3"
├── assess_task(task: str) -> bool
│     Sends a tight YES/NO prompt to llama3.
│     Returns True  → llama3 will attempt it.
│     Returns False → escalate to Haiku.
└── run_task(system: str, task: str, max_tokens: int = 400) -> str
      Calls /api/chat with the given system + user message.
      Returns the response text, or raises on connection error.
```

**`assess_task` prompt:**
```
System: You are a capability assessor. Answer ONLY "YES" or "NO".
User:   Can a small open-source LLM (7B parameters, no internet, no tools) 
        complete the following task accurately?
        
        Task: {task}
        
        Answer YES only if the task requires only text reasoning, summarisation, 
        categorisation, formatting, or simple factual recall within common 
        knowledge. Answer NO if it requires real-time data, complex code 
        generation, multi-step tool calls, or advanced reasoning.
```

First word of the response is checked: `"YES"` → True, anything else → False.

**Connection guard:** If `requests.get(BASE_URL)` times out in < 1s, `ollama_available()` returns False and both swarm tools skip Ollama entirely (no error surfaced to the user).

---

### Modified: `tools/custom/swarm_dispatch.py`

Current flow: every task → Claude Haiku.

New flow per task:
```
ollama_available()?
  no  → Haiku (unchanged)
  yes →
    assess_task(task)?
      True  → ollama run_task()
              error? → Haiku fallback
      False → Haiku
```

The existing batching, Obsidian writing, and UI bridge calls are unchanged.

---

### Modified: `tools/custom/swarm_bridge.py`

Same routing logic as above, applied to each of the 2–6 tasks.  
`tier` param is preserved: if `tier="smart"` is explicitly requested, skip Ollama and go straight to Sonnet (caller is signalling it needs Claude).

---

### Modified: `jarvis_core.py` — 429 retry

In `_run_agent_loop()` (or whichever call site currently catches `APIStatusError`):

```python
RETRY_DELAYS = [5, 15, 30]

for attempt, delay in enumerate(RETRY_DELAYS + [None]):
    try:
        # existing API call
        break
    except anthropic.APIStatusError as e:
        if e.status_code == 429 and delay is not None:
            msg = f"⏳ Rate limit hit — retrying in {delay}s… (attempt {attempt+1}/3)"
            if on_status:
                on_status(msg)       # surfaces to UI as a grey status line
            time.sleep(delay)
        else:
            msg = f"API error {e.status_code}: {e.message}"
            if on_error:
                on_error(msg)
            return
```

`on_status` is a new optional callback (alongside existing `on_error`) that the UI displays as a non-fatal status message. In `main.py`, the `_run()` thread already passes `on_error` to `jarvis_core`; `on_status` is wired the same way and appends a grey italic line to `ChatDisplay` (same widget as regular messages, but styled differently — e.g., `fg_color=BG`, `text_color="#888888"`). It is not dismissible — it scrolls away naturally as conversation continues.

---

### New HUBERT tool: `tools/custom/ollama_route.py`

Per CLAUDE.md, every new capability needs a custom tool. This tool lets HUBERT explicitly ask Ollama a question or run a task, bypassing the swarm.

```python
TOOL_DEFINITION = {
    "name": "ollama_route",
    "description": "Run a task directly on the local Ollama llama3 model. Use for lightweight text reasoning, summarisation, or categorisation tasks where speed matters more than quality.",
    ...
}
```

---

## What Is Unchanged

- Main HUBERT conversation always uses `claude-sonnet-4-6` — Ollama is never in that path.
- `jarvis_core.py` agent loop structure, tool execution, memory, all tool files other than the two swarm ones.
- SwarmPanel UI, node/edge rendering, activity feed.
- Obsidian vault writing, category logic, summary notes.

---

## Files Changed

| File | Change |
|------|--------|
| `ollama_core.py` | New — `OllamaCore` class |
| `tools/custom/swarm_dispatch.py` | Route tasks through Ollama assessor first |
| `tools/custom/swarm_bridge.py` | Same routing; skip Ollama if `tier="smart"` |
| `jarvis_core.py` | Add 429 retry with status callbacks |
| `tools/custom/ollama_route.py` | New HUBERT tool for direct Ollama access |

No new UI files. `on_status` callback plumbed through existing UI bridge patterns.
