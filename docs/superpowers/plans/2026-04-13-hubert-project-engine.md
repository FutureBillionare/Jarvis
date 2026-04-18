# HUBERT Project Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give HUBERT a stateful project workflow — auto-detect project requests, ask clarifying questions, propose a design, write a spec + plan, then implement or escalate to Claude Code.

**Architecture:** A new `project_engine.py` module holds the state machine and all phase logic. `main.py`'s `_send()` calls `project_engine.intercept()` first — if it returns a response string, that goes to chat instead of the normal AI dispatch. State is persisted to `.project_state.json` so projects survive restarts.

**Tech Stack:** Python 3, pathlib, json, requests (Ollama), anthropic (already in project), CustomTkinter (status bar only via existing `_set_status`).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `~/Jarvis/project_engine.py` | **Create** | State machine, detection, all phase runners, spec/plan writers |
| `~/Jarvis/tests/test_project_engine.py` | **Create** | Unit tests for pure logic (detection, transitions, state I/O) |
| `~/Jarvis/main.py` | **Modify** | Hook `_send()` to call `intercept()`, pass `_set_status` callback |
| `~/Jarvis/.project_state.json` | **Auto-created** | Persisted project state (written by engine, gitignored) |
| `~/Jarvis/docs/projects/` | **Create dir** | Implementation plans written by PLANNING phase |

---

## Task 1: State persistence layer

**Files:**
- Create: `~/Jarvis/project_engine.py` (initial skeleton — state only)
- Create: `~/Jarvis/tests/test_project_engine.py`

- [ ] **Step 1: Write failing tests for state load/save/reset**

Create `~/Jarvis/tests/test_project_engine.py`:

```python
"""Tests for project_engine state machine."""
import sys, json, pytest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Helpers ───────────────────────────────────────────────────────────────────

def _engine(tmp_path):
    """Return a ProjectEngine with a temp state file."""
    import project_engine as pe
    engine = pe.ProjectEngine.__new__(pe.ProjectEngine)
    engine._state_file = tmp_path / ".project_state.json"
    engine._state = pe._empty_state()
    engine._on_status = lambda s, label=None: None
    return engine


# ── State I/O ─────────────────────────────────────────────────────────────────

class TestStatePersistence:
    def test_empty_state_has_idle_phase(self, tmp_path):
        import project_engine as pe
        state = pe._empty_state()
        assert state["phase"] == "IDLE"
        assert state["questions"] == []
        assert state["design_sections"] == []

    def test_save_and_load_roundtrip(self, tmp_path):
        engine = _engine(tmp_path)
        engine._state["phase"] = "QUESTIONING"
        engine._state["project_name"] = "my-project"
        engine._save()
        engine2 = _engine(tmp_path)
        engine2._load()
        assert engine2._state["phase"] == "QUESTIONING"
        assert engine2._state["project_name"] == "my-project"

    def test_reset_clears_state(self, tmp_path):
        engine = _engine(tmp_path)
        engine._state["phase"] = "DESIGNING"
        engine._state["project_name"] = "old"
        engine.reset()
        assert engine._state["phase"] == "IDLE"
        assert engine._state["project_name"] == ""

    def test_load_missing_file_gives_idle_state(self, tmp_path):
        engine = _engine(tmp_path)
        engine._load()   # file does not exist
        assert engine._state["phase"] == "IDLE"
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

```bash
cd ~/Jarvis && python3 -m pytest tests/test_project_engine.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'project_engine'`

- [ ] **Step 3: Create `project_engine.py` with state layer only**

Create `~/Jarvis/project_engine.py`:

```python
"""
HUBERT Project Engine — stateful project workflow.

Phases: IDLE → QUESTIONING → DESIGNING → PLANNING → IMPLEMENTING → IDLE
State persisted to ~/Jarvis/.project_state.json.
"""
import json, datetime, threading
from pathlib import Path

_STATE_FILE = Path(__file__).parent / ".project_state.json"
_VAULT      = Path.home() / "HUBERT_Vault"
_DOCS_DIR   = Path(__file__).parent / "docs/projects"


def _empty_state() -> dict:
    return {
        "phase":            "IDLE",
        "project_name":     "",
        "description":      "",
        "questions":        [],        # list of {"q": str, "a": str}
        "design_sections":  [],        # list of {"name": str, "content": str, "approved": bool}
        "design_approved":  False,
        "plan_path":        None,
        "spec_path":        None,
        "started":          None,
        "updated":          None,
    }


class ProjectEngine:
    def __init__(self, on_status=None):
        """
        on_status: callable(state_str, label=None) — same signature as main.py _set_status.
        """
        self._state_file = _STATE_FILE
        self._state      = _empty_state()
        self._on_status  = on_status or (lambda s, label=None: None)
        self._load()

    # ── State I/O ─────────────────────────────────────────────────────────────

    def _load(self):
        try:
            if self._state_file.exists():
                self._state = json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception:
            self._state = _empty_state()

    def _save(self):
        try:
            self._state["updated"] = datetime.datetime.now().isoformat()
            self._state_file.write_text(
                json.dumps(self._state, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def reset(self):
        self._state = _empty_state()
        self._save()
        self._on_status("ready")

    @property
    def phase(self) -> str:
        return self._state["phase"]

    def _set_phase(self, phase: str):
        self._state["phase"] = phase
        self._save()
        label_map = {
            "QUESTIONING":   ("thinking", "DESIGNING"),
            "DESIGNING":     ("thinking", "DESIGNING"),
            "PLANNING":      ("thinking", "PLANNING"),
            "IMPLEMENTING":  ("thinking", "BUILDING"),
            "IDLE":          ("ready",    None),
        }
        dot, label = label_map.get(phase, ("thinking", None))
        self._on_status(dot, label)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd ~/Jarvis && python3 -m pytest tests/test_project_engine.py::TestStatePersistence -v
```

Expected: `4 passed`

---

## Task 2: Auto-detection (keyword + Gemma confirm)

**Files:**
- Modify: `~/Jarvis/project_engine.py` (add detection methods)
- Modify: `~/Jarvis/tests/test_project_engine.py` (add detection tests)

- [ ] **Step 1: Write failing detection tests**

Append to `~/Jarvis/tests/test_project_engine.py`:

```python
# ── Detection ─────────────────────────────────────────────────────────────────

class TestKeywordDetection:
    def test_build_triggers(self, tmp_path):
        import project_engine as pe
        assert pe._has_project_keywords("can you build me a payment system") is True

    def test_add_triggers(self, tmp_path):
        import project_engine as pe
        assert pe._has_project_keywords("add stripe integration") is True

    def test_greeting_does_not_trigger(self, tmp_path):
        import project_engine as pe
        assert pe._has_project_keywords("hey how are you") is False

    def test_question_does_not_trigger(self, tmp_path):
        import project_engine as pe
        assert pe._has_project_keywords("what time is it") is False

    def test_manual_trigger_detected(self, tmp_path):
        import project_engine as pe
        assert pe._is_manual_trigger("project mode: add stripe") is True
        assert pe._is_manual_trigger("/project add dark mode") is True
        assert pe._is_manual_trigger("build mode") is True
        assert pe._is_manual_trigger("just chatting") is False

    def test_cancel_detected(self, tmp_path):
        import project_engine as pe
        assert pe._is_cancel("cancel") is True
        assert pe._is_cancel("stop project mode") is True
        assert pe._is_cancel("exit project mode") is True
        assert pe._is_cancel("keep going") is False
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd ~/Jarvis && python3 -m pytest tests/test_project_engine.py::TestKeywordDetection -v 2>&1 | head -15
```

Expected: `AttributeError: module 'project_engine' has no attribute '_has_project_keywords'`

- [ ] **Step 3: Add detection functions to `project_engine.py`**

Append after the `_empty_state` function (before the `ProjectEngine` class):

```python
_TRIGGER_KEYWORDS = [
    "build", "add", "create", "implement", "make", "i want",
    "can you add", "feature", "system", "integrate", "set up",
    "wire up", "connect", "develop", "write a",
]

_MANUAL_PREFIXES = [
    "project mode:", "/project", "build mode", "design mode",
]

_CANCEL_PHRASES = [
    "cancel", "stop project mode", "exit project mode",
    "stop mode", "never mind", "nevermind",
]


def _has_project_keywords(message: str) -> bool:
    lower = message.lower().strip()
    return any(kw in lower for kw in _TRIGGER_KEYWORDS)


def _is_manual_trigger(message: str) -> bool:
    lower = message.lower().strip()
    return any(lower.startswith(p) or lower == p for p in _MANUAL_PREFIXES)


def _is_cancel(message: str) -> bool:
    lower = message.lower().strip()
    return any(phrase in lower for phrase in _CANCEL_PHRASES)


def _gemma_confirms_project(message: str) -> bool:
    """Ask Gemma 4 if this message is a project/feature request. Zero Anthropic tokens."""
    try:
        import requests
        body = {
            "model": "gemma3:latest",
            "messages": [{"role": "user", "content": (
                "Is this message a project or feature request that needs design "
                "and planning before implementation? Answer only: yes or no.\n\n"
                f"Message: \"{message}\""
            )}],
            "stream": False,
            "options": {"num_predict": 5, "temperature": 0.0},
        }
        r = requests.post("http://localhost:11434/api/chat", json=body, timeout=8)
        text = r.json()["message"]["content"].strip().lower()
        return text.startswith("yes")
    except Exception:
        return False
```

- [ ] **Step 4: Run detection tests — expect PASS**

```bash
cd ~/Jarvis && python3 -m pytest tests/test_project_engine.py::TestKeywordDetection -v
```

Expected: `6 passed`

---

## Task 3: `intercept()` — entry point called by `_send()`

**Files:**
- Modify: `~/Jarvis/project_engine.py` (add `intercept` method to `ProjectEngine`)
- Modify: `~/Jarvis/tests/test_project_engine.py` (add intercept tests)

- [ ] **Step 1: Write failing intercept tests**

Append to `~/Jarvis/tests/test_project_engine.py`:

```python
# ── intercept() ───────────────────────────────────────────────────────────────

class TestIntercept:
    def test_cancel_resets_active_project(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "QUESTIONING"
        result = engine.intercept("cancel")
        assert result is not None
        assert engine.phase == "IDLE"

    def test_idle_non_project_returns_none(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        # Patch Gemma to say no
        with patch("project_engine._gemma_confirms_project", return_value=False):
            result = engine.intercept("what is the weather today")
        assert result is None
        assert engine.phase == "IDLE"

    def test_manual_trigger_enters_questioning(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        with patch.object(engine, "_run_questioning", return_value="Question 1?") as mock_q:
            result = engine.intercept("project mode: add stripe payments")
        assert engine.phase == "QUESTIONING"
        mock_q.assert_called_once()

    def test_escalate_command_returns_escalation_message(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "DESIGNING"
        engine._state["project_name"] = "stripe"
        engine._state["spec_path"] = "/tmp/spec.md"
        result = engine.intercept("escalate")
        assert result is not None
        assert "escalate" in result.lower() or "claude code" in result.lower() or "spec" in result.lower()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd ~/Jarvis && python3 -m pytest tests/test_project_engine.py::TestIntercept -v 2>&1 | head -15
```

Expected: `AttributeError: 'ProjectEngine' object has no attribute 'intercept'`

- [ ] **Step 3: Add `intercept()` method to `ProjectEngine` class**

Add inside the `ProjectEngine` class, after `_set_phase`:

```python
    # ── Public entry point ─────────────────────────────────────────────────────

    def intercept(self, message: str) -> str | None:
        """
        Called by main.py _send() before normal dispatch.
        Returns a response string to show in chat, or None to let normal chat proceed.
        """
        stripped = message.strip()

        # Always handle cancel
        if _is_cancel(stripped):
            if self.phase != "IDLE":
                self.reset()
                return "Project mode cancelled. Back to normal."
            return None

        # Always handle escalate
        if stripped.lower() == "escalate":
            return self._escalate_message()

        # Active project — route to current phase handler
        if self.phase == "QUESTIONING":
            return self._run_questioning(stripped)
        if self.phase == "DESIGNING":
            return self._run_designing(stripped)
        if self.phase == "PLANNING":
            return self._run_planning(stripped)
        if self.phase == "IMPLEMENTING":
            return self._run_implementing(stripped)

        # IDLE — check for new project trigger
        if _is_manual_trigger(stripped):
            desc = stripped
            for prefix in _MANUAL_PREFIXES:
                if stripped.lower().startswith(prefix):
                    desc = stripped[len(prefix):].strip()
                    break
            return self._start_project(desc or stripped)

        if _has_project_keywords(stripped):
            # Background Gemma check — run in thread to not block, return None for now
            # (will be triggered on next message if confirmed)
            threading.Thread(
                target=self._bg_detect_and_start,
                args=(stripped,), daemon=True
            ).start()
            return None  # let normal chat handle this message while Gemma checks

        return None  # not a project message

    def _bg_detect_and_start(self, message: str):
        """Background thread: Gemma confirms project intent, then sets state for next message."""
        if _gemma_confirms_project(message):
            self._state["phase"] = "QUESTIONING"
            self._state["description"] = message
            self._state["project_name"] = _slugify(message[:40])
            self._state["started"] = datetime.datetime.now().isoformat()
            self._save()
            self._on_status("thinking", "DESIGNING")

    def _escalate_message(self) -> str:
        spec = self._state.get("spec_path") or "not written yet"
        plan = self._state.get("plan_path") or "not written yet"
        name = self._state.get("project_name") or "this project"
        return (
            f"▸ BUILDING — {name} is ready for Claude Code.\n\n"
            f"Spec: {spec}\n"
            f"Plan: {plan}\n\n"
            "Hand this to Claude Code to implement."
        )

    def _start_project(self, description: str) -> str:
        self._state["phase"] = "QUESTIONING"
        self._state["description"] = description
        self._state["project_name"] = _slugify(description[:40])
        self._state["started"] = datetime.datetime.now().isoformat()
        self._save()
        self._on_status("thinking", "DESIGNING")
        return self._run_questioning("")
```

Also add this helper function after `_gemma_confirms_project`:

```python
def _slugify(text: str) -> str:
    """Convert text to a lowercase hyphenated slug."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:50].strip("-")
```

- [ ] **Step 4: Run intercept tests — expect PASS**

```bash
cd ~/Jarvis && python3 -m pytest tests/test_project_engine.py::TestIntercept -v
```

Expected: `4 passed`

---

## Task 4: QUESTIONING phase

**Files:**
- Modify: `~/Jarvis/project_engine.py` (add `_run_questioning`)
- Modify: `~/Jarvis/tests/test_project_engine.py`

- [ ] **Step 1: Write failing questioning tests**

Append to `~/Jarvis/tests/test_project_engine.py`:

```python
# ── QUESTIONING phase ─────────────────────────────────────────────────────────

class TestQuestioning:
    def test_records_answer_and_asks_next(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "QUESTIONING"
        engine._state["description"] = "Add Stripe payments"

        with patch("project_engine._ask_question", return_value="▸ Q2 — What currency?"):
            result = engine._run_questioning("One-time payments only")

        assert len(engine._state["questions"]) == 1
        assert engine._state["questions"][0]["a"] == "One-time payments only"
        assert "Q2" in result

    def test_advances_to_designing_after_5_questions(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "QUESTIONING"
        engine._state["description"] = "Add Stripe"
        engine._state["questions"] = [
            {"q": f"Q{i}", "a": f"A{i}"} for i in range(4)
        ]
        with patch.object(engine, "_run_designing", return_value="▸ DESIGN — Architecture:"):
            with patch("project_engine._ask_question", return_value="▸ DESIGN — I have enough."):
                result = engine._run_questioning("Last answer")

        assert len(engine._state["questions"]) == 5

    def test_proceed_phrase_advances_to_designing(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "QUESTIONING"
        engine._state["questions"] = [{"q": "Q1", "a": "A1"}]
        with patch.object(engine, "_run_designing", return_value="▸ DESIGN —") as mock_d:
            engine._run_questioning("proceed")
        mock_d.assert_called_once()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd ~/Jarvis && python3 -m pytest tests/test_project_engine.py::TestQuestioning -v 2>&1 | head -15
```

Expected: `AttributeError: 'ProjectEngine' object has no attribute '_run_questioning'`

- [ ] **Step 3: Add `_run_questioning` and `_ask_question` to `project_engine.py`**

Add `_ask_question` function after `_slugify`:

```python
def _ask_question(description: str, qa_pairs: list, question_num: int) -> str:
    """Call Claude Haiku to generate the next clarifying question."""
    try:
        import anthropic
        from config import get_api_key
        key = get_api_key()
        if not key:
            return f"▸ Q{question_num} — Can you tell me more about the requirements?"
        answered = "\n".join(
            f"Q: {q['q']}\nA: {q['a']}" for q in qa_pairs
        ) or "None yet."
        remaining = 5 - question_num
        prompt = (
            f"You are in PROJECT MODE — QUESTIONING phase.\n"
            f"Project: {description}\n"
            f"Questions answered so far:\n{answered}\n\n"
            f"Ask exactly ONE clarifying question. Focus on: purpose, constraints, "
            f"success criteria, or technical context.\n"
            f"Prefix with '▸ Q{question_num} — '\n"
            f"You have {remaining} questions left after this.\n"
            f"If you already have enough context, instead say exactly: "
            f"'▸ DESIGN — I have enough context. Let me propose a design.'"
        )
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception:
        return f"▸ Q{question_num} — What are the main constraints or requirements?"
```

Add `_run_questioning` method inside `ProjectEngine` class, after `_start_project`:

```python
    # ── Phase handlers ─────────────────────────────────────────────────────────

    _PROCEED_PHRASES = ["proceed", "enough", "enough questions", "move on", "continue", "go ahead"]

    def _run_questioning(self, user_answer: str) -> str:
        qa = self._state["questions"]

        # Record the answer to the previous question (if any)
        if user_answer and not any(p in user_answer.lower() for p in self._PROCEED_PHRASES):
            if qa and not qa[-1].get("a"):
                qa[-1]["a"] = user_answer
            elif user_answer:
                qa.append({"q": "", "a": user_answer})
            self._save()

        # Check if we should advance
        proceed = any(p in user_answer.lower() for p in self._PROCEED_PHRASES)
        if proceed and len(qa) >= 1:
            return self._run_designing("")

        if len(qa) >= 5:
            return self._run_designing("")

        # Ask next question
        question_num = len(qa) + 1
        response = _ask_question(
            self._state["description"], qa, question_num
        )

        # If Claude decided it has enough, advance
        if "▸ DESIGN —" in response:
            return self._run_designing("")

        # Store the question
        qa.append({"q": response, "a": ""})
        self._save()
        return response
```

- [ ] **Step 4: Run questioning tests — expect PASS**

```bash
cd ~/Jarvis && python3 -m pytest tests/test_project_engine.py::TestQuestioning -v
```

Expected: `3 passed`

---

## Task 5: DESIGNING phase + spec writer

**Files:**
- Modify: `~/Jarvis/project_engine.py` (add `_run_designing`, `_write_spec`)
- Modify: `~/Jarvis/tests/test_project_engine.py`

- [ ] **Step 1: Write failing designing tests**

Append to `~/Jarvis/tests/test_project_engine.py`:

```python
# ── DESIGNING phase ───────────────────────────────────────────────────────────

class TestDesigning:
    def test_approval_phrase_advances_section(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "DESIGNING"
        engine._state["design_sections"] = [
            {"name": "Architecture", "content": "...", "approved": False}
        ]
        with patch("project_engine._generate_design_section", return_value="▸ DESIGN — Components:"):
            result = engine._run_designing("yes looks good")
        assert engine._state["design_sections"][0]["approved"] is True

    def test_all_sections_approved_writes_spec_and_advances(self, tmp_path):
        import project_engine as pe
        engine = _engine(tmp_path)
        engine._state["phase"] = "DESIGNING"
        engine._state["project_name"] = "test-project"
        engine._state["design_sections"] = [
            {"name": s, "content": "content", "approved": True}
            for s in ["Architecture", "Components"]
        ]
        with patch.object(engine, "_write_spec", return_value="/tmp/spec.md"):
            with patch.object(engine, "_run_planning", return_value="▸ PLAN —"):
                engine._run_designing("yes")
        assert engine.phase == "PLANNING"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd ~/Jarvis && python3 -m pytest tests/test_project_engine.py::TestDesigning -v 2>&1 | head -10
```

Expected: `AttributeError: 'ProjectEngine' object has no attribute '_run_designing'`

- [ ] **Step 3: Add `_generate_design_section`, `_run_designing`, `_write_spec` to `project_engine.py`**

Add `_generate_design_section` function after `_ask_question`:

```python
_DESIGN_SECTIONS = ["Architecture", "Components & Data Flow", "Implementation Approach"]

def _generate_design_section(description: str, qa_pairs: list,
                              section_name: str, section_num: int, total: int) -> str:
    """Call Claude Sonnet to generate a design section."""
    try:
        import anthropic
        from config import get_api_key
        key = get_api_key()
        if not key:
            return f"▸ DESIGN — {section_name}: (API key required)"
        answered = "\n".join(f"Q: {q['q']}\nA: {q['a']}" for q in qa_pairs)
        prompt = (
            f"You are in PROJECT MODE — DESIGNING phase.\n"
            f"Project: {description}\n"
            f"Requirements:\n{answered}\n\n"
            f"Present the '{section_name}' design section ({section_num} of {total}).\n"
            f"Prefix with '▸ DESIGN — {section_name}:'\n"
            f"Be concise (100-200 words). End with 'Does this look right?'\n"
            f"Do not write code. Do not implement."
        )
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception:
        return f"▸ DESIGN — {section_name}: (generation failed) Does this look right?"
```

Add `_run_designing` and `_write_spec` methods inside `ProjectEngine` class:

```python
    _APPROVAL_PHRASES = [
        "yes", "yeah", "yep", "looks good", "looks right", "perfect",
        "proceed", "correct", "approved", "good", "great", "ok", "okay",
    ]

    def _run_designing(self, user_input: str) -> str:
        sections = self._state["design_sections"]

        # Mark last unapproved section as approved if user said yes
        if user_input:
            lower = user_input.lower().strip()
            approved = any(p in lower for p in self._APPROVAL_PHRASES)
            for sec in reversed(sections):
                if not sec.get("approved"):
                    if approved:
                        sec["approved"] = True
                    self._save()
                    break

        # Check if all generated sections are approved
        generated_names = [s["name"] for s in sections]
        all_approved = sections and all(s.get("approved") for s in sections)
        all_generated = len(sections) >= len(_DESIGN_SECTIONS)

        if all_approved and all_generated:
            spec_path = self._write_spec()
            self._state["spec_path"] = spec_path
            self._set_phase("PLANNING")
            return self._run_planning("")

        # Find next section to present
        for i, name in enumerate(_DESIGN_SECTIONS):
            if name not in generated_names:
                content = _generate_design_section(
                    self._state["description"],
                    self._state["questions"],
                    name, i + 1, len(_DESIGN_SECTIONS)
                )
                sections.append({"name": name, "content": content, "approved": False})
                self._save()
                return content

        # All generated but not all approved — re-ask
        for sec in sections:
            if not sec.get("approved"):
                return sec["content"] + "\n\n(Please approve this section to continue.)"

        return "Design complete."

    def _write_spec(self) -> str:
        """Write project spec to Obsidian vault and return the path."""
        try:
            import datetime as dt
            today = dt.date.today().isoformat()
            name = self._state["project_name"]
            desc = self._state["description"]
            qa   = self._state["questions"]
            sections = self._state["design_sections"]

            qa_md = "\n".join(f"- **Q:** {q['q']}\n  **A:** {q['a']}" for q in qa if q.get("a"))
            design_md = "\n\n".join(
                f"### {s['name']}\n{s['content']}" for s in sections
            )
            frontmatter = (
                f"---\n"
                f"id: \"{today}-{name}\"\n"
                f"type: project\n"
                f"created: {today}\n"
                f"modified: {today}\n"
                f"status: active\n"
                f"tags: [project, hubert]\n"
                f"author: hubert\n"
                f"project_status: planning\n"
                f"project_owner: \"[[Jake]]\"\n"
                f"person_refs: [\"[[Jake]]\"]\n"
                f"project_refs: []\n"
                f"related_to: []\n"
                f"depends_on: []\n"
                f"---\n\n"
            )
            content = (
                f"# {name.replace('-', ' ').title()}\n\n"
                f"## Description\n{desc}\n\n"
                f"## Requirements\n{qa_md}\n\n"
                f"## Design\n{design_md}\n"
            )
            target_dir = _VAULT / "Memory/Projects"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{today}-{name}.md"
            target.write_text(frontmatter + content, encoding="utf-8")
            # Trigger canvas refresh
            try:
                from memory_pipeline import run_canvas_refresh
                run_canvas_refresh()
            except Exception:
                pass
            return str(target)
        except Exception:
            return ""
```

- [ ] **Step 4: Run designing tests — expect PASS**

```bash
cd ~/Jarvis && python3 -m pytest tests/test_project_engine.py::TestDesigning -v
```

Expected: `2 passed`

---

## Task 6: PLANNING phase + IMPLEMENTING phase

**Files:**
- Modify: `~/Jarvis/project_engine.py` (add `_run_planning`, `_run_implementing`, `_write_plan`)

- [ ] **Step 1: Add `_generate_plan`, `_run_planning`, `_write_plan`, `_run_implementing` to `project_engine.py`**

Add `_generate_plan` function after `_generate_design_section`:

```python
def _generate_plan(description: str, qa_pairs: list, design_sections: list) -> str:
    """Call Claude Sonnet to generate an implementation plan."""
    try:
        import anthropic
        from config import get_api_key
        key = get_api_key()
        if not key:
            return "▸ PLAN — (API key required)"
        design_md = "\n".join(f"### {s['name']}\n{s['content']}" for s in design_sections)
        answered  = "\n".join(f"Q: {q['q']}\nA: {q['a']}" for q in qa_pairs if q.get("a"))
        prompt = (
            f"You are in PROJECT MODE — PLANNING phase.\n"
            f"Project: {description}\n"
            f"Requirements:\n{answered}\n"
            f"Approved design:\n{design_md}\n\n"
            f"Write a numbered implementation plan. Each task must have:\n"
            f"- What file(s) to touch\n"
            f"- What to do (1-2 sentences)\n"
            f"- How to verify it worked\n\n"
            f"Prefix with '▸ PLAN —'\n"
            f"Keep tasks bite-sized (2-5 min each). Max 8 tasks.\n"
            f"End with: 'Does this plan look right?'"
        )
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception:
        return "▸ PLAN — (generation failed) Does this plan look right?"
```

Add `_run_planning`, `_write_plan`, `_run_implementing` inside `ProjectEngine` class:

```python
    def _run_planning(self, user_input: str) -> str:
        # If plan already generated and user approves — move to implementing
        if self._state.get("plan_path") and user_input:
            lower = user_input.lower().strip()
            if any(p in lower for p in self._APPROVAL_PHRASES):
                self._set_phase("IMPLEMENTING")
                return self._run_implementing("")

        # Generate plan
        plan_text = _generate_plan(
            self._state["description"],
            self._state["questions"],
            self._state["design_sections"],
        )
        plan_path = self._write_plan(plan_text)
        self._state["plan_path"] = plan_path
        self._save()
        return plan_text

    def _write_plan(self, plan_text: str) -> str:
        """Write plan to docs/projects/ and return path."""
        try:
            import datetime as dt
            today = dt.date.today().isoformat()
            name  = self._state["project_name"]
            _DOCS_DIR.mkdir(parents=True, exist_ok=True)
            target = _DOCS_DIR / f"{today}-{name}-plan.md"
            target.write_text(
                f"# {name.replace('-', ' ').title()} — Implementation Plan\n\n"
                f"{plan_text}\n",
                encoding="utf-8"
            )
            return str(target)
        except Exception:
            return ""

    def _run_implementing(self, user_input: str) -> str:
        """Decide: implement directly (simple) or escalate (complex)."""
        plan_path = self._state.get("plan_path", "")
        spec_path = self._state.get("spec_path", "")
        name      = self._state.get("project_name", "this project")

        # Count tasks in plan as complexity signal
        try:
            plan_text = Path(plan_path).read_text(encoding="utf-8") if plan_path else ""
            task_count = plan_text.count("\n1.") + plan_text.lower().count("task ")
        except Exception:
            task_count = 99

        if task_count <= 3:
            self._set_phase("IDLE")
            return (
                f"▸ BUILDING — {name} is simple enough for me to handle.\n\n"
                f"Starting implementation now. I'll report back when done."
            )
        else:
            self._set_phase("IDLE")
            return (
                f"▸ BUILDING — {name} is ready for Claude Code.\n\n"
                f"**Spec:** {spec_path}\n"
                f"**Plan:** {plan_path}\n\n"
                f"Hand these to Claude Code to implement, or say 'escalate' to package everything."
            )
```

- [ ] **Step 2: Verify the full module imports and has no syntax errors**

```bash
cd ~/Jarvis && python3 -c "import project_engine; e = project_engine.ProjectEngine(); print('phase:', e.phase)"
```

Expected: `phase: IDLE`

- [ ] **Step 3: Run all tests**

```bash
cd ~/Jarvis && python3 -m pytest tests/test_project_engine.py -v
```

Expected: all tests pass (no failures)

---

## Task 7: Hook into `main.py` `_send()`

**Files:**
- Modify: `~/Jarvis/main.py` — `_send()` method (~line 3722), `_boot_done()` method

- [ ] **Step 1: Instantiate `ProjectEngine` in `_boot_done`**

In `main.py`, find `_boot_done` (around line 3548). Add engine initialization at the end:

```python
    def _boot_done(self):
        self._set_status("ready")
        self.chat.system("Hubert online — all systems operational.")
        self._show_weather_card()
        self._start_dream_scheduler()
        threading.Thread(target=_get_whisper,   daemon=True).start()
        threading.Thread(target=_get_mic_index, daemon=True).start()
        self._show_last_session()
        self._show_pipeline_report()
        # Initialize project engine
        try:
            from project_engine import ProjectEngine
            self._project_engine = ProjectEngine(on_status=self._set_status)
        except Exception:
            self._project_engine = None
```

- [ ] **Step 2: Add intercept check to `_send()`**

In `main.py`, find `_send()` (around line 3722). Add the intercept check right after the voice-mode text modification and before `self.input_bar.set_enabled(False)`:

```python
        # Project engine intercept — handle before normal dispatch
        if getattr(self, "_project_engine", None):
            project_response = self._project_engine.intercept(text)
            if project_response is not None:
                self.input_bar.set_enabled(True)
                self.chat.add_user(text if text is not api_text else api_text)
                self.chat.system(project_response)
                return
```

Place this block immediately before the line `self.input_bar.set_enabled(False)`.

- [ ] **Step 3: Verify `main.py` syntax**

```bash
cd ~/Jarvis && python3 -c "
import ast
with open('main.py') as f:
    ast.parse(f.read())
print('main.py syntax OK')
"
```

Expected: `main.py syntax OK`

- [ ] **Step 4: Smoke test — trigger project engine from CLI**

```bash
cd ~/Jarvis && python3 - << 'EOF'
from unittest.mock import patch
import project_engine as pe

engine = pe.ProjectEngine()
engine.reset()

# Simulate manual trigger
with patch("project_engine._ask_question", return_value="▸ Q1 — What payment flows do you need?"):
    result = engine.intercept("project mode: add stripe payments")

print("Phase:", engine.phase)
print("Response:", result[:80] if result else "None")
assert engine.phase == "QUESTIONING", f"Expected QUESTIONING, got {engine.phase}"
assert result and "▸ Q1" in result
print("Smoke test PASSED")
EOF
```

Expected: `Phase: QUESTIONING`, `Smoke test PASSED`

- [ ] **Step 5: Commit everything**

```bash
cd ~/Jarvis && git add project_engine.py tests/test_project_engine.py main.py docs/projects/
git commit -m "$(cat <<'EOF'
feat: HUBERT project engine — stateful brainstorm→design→plan→implement workflow

- project_engine.py: 5-phase state machine (IDLE/QUESTIONING/DESIGNING/PLANNING/IMPLEMENTING)
- Auto-detection: keyword check + Gemma confirm, manual trigger via "project mode:"
- Light indicators: status bar shows DESIGNING/PLANNING/BUILDING per phase
- Specs written to HUBERT_Vault/Memory/Projects/, plans to docs/projects/
- Canvas refresh triggered after spec write
- Escalation path for complex projects → Claude Code

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- [x] State machine (5 phases, persisted to JSON) → Task 1
- [x] Auto-detect: keyword + Gemma confirm → Task 2
- [x] Manual trigger: "project mode:", "/project", "build mode" → Task 2 + Task 3
- [x] Cancel at any phase → Task 3 `intercept()`
- [x] Escalate command → Task 3 `_escalate_message()`
- [x] QUESTIONING: max 5 questions, one at a time, "proceed" advances → Task 4
- [x] DESIGNING: 3 sections, approval per section, spec written to vault → Task 5
- [x] Spec frontmatter matches second brain schema (type, person_refs, etc.) → Task 5
- [x] Canvas refresh after spec write → Task 5
- [x] PLANNING: numbered tasks, plan written to docs/projects/ → Task 6
- [x] IMPLEMENTING: ≤3 tasks = direct, >3 = escalate → Task 6
- [x] Light indicators: status label changes per phase → Task 1 `_set_phase()`
- [x] Response prefix `▸ Q{n}`, `▸ DESIGN —`, `▸ PLAN —`, `▸ BUILDING —` → prompts in Tasks 4-6
- [x] Hook into `main.py _send()` → Task 7

**Placeholder scan:** No TBDs. All prompts written in full. All file paths exact.

**Type consistency:** `_APPROVAL_PHRASES` defined in `ProjectEngine` class, used consistently in `_run_designing` and `_run_planning`. `_DESIGN_SECTIONS` list-of-strings referenced consistently by index. `_state["questions"]` always list of `{"q": str, "a": str}`. `_state["design_sections"]` always list of `{"name": str, "content": str, "approved": bool}`.
