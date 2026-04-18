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


def _slugify(text: str) -> str:
    """Convert text to a lowercase hyphenated slug."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:50].strip("-")


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
        answered = "\n".join(f"Q: {q['q']}\nA: {q['a']}" for q in qa_pairs if q.get("a"))
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

    # ── Public entry point ─────────────────────────────────────────────────────

    def intercept(self, message: str):
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
            # Background Gemma check — run in thread to not block
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

    _PROCEED_PHRASES = ["proceed", "enough", "enough questions", "move on", "continue", "go ahead"]

    def _run_questioning(self, user_answer: str) -> str:
        qa = self._state["questions"]
        is_proceed = bool(user_answer) and any(p in user_answer.lower() for p in self._PROCEED_PHRASES)

        # Record the answer
        if user_answer and not is_proceed:
            if qa and not qa[-1].get("a"):
                # Fill the open slot on the last question
                qa[-1]["a"] = user_answer
            else:
                # No open slot — store answer now; question text will be filled below
                qa.append({"q": "", "a": user_answer})
            self._save()

        # Check if we should advance based on count or explicit proceed
        if is_proceed and len(qa) >= 1:
            return self._run_designing("")

        if len(qa) >= 5:
            return self._run_designing("")

        # Ask next question
        question_num = len(qa) + 1
        response = _ask_question(
            self._state["description"], qa, question_num
        )

        # If Claude decided it has enough, advance (answer already stored above)
        if "▸ DESIGN —" in response:
            return self._run_designing("")

        # Store the question text — fill in the slot we just created, or append a new one
        if qa and not qa[-1].get("q"):
            qa[-1]["q"] = response
        else:
            qa.append({"q": response, "a": ""})
        self._save()
        return response

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

        # Check if all sections generated and approved
        all_approved = sections and all(s.get("approved") for s in sections)
        all_generated = len(sections) >= len(_DESIGN_SECTIONS)

        if all_approved and all_generated:
            spec_path = self._write_spec()
            self._state["spec_path"] = spec_path
            self._set_phase("PLANNING")
            return self._run_planning("")

        # Find next section to present
        generated_names = [s["name"] for s in sections]
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

        # All generated but not all approved — re-prompt
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
            try:
                from memory_pipeline import run_canvas_refresh
                run_canvas_refresh()
            except Exception:
                pass
            return str(target)
        except Exception:
            return ""

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
