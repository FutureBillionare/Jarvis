"""
Tool: skill_activate
Description: Load and return the guidelines from any installed antigravity skill.
Injects expert-level domain knowledge into the current conversation context.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Path to the antigravity plugin skills
SKILL_ROOT = Path.home() / ".claude" / "plugins" / "cache" / "local-antigravity" / "antigravity" / "1.0.0" / "skills"

AVAILABLE_SKILLS = {
    "ai-engineer":           "Production LLM apps, RAG, agents, vector search, prompt caching",
    "python-patterns":       "Python framework selection, async patterns, type hints, project structure",
    "database-design":       "Schema design, indexing, ORM selection, Supabase, migrations",
    "async-python-patterns": "asyncio, httpx, concurrent scraping, FastAPI background tasks",
    "api-design-principles": "REST design, versioning, error formats, pagination, auth, OpenAPI",
    "agent-orchestration":   "Multi-agent coordination, token budgets, latency, swarm optimization",
    "startup-analyst":       "TAM/SAM/SOM, unit economics, financial modeling, go-to-market, pricing",
    "code-review-excellence":"Systematic code review: correctness, security, performance, maintainability",
    "easing-animations":     "CSS easing curves, animation timing, keyframes, scroll reveals, micro-interactions",
    "design-commands":       "20 typography/spacing commands: type scale, 4px grid, shadows, color tokens",
    "design-references":     "Named design aesthetics (Vercel, Linear, brutalist, editorial) to stop generic AI output",
}

TOOL_DEFINITION = {
    "name": "skill_activate",
    "description": (
        "Load expert domain guidelines from an installed antigravity skill into the current conversation. "
        "Use this to activate specialized knowledge before tackling a task in that domain. "
        "Available skills: ai-engineer, python-patterns, database-design, async-python-patterns, "
        "api-design-principles, agent-orchestration, startup-analyst, code-review-excellence, "
        "easing-animations, design-commands, design-references. "
        "Returns the full skill guidelines as context."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "description": (
                    "Skill name to activate. One of: "
                    "ai-engineer, python-patterns, database-design, async-python-patterns, "
                    "api-design-principles, agent-orchestration, startup-analyst, code-review-excellence, "
                    "easing-animations, design-commands, design-references"
                ),
            },
            "list": {
                "type": "boolean",
                "description": "If true, list all available skills instead of loading one",
            },
        },
        "required": [],
    },
}


def run(params: dict) -> str:
    if params.get("list"):
        lines = ["Available antigravity skills:\n"]
        for name, desc in AVAILABLE_SKILLS.items():
            lines.append(f"  {name:<28} — {desc}")
        return "\n".join(lines)

    skill_name = params.get("skill", "").strip().lower()
    if not skill_name:
        return "Provide a skill name or pass list=true to see available skills."

    # Fuzzy match
    if skill_name not in AVAILABLE_SKILLS:
        matches = [k for k in AVAILABLE_SKILLS if skill_name in k]
        if len(matches) == 1:
            skill_name = matches[0]
        elif len(matches) > 1:
            return f"Ambiguous skill name '{skill_name}'. Matches: {matches}"
        else:
            return (
                f"Skill '{skill_name}' not found. "
                f"Available: {list(AVAILABLE_SKILLS.keys())}"
            )

    skill_path = SKILL_ROOT / skill_name / "SKILL.md"
    if not skill_path.exists():
        return f"Skill file not found at {skill_path}"

    content = skill_path.read_text(encoding="utf-8")
    return f"[Skill activated: {skill_name}]\n\n{content}"


TOOLS = [(TOOL_DEFINITION, run)]
