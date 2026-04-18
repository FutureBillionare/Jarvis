"""
Tool: token_stats
Description: Report current session token usage against the budget.
Returns a summary of input tokens, output tokens, total used, budget, and percentage.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

TOOL_DEFINITION = {
    "name": "token_stats",
    "description": (
        "Report current session Anthropic token usage. "
        "Returns input tokens, output tokens, total used, budget (80,000), and percentage consumed. "
        "Use this to check how much of the token budget remains before launching expensive operations."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def run(params: dict) -> str:
    try:
        from jarvis_core import get_global_token_stats
        s = get_global_token_stats()
        return (
            f"Session tokens: {s['input']:,} in + {s['output']:,} out "
            f"= {s['total']:,} total  |  Budget: {s['budget']:,}  |  "
            f"Used: {s['pct']}%  |  Remaining: {s['remaining']:,}"
        )
    except Exception as e:
        return f"Could not read token stats: {e}"


TOOLS = [(TOOL_DEFINITION, run)]
