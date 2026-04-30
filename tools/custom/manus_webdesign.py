"""
Tool: manus_webdesign
Description: Returns the Manus web design philosophy guide — production-first approach
             for building polished, full-stack web apps with real integrations.
"""

TOOL_DEFINITION = {
    "name": "manus_webdesign",
    "description": (
        "Get the Manus web design philosophy and checklist. Use when starting any "
        "web app feature, UI component, or full-stack task to ensure production-quality "
        "output: polished UI, real integrations, proper stack defaults, and design principles."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "description": (
                    "Optional: which section to retrieve. "
                    "Options: 'philosophy', 'stack', 'design', 'antipatterns', 'checklist', 'all'. "
                    "Defaults to 'all'."
                )
            }
        },
        "required": []
    }
}

SECTIONS = {
    "philosophy": """
## Core Philosophy — Manus Web Design

Think full-stack from day one. Before writing a single line, mentally wire up:
- What does the user SEE? (UI/UX)
- What does the app STORE? (data model)
- Who can ACCESS what? (auth/permissions)
- How does it SHIP? (deployment)

**Production-quality from the first prompt.** Every feature ships with real UI,
real data, real auth, and real integrations — not placeholders or stubs.
""",

    "stack": """
## Stack Defaults

| Layer     | Default                              |
|-----------|--------------------------------------|
| Frontend  | React + Tailwind CSS                 |
| Backend   | Node.js/Express or Next.js API routes|
| Database  | SQLite (local) / PostgreSQL (prod)   |
| Auth      | JWT or session-based                 |
| Deployment| Vercel / Railway / Fly.io ready      |

Adapt based on the user's existing stack.
""",

    "design": """
## Visual Design Principles

- No default blue buttons on white — use a real color palette
- No card-soup layouts — choose the right information architecture
- Typography matters — set font-size scale, line-height, letter-spacing intentionally
- Empty states are UI too — design what the app looks like with no data
- Error states are UI too — never let raw error messages hit the user
- Micro-interactions and transitions where appropriate
- Mobile-first responsive layout
- Accessible by default (semantic HTML, ARIA where needed)
""",

    "antipatterns": """
## What NOT to Do

| Anti-pattern             | Instead                                     |
|--------------------------|---------------------------------------------|
| TODO comments            | Implement it now or explain the trade-off   |
| Generic gray placeholders| Real content with realistic mock data       |
| Hardcoded auth bypass    | Real auth flow, even if simplified          |
| Console.log left in      | Clean production-ready code                 |
| One giant component file | Logical component breakdown                 |
| No loading/error states  | Handle all async states visibly             |
""",

    "checklist": """
## Quick Reference Checklist

Starting a new feature:
1. Define the user-visible outcome first
2. Design the data shape it requires
3. Wire the UI to real or realistically mocked data
4. Handle loading, error, and empty states
5. Make it responsive and accessible
6. Review: does it look designed, or generated?

Before calling it done:
- Does it handle the unhappy path?
- Is the visual design distinctive, not default?
- Would a real user understand this without explanation?
- Is the code something you would be comfortable handing off?
"""
}


def run(params: dict) -> str:
    section = params.get("section", "all").lower().strip()

    if section == "all":
        return "\n".join(SECTIONS.values())

    if section in SECTIONS:
        return SECTIONS[section]

    return (
        f"Unknown section '{section}'. "
        f"Available: {', '.join(SECTIONS.keys())}, all"
    )


TOOLS = [(TOOL_DEFINITION, run)]
