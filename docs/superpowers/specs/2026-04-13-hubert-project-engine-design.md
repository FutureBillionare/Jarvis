# HUBERT Project Engine — Design Spec
*2026-04-13*

## Goal

Give HUBERT a stateful project workflow that mirrors the brainstorm → design → plan → implement cycle used in Claude Code. HUBERT detects project requests automatically, asks clarifying questions one at a time, proposes a design, writes a spec, writes a plan, then implements or escalates — all from within his chat UI.

---

## State Machine

Five phases, persisted to `~/Jarvis/.project_state.json`:

```
IDLE → QUESTIONING → DESIGNING → PLANNING → IMPLEMENTING → IDLE
```

### Transitions

| From | To | Condition |
|------|----|-----------|
| IDLE | QUESTIONING | Auto-detect fires OR manual trigger |
| QUESTIONING | DESIGNING | HUBERT has ≥3 answers OR user says "enough" / "proceed" |
| DESIGNING | PLANNING | User approves design ("yes", "looks good", "proceed", "perfect") |
| PLANNING | IMPLEMENTING | User approves plan |
| IMPLEMENTING | IDLE | Implementation complete or escalated |
| Any | IDLE | User says "cancel", "stop", "exit project mode" |

### State File Schema (`~/Jarvis/.project_state.json`)

```json
{
  "phase": "QUESTIONING",
  "project_name": "stripe-integration",
  "description": "Add Stripe payments to the website builder",
  "questions": [
    {"q": "What payment flows do you need?", "a": "one-time and subscriptions"},
    {"q": "Do you have a Stripe account already?", "a": "yes, test mode keys"}
  ],
  "design_sections": [],
  "design_approved": false,
  "plan_path": null,
  "spec_path": null,
  "started": "2026-04-13T14:22:00",
  "updated": "2026-04-13T14:25:00"
}
```

State is written after every phase transition and every answered question. If HUBERT restarts mid-project, it reloads and continues from the saved phase.

---

## Auto-Detection

Runs on every incoming message before normal chat dispatch.

### Step 1: Fast keyword check (zero tokens, instant)

Trigger words: `build`, `add`, `create`, `implement`, `make`, `i want`, `can you add`, `feature`, `system`, `integrate`, `set up`, `wire up`, `connect`

If none match → skip, normal chat.

### Step 2: Gemma 4 confirmation (~0.5s, zero Anthropic tokens)

Single yes/no prompt:
```
Is this message a project or feature request that needs design and planning before implementation? Answer only: yes or no.

Message: "{user_message}"
```

If `yes` → enter QUESTIONING with the user's message as the project description seed.
If `no` → normal chat.

### Manual Trigger

Any message matching: `"project mode:"`, `"build mode"`, `"design mode"`, or `"/project"` bypasses detection and enters QUESTIONING immediately. The text after the trigger keyword becomes the project description seed.

---

## Visual Indicators (Light)

- Status bar label changes: `DESIGNING` / `PLANNING` / `BUILDING` (instead of `THINKING`)
- Response prefix on project-phase messages only:
  - Questions: `▸ Q{n} —`
  - Design sections: `▸ DESIGN —`
  - Plan output: `▸ PLAN —`
  - Implementation: `▸ BUILDING —`
- No modals, badges, or separate UI panels — feels like a focused conversation

---

## Per-Phase Behavior

### QUESTIONING

- Max 5 questions, one per message
- Uses Claude Sonnet with a brainstorming-style system prompt
- Focuses on: purpose → constraints → success criteria → tech context → scope
- Stores each Q&A pair in state
- After 3+ answers, HUBERT can decide he has enough and move to DESIGNING
- User can also say "proceed" / "enough questions" to advance

**Question system prompt:**
```
You are in PROJECT MODE — QUESTIONING phase.
You are gathering requirements for: {description}
Questions answered so far: {qa_pairs}

Ask exactly ONE clarifying question to better understand the project.
Focus on: purpose, constraints, success criteria, or technical context.
Prefix your question with "▸ Q{n} —"
Do not implement anything. Do not propose solutions yet.
After this question, you will have {remaining} questions left.
If you have enough information already, say "▸ DESIGN — I have enough context. Let me propose a design." and stop asking.
```

### DESIGNING

- Uses Claude Sonnet (not Gemma — quality matters here)
- Presents design in 2-3 sections, one per message, asks approval after each
- Sections: Architecture → Components → Data Flow (scaled to project complexity)
- On full approval: writes spec to vault

**Design system prompt:**
```
You are in PROJECT MODE — DESIGNING phase.
Project: {description}
Requirements gathered: {qa_pairs}
Design section to present: {section_name} ({section_num} of {total})

Present this design section clearly and concisely.
Prefix with "▸ DESIGN —"
End with: "Does this look right?"
Do not write code. Do not implement yet.
```

**Spec output** — `~/HUBERT_Vault/Memory/Projects/{project-name}.md`:
```yaml
---
id: "{date}-{project-name}"
type: project
created: {date}
modified: {date}
status: active
tags: [project, hubert]
author: hubert
project_status: planning
project_owner: "[[Jake]]"
person_refs: ["[[Jake]]"]
---
```

### PLANNING

- Breaks work into numbered tasks with: exact file paths, commands, verification steps
- Writes plan to `~/Jarvis/docs/projects/{date}-{project-name}-plan.md`
- Presents summary in chat, asks for approval

**Plan system prompt:**
```
You are in PROJECT MODE — PLANNING phase.
Project: {description}
Approved design: {design_sections}

Write a concise implementation plan. Number each task.
Each task must have: file paths, what to do, how to verify it worked.
Prefix with "▸ PLAN —"
Keep tasks bite-sized (2-5 minutes each). Max 8 tasks.
End with: "Does this plan look right?"
```

### IMPLEMENTING

**Complexity check** (HUBERT decides based on task count and file count in plan):
- Simple (≤3 tasks, ≤3 files) → HUBERT implements directly using file write + shell tools, commits
- Complex (>3 tasks or >3 files) → escalate to Claude Code

**Escalation output** — HUBERT posts in chat:
```
▸ BUILDING — This project is ready for Claude Code.
Spec: ~/HUBERT_Vault/Memory/Projects/{name}.md
Plan: ~/Jarvis/docs/projects/{date}-{name}-plan.md
Say "escalate" to hand this off, or I'll start on the simple parts now.
```

**`escalate` command** — available at any phase. HUBERT immediately packages current state and posts the spec + plan paths.

---

## New Files

| File | Purpose |
|------|---------|
| `~/Jarvis/project_engine.py` | State machine, detection, phase runners |
| `~/Jarvis/.project_state.json` | Persisted project state (auto-created) |
| `~/Jarvis/docs/projects/` | Implementation plans |
| `~/HUBERT_Vault/Memory/Projects/` | Specs (already exists) |

## Modified Files

| File | Change |
|------|--------|
| `main.py` | `_send()` checks `project_engine.intercept()` before normal dispatch |
| `main.py` | Status bar updates for project phases |

---

## Spec Self-Review

- **Placeholder scan:** No TBDs. All prompts written out fully. File paths explicit.
- **Consistency:** State file schema matches all phase references. `project_name` used consistently as slug (lowercase, hyphenated).
- **Scope:** Single module (`project_engine.py`) + one hook in `_send()`. Appropriately bounded.
- **Ambiguity:** "Complexity check" — defined as ≤3 tasks AND ≤3 files for simple. Explicit.
