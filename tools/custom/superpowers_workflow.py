"""
Tool: superpowers_workflow
Description: Injects obra/superpowers structured development workflow into HUBERT.
Enforces brainstorm → plan → TDD → review → verify cycle for any engineering task.
"""

BRAINSTORM_PROMPT = """Before implementing, ask clarifying questions to refine scope.
Present the design in sections the user can read and approve.
Do not write code until the design is approved."""

PLAN_PROMPT = """Break the work into 2-5 minute tasks.
Each task must have: exact file paths, complete code (no placeholders), verification steps.
Do not proceed to implementation until the plan is approved."""

TDD_PROMPT = """RED-GREEN-REFACTOR:
1. Write a failing test first
2. Watch it fail
3. Write minimal code to make it pass
4. Watch it pass
5. Commit
Delete any code written before its test exists."""

DEBUG_PROMPT = """4-phase root cause analysis:
1. Reproduce reliably
2. Isolate the cause (don't guess)
3. Understand why it happens
4. Fix the root cause, not the symptom
Never declare fixed without evidence."""

TOOL_DEFINITION = {
    "name": "superpowers_workflow",
    "description": (
        "Inject a structured workflow protocol into the current task. "
        "Use before any engineering task to enforce: brainstorm → plan → TDD → review → verify. "
        "Specify the phase: brainstorm, plan, tdd, debug, review, or verify."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "phase": {
                "type": "string",
                "description": "Workflow phase to activate",
                "enum": ["brainstorm", "plan", "tdd", "debug", "review", "verify"],
            },
            "context": {
                "type": "string",
                "description": "Current task or problem description",
            },
        },
        "required": ["phase"],
    },
}


def run(params: dict) -> str:
    phase   = params["phase"]
    context = params.get("context", "")

    prompts = {
        "brainstorm": BRAINSTORM_PROMPT,
        "plan":       PLAN_PROMPT,
        "tdd":        TDD_PROMPT,
        "debug":      DEBUG_PROMPT,
        "review":     "Review against the plan. Report issues by severity. Critical issues block progress.",
        "verify":     "Provide evidence that the task is complete. Run tests. Show output. Do not declare done without proof.",
    }

    protocol = prompts.get(phase, "Unknown phase.")
    out = [f"[SUPERPOWERS: {phase.upper()}]", protocol]
    if context:
        out.append(f"\nContext: {context}")
    return "\n".join(out)


TOOLS = [(TOOL_DEFINITION, run)]
