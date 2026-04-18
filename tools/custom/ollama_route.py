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
        "⭐ TOKEN-FREE: Run a task on the local Ollama llama3 model — uses ZERO Anthropic tokens. "
        "ALWAYS try this first before using swarm_dispatch or any Haiku agent. "
        "Best for: summarising text, categorising items, formatting/transforming data, "
        "drafting short text, simple factual Q&A, writing outlines, code snippets. "
        "Skip only when the task truly requires real-time data, complex multi-step tool chains, "
        "or advanced reasoning. Returns an error string if Ollama is not running."
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
