# CC Swarm Integration Design

**Date:** 2026-04-14  
**Goal:** Surface Claude Code CLI tool activity in the SwarmPanel node graph and activity feed so Jake can watch what Claude Code is doing in real time.

---

## Problem

`claude_code_backend.py` only parses `text_delta` stream events from the claude CLI subprocess. The CC mode branch in `_send()` passes zero swarm callbacks, so the SwarmPanel is completely silent during CC sessions — no tool nodes, no pulses, no activity feed entries.

---

## Architecture

Three targeted changes. No chat display changes. No drawer changes.

### 1. `claude_code_backend.py` — StatefulStreamParser

Replace `_extract_text_delta` (a one-shot function) with a `StreamParser` class that maintains state across stream-json event lines.

**State machine:**

| Event | Action |
|-------|--------|
| `content_block_start` with `type: tool_use` | Save `{id, name}` to `current_tool`, reset `input_buf` |
| `input_json_delta` | Append `partial_json` to `input_buf` |
| `content_block_stop` (when `current_tool` set) | Parse `input_buf` as JSON → fire `on_tool_start(name, params)` → record `tool_id_to_name[id] = name` |
| `text_delta` | Fire `on_text(text)` (unchanged) |
| `user` message event with `tool_result` content | Look up `tool_id_to_name[tool_use_id]` → fire `on_tool_result(name, result_text)` |

**`chat_in_thread` new signature:**

```python
def chat_in_thread(
    message, history, last_session,
    on_text, on_done, on_error,
    on_tool_start=None,    # (name: str, params: dict) -> None
    on_tool_result=None,   # (name: str, result: str) -> None
    on_status=None,        # (msg: str) -> None
    **kwargs
)
```

`on_status` fires three times: `"CC ▶ session started"` at subprocess spawn, `"CC ✓ done"` on exit code 0, `"CC ✗ error"` on failure.

---

### 2. `main.py` — Wire CC callbacks in `_send()`

In the CC mode branch of `_send()`, add:

```python
_cc_chat(
    api_text,
    history       = ...,
    last_session  = ...,
    on_text       = _on_text_cc,
    on_done       = _on_done_cc,
    on_error      = lambda e: self._q_put(self._error, e),
    on_tool_start = lambda n, p: self._q_put(self.swarm_panel.on_cc_tool_call, n),
    on_tool_result= lambda n, r: self._q_put(self.swarm_panel.on_tool_result, n, r),
    on_status     = lambda s: self._q_put(self.swarm_panel._log_event, "sys", s),
)
```

No changes to chat display, `_tool_start`, `_tool_result`, or the drawer.

---

### 3. `SwarmPanel` — CC Node + Pulse Source

**New methods:**

- `add_cc_node()` — creates a node `"CC"` at a fixed offset from HUBERT (kind=`"agent"`, label=`"CC"`), adds a HUBERT→CC edge
- `remove_cc_node()` — removes the CC node and its edge

**Modified method:**

`on_tool_call(tool_name, source="HUBERT")` — the pulse origin is now parameterized. When called from CC mode, `source="CC"`, so pulses travel CC→tool instead of HUBERT→tool.

Add a `on_cc_tool_call(tool_name)` alias that calls `self.on_tool_call(tool_name, source="CC")`. This is needed because `_q_put(fn, *args)` only supports positional args — kwarg routing through the queue isn't possible.

**Lifecycle:**

- `HubertApp.__init__` calls `swarm_panel.add_cc_node()` (CC is the default mode)
- Mode toggle button calls `add_cc_node()` / `remove_cc_node()` when switching in/out of CC mode

---

## Data Flow

```
claude CLI subprocess
  └─ stream-json lines (stdout)
       └─ StreamParser
            ├─ text_delta        → on_text   → chat display
            ├─ tool_use start    → on_tool_start → swarm_panel.on_tool_call(name, source="CC")
            ├─ tool_use result   → on_tool_result → swarm_panel.on_tool_result(name, result)
            └─ lifecycle events  → on_status → swarm_panel._log_event("sys", msg)
```

---

## What Does NOT Change

- Chat display (no tool call bubbles for CC tools)
- Drawer / subagent tracking
- Native HUBERT mode (API)
- Ollama mode
- SwarmPanel rendering logic (just the node data and pulse source)

---

## Files Changed

| File | Change |
|------|--------|
| `claude_code_backend.py` | Replace `_extract_text_delta` with `StreamParser`; extend `chat_in_thread` |
| `main.py` (`_send`) | Add 3 callbacks to `_cc_chat` call |
| `main.py` (`SwarmPanel`) | Add `add_cc_node`, `remove_cc_node`; parameterize `on_tool_call` source |
| `main.py` (`HubertApp.__init__`) | Call `add_cc_node()` on boot |
| `main.py` (mode toggle) | Call `add_cc_node`/`remove_cc_node` on switch |
