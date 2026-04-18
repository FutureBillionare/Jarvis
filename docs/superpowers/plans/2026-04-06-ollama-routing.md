# Ollama Local Subagent Routing + Rate Limit Retry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route swarm sub-agent tasks through a local llama3 model first (with self-assessment escalation), and add graceful 429 retry with UI status messages instead of a hard error.

**Architecture:** A new `ollama_core.py` module wraps the Ollama REST API and provides `assess_task()` + `run_task()`. Both swarm tools import it and attempt Ollama before falling back to Haiku. `jarvis_core.py` gains an `on_status` callback and retry loop for 429. `main.py` wires `on_status` to a new `_status()` handler that shows a grey info line in the chat.

**Tech Stack:** `requests` (stdlib-adjacent, already in env), Ollama REST API at `localhost:11434`, `anthropic` SDK (existing), `customtkinter` / tkinter (existing UI).

> **Note:** This project has no git repository. Skip all `git add` / `git commit` steps.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `ollama_core.py` | Create | Ollama availability check, task self-assessment, task execution |
| `tools/custom/ollama_route.py` | Create | HUBERT tool for direct Ollama access (CLAUDE.md requirement) |
| `tools/custom/swarm_dispatch.py` | Modify lines 66–88, 91–100 | Route each task through Ollama assessor before Haiku |
| `tools/custom/swarm_bridge.py` | Modify lines 60–108 | Same routing; skip Ollama if `tier="smart"` |
| `jarvis_core.py` | Modify lines 204–213, 245, 305–310 | Add `on_status` param + 429 retry with backoff |
| `main.py` | Modify lines 2350–2357, add `_status()` handler | Wire `on_status` to grey info message in chat |
| `tests/test_ollama_core.py` | Create | Unit tests for `OllamaCore` (mocked HTTP) |

---

## Task 1: Create `ollama_core.py`

**Files:**
- Create: `C:\Users\Jake\Jarvis\ollama_core.py`
- Create (test): `C:\Users\Jake\Jarvis\tests\test_ollama_core.py`

- [ ] **Step 1: Create the tests directory and write failing tests**

Create `C:\Users\Jake\Jarvis\tests\__init__.py` (empty file), then create `C:\Users\Jake\Jarvis\tests\test_ollama_core.py`:

```python
"""Tests for ollama_core.OllamaCore."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch, MagicMock
import pytest


def _make_response(text: str, status=200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = {
        "message": {"content": text}
    }
    m.raise_for_status = MagicMock()
    return m


class TestOllamaAvailable:
    def test_returns_true_when_server_responds(self):
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200)
            from ollama_core import OllamaCore
            core = OllamaCore()
            assert core.ollama_available() is True

    def test_returns_false_on_connection_error(self):
        with patch("requests.get", side_effect=Exception("refused")):
            from ollama_core import OllamaCore
            core = OllamaCore()
            assert core.ollama_available() is False


class TestAssessTask:
    def test_returns_true_for_yes_response(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value = _make_response("YES, this is straightforward")
            from ollama_core import OllamaCore
            core = OllamaCore()
            assert core.assess_task("Summarise this paragraph") is True

    def test_returns_false_for_no_response(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value = _make_response("NO, needs real-time data")
            from ollama_core import OllamaCore
            core = OllamaCore()
            assert core.assess_task("What is today's stock price?") is False

    def test_returns_false_on_error(self):
        with patch("requests.post", side_effect=Exception("timeout")):
            from ollama_core import OllamaCore
            core = OllamaCore()
            assert core.assess_task("anything") is False


class TestRunTask:
    def test_returns_response_text(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value = _make_response("Paris is the capital of France.")
            from ollama_core import OllamaCore
            core = OllamaCore()
            result = core.run_task("Be concise.", "What is the capital of France?")
            assert result == "Paris is the capital of France."

    def test_raises_on_connection_error(self):
        with patch("requests.post", side_effect=ConnectionError("no server")):
            from ollama_core import OllamaCore
            core = OllamaCore()
            with pytest.raises(ConnectionError):
                core.run_task("sys", "task")
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd C:\Users\Jake\Jarvis
python -m pytest tests/test_ollama_core.py -v
```

Expected: `ModuleNotFoundError: No module named 'ollama_core'` or similar — all tests fail.

- [ ] **Step 3: Write `ollama_core.py`**

Create `C:\Users\Jake\Jarvis\ollama_core.py`:

```python
"""
OllamaCore — wraps the Ollama REST API for local llama3 inference.

Used by swarm tools to attempt tasks locally before falling back to
Claude Haiku. Never used in HUBERT's main conversation path.
"""
import requests

OLLAMA_BASE  = "http://localhost:11434"
OLLAMA_MODEL = "llama3"

_ASSESS_SYSTEM = (
    "You are a capability assessor. Answer ONLY \"YES\" or \"NO\". "
    "No explanation, no punctuation beyond the word itself."
)

_ASSESS_TEMPLATE = (
    "Can a small open-source LLM (7B parameters, no internet access, no tools) "
    "complete the following task accurately?\n\n"
    "Task: {task}\n\n"
    "Answer YES only if the task requires only text reasoning, summarisation, "
    "categorisation, formatting, or simple factual recall within common knowledge. "
    "Answer NO if it requires real-time data, complex multi-step code generation, "
    "multi-step tool calls, or advanced reasoning."
)


class OllamaCore:
    def __init__(self, base_url: str = OLLAMA_BASE, model: str = OLLAMA_MODEL):
        self.base_url = base_url
        self.model    = model

    def ollama_available(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            requests.get(self.base_url, timeout=1)
            return True
        except Exception:
            return False

    def assess_task(self, task: str) -> bool:
        """
        Ask llama3 whether it can handle this task.
        Returns True (attempt locally) or False (escalate to Haiku).
        Returns False on any error — fail safe.
        """
        try:
            prompt = _ASSESS_TEMPLATE.format(task=task)
            resp   = self._chat(_ASSESS_SYSTEM, prompt, max_tokens=5)
            first_word = resp.strip().split()[0].upper().rstrip(".,!?")
            return first_word == "YES"
        except Exception:
            return False

    def run_task(self, system: str, task: str, max_tokens: int = 400) -> str:
        """
        Run a task on llama3 and return the response text.
        Raises ConnectionError if the server is unreachable.
        Raises RuntimeError on unexpected API errors.
        """
        return self._chat(system, task, max_tokens)

    def _chat(self, system: str, user: str, max_tokens: int) -> str:
        url  = f"{self.base_url}/api/chat"
        body = {
            "model":  self.model,
            "stream": False,
            "options": {"num_predict": max_tokens},
            "messages": [
                {"role": "system",  "content": system},
                {"role": "user",    "content": user},
            ],
        }
        try:
            resp = requests.post(url, json=body, timeout=30)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Ollama server unreachable: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Ollama API error: {e}") from e
```

- [ ] **Step 4: Run tests to confirm they pass**

```
cd C:\Users\Jake\Jarvis
python -m pytest tests/test_ollama_core.py -v
```

Expected output:
```
tests/test_ollama_core.py::TestOllamaAvailable::test_returns_true_when_server_responds PASSED
tests/test_ollama_core.py::TestOllamaAvailable::test_returns_false_on_connection_error PASSED
tests/test_ollama_core.py::TestAssessTask::test_returns_true_for_yes_response PASSED
tests/test_ollama_core.py::TestAssessTask::test_returns_false_for_no_response PASSED
tests/test_ollama_core.py::TestAssessTask::test_returns_false_on_error PASSED
tests/test_ollama_core.py::TestRunTask::test_returns_response_text PASSED
tests/test_ollama_core.py::TestRunTask::test_raises_on_connection_error PASSED

7 passed in ...
```

---

## Task 2: Create `tools/custom/ollama_route.py`

**Files:**
- Create: `C:\Users\Jake\Jarvis\tools\custom\ollama_route.py`

Required by CLAUDE.md: every new capability needs a HUBERT tool file.

- [ ] **Step 1: Write the tool file**

Create `C:\Users\Jake\Jarvis\tools\custom\ollama_route.py`:

```python
"""
Tool: ollama_route
Description: Run a task directly on the local Ollama llama3 model. Use for
lightweight text reasoning, summarisation, categorisation, or formatting tasks
where speed matters more than quality. Returns an error string if Ollama is not running.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

TOOL_DEFINITION = {
    "name": "ollama_route",
    "description": (
        "Run a task directly on the local Ollama llama3 model. "
        "Use for lightweight text reasoning, summarisation, categorisation, "
        "or formatting where speed matters more than quality. "
        "Does NOT use Anthropic tokens. Returns an error if Ollama is not running."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task or question to send to llama3",
            },
            "system": {
                "type": "string",
                "description": "Optional system prompt (default: concise task worker)",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Max tokens in response (default: 400)",
            },
        },
        "required": ["task"],
    },
}


def run(params: dict) -> str:
    from ollama_core import OllamaCore
    core = OllamaCore()
    if not core.ollama_available():
        return "Error: Ollama is not running. Start it with: ollama serve"
    task       = params["task"]
    system     = params.get("system", "Be concise and direct. Answer only what is asked.")
    max_tokens = params.get("max_tokens", 400)
    try:
        return core.run_task(system, task, max_tokens)
    except Exception as e:
        return f"Ollama error: {e}"


TOOLS = [(TOOL_DEFINITION, run)]
```

- [ ] **Step 2: Verify hot-reload picks it up**

In the running HUBERT app, check the tool appears, OR run:

```
cd C:\Users\Jake\Jarvis
python -c "import tools; tools.reload_all(); print([t['name'] for t in tools.get_tool_definitions()])"
```

Expected: `'ollama_route'` appears in the printed list.

---

## Task 3: Add Ollama routing to `tools/custom/swarm_dispatch.py`

**Files:**
- Modify: `C:\Users\Jake\Jarvis\tools\custom\swarm_dispatch.py`

The existing `_agent_worker` function at lines 67–88 always calls Haiku. We add Ollama routing before the Haiku call.

- [ ] **Step 1: Add the import at the top of the file**

After line 10 (`sys.path.insert(...)`), add:

```python
try:
    from ollama_core import OllamaCore as _OllamaCore
    _ollama = _OllamaCore()
except Exception:
    _ollama = None
```

The `try/except` means the file still loads if `ollama_core.py` is missing.

- [ ] **Step 2: Replace `_agent_worker` with the routed version**

Replace the entire `_agent_worker` function (lines 67–88) with:

```python
def _agent_worker(idx: int, task: str, model: str, max_tokens: int,
                  system: str, api_key: str, result_q: queue.Queue):
    text = None

    # ── Try Ollama first ──────────────────────────────────────────────────────
    if _ollama is not None and _ollama.ollama_available():
        if _ollama.assess_task(task):
            try:
                text = _ollama.run_task(system, task, max_tokens)
            except Exception:
                text = None   # fall through to Haiku

    # ── Haiku fallback ────────────────────────────────────────────────────────
    if text is None:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": task}],
            )
            text = resp.content[0].text.strip() if resp.content else "(no response)"
        except Exception as e:
            result_q.put((idx, task, None, str(e)))
            return

    result_q.put((idx, task, text, None))
    try:
        import ui_bridge
        ui_bridge.push("add_comm",
                       **{"from": f"agent-{idx+1:02d}", "to": "HUBERT",
                          "msg": text[:60]})
    except Exception:
        pass
```

- [ ] **Step 3: Smoke-test the import**

```
cd C:\Users\Jake\Jarvis
python -c "from tools.custom.swarm_dispatch import run; print('OK')"
```

Expected: `OK` (no import errors).

---

## Task 4: Add Ollama routing to `tools/custom/swarm_bridge.py`

**Files:**
- Modify: `C:\Users\Jake\Jarvis\tools\custom\swarm_bridge.py`

Same pattern as Task 3, but `tier="smart"` bypasses Ollama entirely.

- [ ] **Step 1: Add the import at the top of the file**

After line 9 (`sys.path.insert(...)`), add:

```python
try:
    from ollama_core import OllamaCore as _OllamaCore
    _ollama = _OllamaCore()
except Exception:
    _ollama = None
```

- [ ] **Step 2: Replace `_run_agent` with the routed version**

Replace the entire `_run_agent` nested function inside `run()` (lines 86–108) with:

```python
    def _run_agent(idx: int, task: str):
        text = None

        # ── Try Ollama first (skip if tier="smart") ───────────────────────────
        if tier_key != "smart" and _ollama is not None and _ollama.ollama_available():
            if _ollama.assess_task(task):
                try:
                    text = _ollama.run_task(system, task, max_tokens)
                except Exception:
                    text = None   # fall through to Claude

        # ── Claude fallback ───────────────────────────────────────────────────
        if text is None:
            try:
                client = anthropic.Anthropic(api_key=api_key)
                resp   = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": task}],
                )
                text = resp.content[0].text.strip() if resp.content else "(no response)"
                with lock:
                    results[idx] = text
            except Exception as e:
                with lock:
                    errors[idx] = str(e)
                return
        else:
            with lock:
                results[idx] = text

        try:
            import ui_bridge
            ui_bridge.push("add_comm",
                           **{"from": f"sub-{idx+1}", "to": "HUBERT",
                              "msg": text[:60]})
        except Exception:
            pass
```

Also capture `tier_key` before the thread loop so the closure can read it. Find this line in `run()`:

```python
    model      = MODELS.get(params.get("tier", "fast"), MODELS["fast"])
```

Add immediately after it:

```python
    tier_key   = params.get("tier", "fast")
```

- [ ] **Step 3: Smoke-test the import**

```
cd C:\Users\Jake\Jarvis
python -c "from tools.custom.swarm_bridge import run; print('OK')"
```

Expected: `OK`

---

## Task 5: Add `on_status` callback + 429 retry to `jarvis_core.py`

**Files:**
- Modify: `C:\Users\Jake\Jarvis\jarvis_core.py`

Three changes: (a) add `import time` at the top, (b) add `on_status` to `chat()` signature and pass it through, (c) replace the `APIStatusError` handler with a retry loop.

- [ ] **Step 1: Add `import time`**

In `jarvis_core.py`, the imports are on lines 1–13. Add `import time` to the existing imports block:

```python
import threading
import concurrent.futures
import traceback
import datetime
import time
from pathlib import Path
```

- [ ] **Step 2: Add `on_status` to `chat()` signature**

`chat()` is defined at line 204. Its current signature is:

```python
    def chat(
        self,
        user_message: str,
        image_path: str = None,
        on_text: Callable[[str], None] = None,
        on_tool_start: Callable[[str, dict], None] = None,
        on_tool_result: Callable[[str, str], None] = None,
        on_done: Callable[[], None] = None,
        on_error: Callable[[str], None] = None,
    ):
```

Replace with:

```python
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
    ):
```

- [ ] **Step 3: Pass `on_status` through to `_run_agent_loop`**

The call to `_run_agent_loop` is at line 240:

```python
        try:
            self._run_agent_loop(on_text, on_tool_start, on_tool_result, on_done, on_error)
```

Replace with:

```python
        try:
            self._run_agent_loop(on_text, on_tool_start, on_tool_result, on_done, on_error, on_status)
```

- [ ] **Step 4: Update `_run_agent_loop` signature**

At line 245:

```python
    def _run_agent_loop(self, on_text, on_tool_start, on_tool_result, on_done, on_error):
```

Replace with:

```python
    def _run_agent_loop(self, on_text, on_tool_start, on_tool_result, on_done, on_error, on_status=None):
```

- [ ] **Step 5: Replace the `APIStatusError` handler with a retry loop**

The current handler is at lines 305–310:

```python
            except anthropic.APIStatusError as e:
                msg = f"API error {e.status_code}: {e.message}"
                _log_error(f"APIStatusError (iteration {iteration})", e)
                if on_error:
                    on_error(msg)
                return
```

Replace with:

```python
            except anthropic.APIStatusError as e:
                if e.status_code == 429:
                    _RETRY_DELAYS = [5, 15, 30]
                    if not hasattr(self, "_retry_attempt"):
                        self._retry_attempt = 0
                    if self._retry_attempt < len(_RETRY_DELAYS):
                        delay = _RETRY_DELAYS[self._retry_attempt]
                        self._retry_attempt += 1
                        status_msg = (
                            f"⏳ Rate limit reached — retrying in {delay}s "
                            f"(attempt {self._retry_attempt}/3)…"
                        )
                        _log_error(f"429 rate limit (retry {self._retry_attempt})", e)
                        if on_status:
                            on_status(status_msg)
                        time.sleep(delay)
                        continue   # retry the current iteration
                    else:
                        # All retries exhausted
                        del self._retry_attempt
                        _log_error(f"APIStatusError 429 exhausted (iteration {iteration})", e)
                        if on_error:
                            on_error("Rate limit reached after 3 retries. Please wait a moment and try again.")
                        return
                else:
                    msg = f"API error {e.status_code}: {e.message}"
                    _log_error(f"APIStatusError (iteration {iteration})", e)
                    if on_error:
                        on_error(msg)
                    return
```

Also add a reset of `_retry_attempt` when the stream succeeds. After the `with self.client.messages.stream(...) as stream:` block closes successfully (after `stop_reason = final_msg.stop_reason`), reset the counter:

```python
                    final_msg   = stream.get_final_message()
                    stop_reason = final_msg.stop_reason
                    content_blocks = final_msg.content
                    # Reset retry counter on any successful response
                    if hasattr(self, "_retry_attempt"):
                        del self._retry_attempt
```

- [ ] **Step 6: Verify `chat_in_thread` still works**

`chat_in_thread` at line 394 uses `**callbacks`. Because `on_status` is just a new kwarg on `chat()`, it passes through automatically. No change needed.

- [ ] **Step 7: Smoke-test import**

```
cd C:\Users\Jake\Jarvis
python -c "from jarvis_core import JarvisCore; print('OK')"
```

Expected: `OK`

---

## Task 6: Wire `on_status` to the UI in `main.py`

**Files:**
- Modify: `C:\Users\Jake\Jarvis\main.py`

Two changes: add a `_status()` handler method, and pass `on_status` to `chat_in_thread`.

- [ ] **Step 1: Add `_status()` handler method**

The `_error()` method is at line 2387:

```python
    def _error(self, err):
        self.chat.end_hubert()
        self.chat.error(err)
        self._set_status("error")
        self.input_bar.set_enabled(True)
```

Add `_status()` immediately before `_error()`:

```python
    def _status(self, msg: str):
        """Show a non-fatal status message (e.g. retry notice) in the chat."""
        self.chat.add_status(msg)

    def _error(self, err):
```

- [ ] **Step 2: Add `add_status()` to `ChatDisplay`**

Find the `ChatDisplay` class. It has `add_user()`, `error()`, and similar methods. Add `add_status()` after `error()`:

```python
    def add_status(self, msg: str):
        """Append a grey italic status line (e.g. rate-limit retry notice)."""
        lbl = ctk.CTkLabel(
            self._inner,
            text=msg,
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color="#888888",
            anchor="w",
            wraplength=500,
        )
        lbl.pack(anchor="w", padx=12, pady=(0, 4))
        self._scroll()
```

To find the right location, search for `def error(self` in `main.py` — add `add_status` directly after that method.

- [ ] **Step 3: Pass `on_status` to `chat_in_thread`**

The `chat_in_thread` call is at line 2350:

```python
        chat_in_thread(
            self.core, text,
            on_text        = lambda c: self._q_put(self.chat.stream, c),
            on_tool_start  = lambda n, p: self._q_put(self._tool_start, n, p),
            on_tool_result = lambda n, r: self._q_put(self._tool_result, n, r),
            on_done        = lambda: self._q_put(self._done),
            on_error       = lambda e: self._q_put(self._error, e),
        )
```

Replace with:

```python
        chat_in_thread(
            self.core, text,
            on_text        = lambda c: self._q_put(self.chat.stream, c),
            on_tool_start  = lambda n, p: self._q_put(self._tool_start, n, p),
            on_tool_result = lambda n, r: self._q_put(self._tool_result, n, r),
            on_done        = lambda: self._q_put(self._done),
            on_error       = lambda e: self._q_put(self._error, e),
            on_status      = lambda s: self._q_put(self._status, s),
        )
```

- [ ] **Step 4: Launch HUBERT and verify the UI starts correctly**

```
cd C:\Users\Jake\Jarvis
python main.py
```

Expected: HUBERT boots normally, no errors in the terminal. The chat window opens.

- [ ] **Step 5: Verify `add_status` renders correctly (manual)**

In the Python REPL or by temporarily adding a debug trigger, call:

```python
app._status("⏳ Rate limit reached — retrying in 5s (attempt 1/3)…")
```

Expected: a grey italic line appears in the chat area.

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|------------------|------|
| `OllamaCore` with `ollama_available`, `assess_task`, `run_task` | Task 1 |
| `assess_task` YES/NO prompt | Task 1, Step 3 |
| Connection guard (1s timeout) | Task 1, Step 3 (`ollama_available`) |
| `ollama_route` HUBERT tool | Task 2 |
| Swarm dispatch routing through Ollama | Task 3 |
| Swarm bridge routing through Ollama | Task 4 |
| `tier="smart"` bypasses Ollama | Task 4 |
| `on_status` callback on `jarvis_core.chat()` | Task 5 |
| 429 retry: 3 attempts at 5s/15s/30s | Task 5 |
| Status message during retry (non-fatal, grey) | Tasks 5 + 6 |
| `on_status` wired in `main.py` | Task 6 |

All spec requirements are covered. ✓
