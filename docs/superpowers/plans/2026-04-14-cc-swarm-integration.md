# CC Swarm Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface Claude Code CLI tool activity (tool calls, results, lifecycle) in the SwarmPanel node graph and activity feed in real time.

**Architecture:** Replace the one-shot `_extract_text_delta` function in `claude_code_backend.py` with a stateful `StreamParser` class that detects tool use events from the stream-json output. Wire three new callbacks (`on_tool_start`, `on_tool_result`, `on_status`) into the CC mode `_send()` branch. Add a persistent `"CC"` node to the SwarmPanel that acts as the pulse source for CC tool calls.

**Tech Stack:** Python 3.13, CustomTkinter, Claude Code CLI stream-json format

---

## File Map

| File | Change |
|------|--------|
| `claude_code_backend.py` | Add `StreamParser` class; extend `chat_in_thread` with 3 new callbacks |
| `tests/test_cc_stream_parser.py` | New — unit tests for `StreamParser` |
| `main.py` — `SwarmPanel` | Add `add_cc_node`, `remove_cc_node`, `on_cc_tool_call`; parameterize `on_tool_call` source |
| `main.py` — `HubertApp._send` | Wire `on_tool_start`, `on_tool_result`, `on_status` into `_cc_chat` call |
| `main.py` — `HubertApp.__init__` & mode toggle | Call `add_cc_node` / `remove_cc_node` on mode switch |

---

## Task 1: Write failing tests for StreamParser

**Files:**
- Create: `tests/test_cc_stream_parser.py`

The `StreamParser` class doesn't exist yet — all tests should fail with `ImportError`.

- [ ] **Step 1: Create the test file**

```python
# tests/test_cc_stream_parser.py
import json
import pytest
from claude_code_backend import StreamParser


def _lines(*events):
    """Serialize dicts to newline-separated JSON strings."""
    return [json.dumps(e) + "\n" for e in events]


def test_text_delta_fires_on_text():
    received = []
    parser = StreamParser(on_text=received.append)
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_delta", "index": 0,
                  "delta": {"type": "text_delta", "text": "hello"}}
    }))
    assert received == ["hello"]


def test_tool_use_fires_on_tool_start():
    starts = []
    parser = StreamParser(on_tool_start=lambda n, p: starts.append((n, p)))

    # content_block_start with tool_use
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_start", "index": 1,
                  "content_block": {"type": "tool_use", "id": "tu_1", "name": "Bash", "input": {}}}
    }))
    # input_json_delta
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_delta", "index": 1,
                  "delta": {"type": "input_json_delta", "partial_json": '{"command": "ls"}'}}
    }))
    # content_block_stop
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_stop", "index": 1}
    }))

    assert len(starts) == 1
    assert starts[0] == ("Bash", {"command": "ls"})


def test_tool_result_fires_on_tool_result():
    starts = []
    results = []
    parser = StreamParser(
        on_tool_start=lambda n, p: starts.append((n, p)),
        on_tool_result=lambda n, r: results.append((n, r)),
    )

    # First: register the tool call so the id is known
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_start", "index": 0,
                  "content_block": {"type": "tool_use", "id": "tu_abc", "name": "Read", "input": {}}}
    }))
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_stop", "index": 0}
    }))

    # Then: user message with tool_result
    parser.feed(json.dumps({
        "type": "user",
        "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu_abc", "content": "file contents here"}
        ]}
    }))

    assert results == [("Read", "file contents here")]


def test_tool_result_with_list_content():
    results = []
    parser = StreamParser(on_tool_result=lambda n, r: results.append((n, r)))

    # Register tool id without firing on_tool_start (just need the mapping)
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_start", "index": 0,
                  "content_block": {"type": "tool_use", "id": "tu_xyz", "name": "Grep", "input": {}}}
    }))
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_stop", "index": 0}
    }))

    parser.feed(json.dumps({
        "type": "user",
        "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu_xyz",
             "content": [{"type": "text", "text": "match line 1"}, {"type": "text", "text": "match line 2"}]}
        ]}
    }))

    assert results[0] == ("Grep", "match line 1 match line 2")


def test_invalid_json_ignored():
    received = []
    parser = StreamParser(on_text=received.append)
    parser.feed("not json at all\n")
    assert received == []


def test_non_tool_content_block_start_ignored():
    starts = []
    parser = StreamParser(on_tool_start=lambda n, p: starts.append((n, p)))
    # text content block — should not start a tool accumulation
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_start", "index": 0,
                  "content_block": {"type": "text"}}
    }))
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_stop", "index": 0}
    }))
    assert starts == []


def test_split_input_json_accumulated():
    """input_json_delta arrives in multiple chunks — final params should be complete."""
    starts = []
    parser = StreamParser(on_tool_start=lambda n, p: starts.append((n, p)))

    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_start", "index": 0,
                  "content_block": {"type": "tool_use", "id": "tu_split", "name": "Edit", "input": {}}}
    }))
    # Three partial JSON chunks
    for chunk in ['{"file_path": "/foo/bar"', ', "old_string": "x"', ', "new_string": "y"}']:
        parser.feed(json.dumps({
            "type": "stream_event",
            "event": {"type": "content_block_delta", "index": 0,
                      "delta": {"type": "input_json_delta", "partial_json": chunk}}
        }))
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_stop", "index": 0}
    }))

    assert starts == [("Edit", {"file_path": "/foo/bar", "old_string": "x", "new_string": "y"})]
```

- [ ] **Step 2: Run tests to confirm they all fail with ImportError**

```bash
cd /Users/jakegoncalves/Jarvis && python -m pytest tests/test_cc_stream_parser.py -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name 'StreamParser' from 'claude_code_backend'`

---

## Task 2: Implement StreamParser and extend chat_in_thread

**Files:**
- Modify: `claude_code_backend.py` (full rewrite — replace `_extract_text_delta`, extend `chat_in_thread`)

- [ ] **Step 1: Replace the contents of claude_code_backend.py**

```python
"""
Claude Code CLI backend — routes HUBERT messages through the `claude` CLI subprocess.
Uses the user's Claude.ai subscription (Pro/Max) instead of Anthropic API credits.

Streaming strategy: --output-format stream-json + --include-partial-messages emits
individual token deltas via stream_event → content_block_delta → text_delta.
Tool calls arrive as content_block_start (tool_use) → input_json_delta → content_block_stop.
Tool results arrive as user message events with tool_result content blocks.

History strategy: caller passes a list of {role, content} dicts; this module injects
them as a conversation prefix in the prompt so the stateless `claude -p` call has context.
"""
import json
import subprocess
import threading
import shutil
from typing import Callable

_HISTORY_TURNS = 24   # max turns to inject (12 exchanges)
_TURN_MAX_CHARS = 600 # truncate very long turns in the history prefix


def _find_claude_bin() -> str | None:
    return shutil.which("claude")


_EXTRA_FLAGS = [
    "--dangerously-skip-permissions",   # user-approved: skip all tool permission prompts
    "--no-session-persistence",
    "--output-format", "stream-json",
    "--include-partial-messages",
    "--verbose",
]


def _build_prompt(message: str, history: list[dict] | None,
                  last_session: str | None) -> str:
    """
    Prepend conversation history (and optional last-session recap) to the message
    so claude -p has full context despite being stateless.
    """
    parts = []

    if last_session:
        parts.append(
            f"[PREVIOUS SESSION RECAP]\n{last_session.strip()}\n[END RECAP]"
        )

    if history:
        recent = history[-_HISTORY_TURNS:]
        lines = []
        for turn in recent:
            role    = "User" if turn["role"] == "user" else "HUBERT"
            content = turn["content"]
            if len(content) > _TURN_MAX_CHARS:
                content = content[:_TURN_MAX_CHARS] + "…"
            lines.append(f"{role}: {content}")
        if lines:
            parts.append(
                "[CONVERSATION HISTORY]\n"
                + "\n".join(lines)
                + "\n[END HISTORY]"
            )

    parts.append(f"User: {message}")
    return "\n\n".join(parts)


class StreamParser:
    """
    Stateful parser for the claude CLI stream-json output.

    Call .feed(line) for each raw stdout line. Fires callbacks:
      on_text(text)             — streaming text delta
      on_tool_start(name, params) — tool call detected (name=str, params=dict)
      on_tool_result(name, result) — tool result received (result=str)
    """

    def __init__(
        self,
        on_text: Callable[[str], None] | None = None,
        on_tool_start: Callable[[str, dict], None] | None = None,
        on_tool_result: Callable[[str, str], None] | None = None,
    ):
        self._on_text        = on_text
        self._on_tool_start  = on_tool_start
        self._on_tool_result = on_tool_result
        self._current_tool: dict | None = None   # {"id": ..., "name": ...}
        self._input_buf: str = ""
        self._tool_id_to_name: dict[str, str] = {}

    def feed(self, line: str) -> None:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return

        t = event.get("type")

        if t == "stream_event":
            self._handle_stream_event(event.get("event", {}))
        elif t == "user":
            self._handle_user_message(event.get("message", {}))

    def _handle_stream_event(self, inner: dict) -> None:
        inner_type = inner.get("type")

        if inner_type == "content_block_start":
            cb = inner.get("content_block", {})
            if cb.get("type") == "tool_use":
                self._current_tool = {"id": cb["id"], "name": cb["name"]}
                self._input_buf = ""

        elif inner_type == "content_block_delta":
            delta = inner.get("delta", {})
            dtype = delta.get("type")
            if dtype == "text_delta":
                text = delta.get("text")
                if text and self._on_text:
                    self._on_text(text)
            elif dtype == "input_json_delta" and self._current_tool is not None:
                self._input_buf += delta.get("partial_json", "")

        elif inner_type == "content_block_stop":
            if self._current_tool is not None:
                name = self._current_tool["name"]
                tid  = self._current_tool["id"]
                try:
                    params = json.loads(self._input_buf) if self._input_buf else {}
                except (json.JSONDecodeError, ValueError):
                    params = {}
                self._tool_id_to_name[tid] = name
                if self._on_tool_start:
                    self._on_tool_start(name, params)
                self._current_tool = None
                self._input_buf = ""

    def _handle_user_message(self, msg: dict) -> None:
        content = msg.get("content", [])
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            tool_use_id    = block.get("tool_use_id", "")
            result_content = block.get("content", "")
            name = self._tool_id_to_name.get(tool_use_id, tool_use_id)
            if isinstance(result_content, list):
                result_text = " ".join(
                    b.get("text", "")
                    for b in result_content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                result_text = str(result_content)
            if self._on_tool_result:
                self._on_tool_result(name, result_text)


def chat_in_thread(
    message: str,
    history: list[dict] | None = None,
    last_session: str | None = None,
    on_text: Callable[[str], None] = None,
    on_done: Callable[[], None] = None,
    on_error: Callable[[str], None] = None,
    on_tool_start: Callable[[str, dict], None] = None,
    on_tool_result: Callable[[str, str], None] = None,
    on_status: Callable[[str], None] = None,
    **kwargs,
):
    """
    Spawn `claude -p <prompt>` with conversation history injected in the prompt.
    Streams text deltas via on_text, tool events via on_tool_start/on_tool_result,
    lifecycle events via on_status, then calls on_done/on_error.
    """
    claude_bin = _find_claude_bin()
    if not claude_bin:
        if on_error:
            on_error(
                "claude CLI not found in PATH.\n"
                "Install: npm install -g @anthropic-ai/claude-code"
            )
        return

    prompt = _build_prompt(message, history, last_session)

    def _run():
        try:
            cmd = [claude_bin, "-p", prompt] + _EXTRA_FLAGS
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            if on_status:
                on_status("CC ▶ session started")
            parser = StreamParser(
                on_text=on_text,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
            )
            for raw_line in proc.stdout:
                parser.feed(raw_line)
            proc.wait()
            stderr_out = proc.stderr.read().strip()
            if proc.returncode == 0:
                if on_status:
                    on_status("CC ✓ done")
                if on_done:
                    on_done()
            else:
                if on_status:
                    on_status("CC ✗ error")
                if on_error:
                    on_error(stderr_out or f"claude exited with code {proc.returncode}")
        except Exception as exc:
            if on_status:
                on_status("CC ✗ error")
            if on_error:
                on_error(str(exc))

    threading.Thread(target=_run, daemon=True).start()
```

- [ ] **Step 2: Run the tests**

```bash
cd /Users/jakegoncalves/Jarvis && python -m pytest tests/test_cc_stream_parser.py -v
```

Expected: all 7 tests pass. If any fail, read the error — most likely a JSON structure mismatch in `_handle_user_message` or `_handle_stream_event`.

- [ ] **Step 3: Commit**

```bash
cd /Users/jakegoncalves/Jarvis && git add claude_code_backend.py tests/test_cc_stream_parser.py && git commit -m "feat: replace _extract_text_delta with StatefulStreamParser for tool event detection"
```

---

## Task 3: Extend SwarmPanel with CC node and parameterized pulse source

**Files:**
- Modify: `main.py` — `SwarmPanel` class (lines ~3081–3117)

- [ ] **Step 1: Modify `on_tool_call` to accept a `source` parameter**

Find `on_tool_call` at line ~3081. Replace it:

```python
    def on_tool_call(self, tool_name: str, source: str = "HUBERT"):
        nid = f"tool_{tool_name}"
        if nid not in self._nodes:
            x, y = self._place_node("tool")
            self._nodes[nid] = {
                "x": x, "y": y, "kind": "tool",
                "label": tool_name.replace("_", " "),
                "last_active": self._t,
            }
            self._add_edge(source, nid)
        else:
            self._nodes[nid]["last_active"] = self._t
        self._fire_pulse(source, nid, GREEN)
        self._log_event("tool", f"⚙  {tool_name}")
```

- [ ] **Step 2: Add `add_cc_node`, `remove_cc_node`, and `on_cc_tool_call` after `on_tool_call`**

Insert these three methods immediately after the modified `on_tool_call`:

```python
    def add_cc_node(self):
        """Add a Claude Code CLI node connected to HUBERT (call when entering CC mode)."""
        if "CC" in self._nodes:
            return
        hub = self._nodes["HUBERT"]
        x = hub["x"]
        y = hub["y"] + 70
        self._nodes["CC"] = {
            "x": x, "y": y, "kind": "agent",
            "label": "CC", "last_active": self._t,
        }
        self._add_edge("HUBERT", "CC")

    def remove_cc_node(self):
        """Remove the CC node and all its edges (call when leaving CC mode)."""
        self._nodes.pop("CC", None)
        self._edges = [(f, t) for f, t in self._edges if f != "CC" and t != "CC"]

    def on_cc_tool_call(self, tool_name: str):
        """Route a CC-mode tool call through the CC node instead of HUBERT."""
        self.on_tool_call(tool_name, source="CC")
```

- [ ] **Step 3: Verify the app still imports cleanly**

```bash
cd /Users/jakegoncalves/Jarvis && python -c "import main; print('OK')" 2>&1 | head -5
```

Expected: `OK` (may take a few seconds for tkinter init to fail — any `ImportError` or `SyntaxError` is a bug).

- [ ] **Step 4: Commit**

```bash
cd /Users/jakegoncalves/Jarvis && git add main.py && git commit -m "feat: add CC node to SwarmPanel with parameterized pulse source"
```

---

## Task 4: Wire CC callbacks in _send() and manage CC node on mode switch

**Files:**
- Modify: `main.py` — `HubertApp._send` (line ~4080), `HubertApp.__init__` (line ~3644), mode toggle (line ~4325)

- [ ] **Step 1: Wire the three new callbacks into the `_cc_chat` call in `_send()`**

Find the `_cc_chat(...)` call at line ~4080. It currently looks like:

```python
            _cc_chat(
                api_text,
                history      = self._cc_history[:-1],
                last_session = _last_sess,
                on_text      = _on_text_cc,
                on_done      = _on_done_cc,
                on_error     = lambda e: self._q_put(self._error, e),
            )
```

Replace it with:

```python
            _cc_chat(
                api_text,
                history        = self._cc_history[:-1],
                last_session   = _last_sess,
                on_text        = _on_text_cc,
                on_done        = _on_done_cc,
                on_error       = lambda e: self._q_put(self._error, e),
                on_tool_start  = lambda n, p: self._q_put(self.swarm_panel.on_cc_tool_call, n),
                on_tool_result = lambda n, r: self._q_put(self.swarm_panel.on_tool_result, n, r),
                on_status      = lambda s: self._q_put(self.swarm_panel._log_event, "sys", s),
            )
```

- [ ] **Step 2: Call `add_cc_node()` on boot**

Find the line at ~3646 where `self.swarm_panel` is assigned and the paned widget is set up:

```python
        self.swarm_panel = SwarmPanel(self._paned)
        self._paned.add(self.swarm_panel, minsize=180, width=300, stretch="never")
```

Add `add_cc_node()` immediately after (CC is the default mode):

```python
        self.swarm_panel = SwarmPanel(self._paned)
        self._paned.add(self.swarm_panel, minsize=180, width=300, stretch="never")
        self.swarm_panel.add_cc_node()   # CC is the default mode
```

- [ ] **Step 3: Toggle the CC node when switching modes**

Find the mode toggle at line ~4325 (the `_toggle_mode` method). There are two branches:

**Switch TO Ollama** (around line 4325–4333):
```python
            self._ollama_mode      = True
            self._claude_code_mode = False
            self.core = self._ollama_core
```
Add `self.swarm_panel.remove_cc_node()` immediately after setting `_claude_code_mode = False`:
```python
            self._ollama_mode      = True
            self._claude_code_mode = False
            self.swarm_panel.remove_cc_node()
            self.core = self._ollama_core
```

**Switch BACK to Claude Code** (around line 4336–4343):
```python
            self._ollama_mode      = False
            self._claude_code_mode = True
            self.core = self._claude_core
```
Add `self.swarm_panel.add_cc_node()` immediately after:
```python
            self._ollama_mode      = False
            self._claude_code_mode = True
            self.swarm_panel.add_cc_node()
            self.core = self._claude_core
```

- [ ] **Step 4: Verify the app still imports cleanly**

```bash
cd /Users/jakegoncalves/Jarvis && python -c "import main; print('OK')" 2>&1 | head -5
```

Expected: `OK`

- [ ] **Step 5: Run all tests to confirm nothing regressed**

```bash
cd /Users/jakegoncalves/Jarvis && python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all previously passing tests still pass, all 7 new StreamParser tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/jakegoncalves/Jarvis && git add main.py && git commit -m "feat: wire CC tool/status callbacks into _send and manage CC node on mode toggle"
```
