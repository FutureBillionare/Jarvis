"""
Tool: task_router
Description: Classify a task message into HUBERT tool groups using Ollama (zero Anthropic tokens).
Returns the active tool groups and estimated token savings.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

TOOL_DEFINITION = {
    "name": "task_router",
    "description": (
        "Classify a task into HUBERT tool groups using local Ollama — zero Anthropic tokens. "
        "Returns which groups would be activated and how many tools that involves. "
        "Useful for understanding routing decisions or pre-planning a complex task."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The task message to classify",
            },
        },
        "required": ["message"],
    },
}


def run(params: dict) -> str:
    from jarvis_core import _classify_task_groups_fast, _classify_task_groups_ollama, _select_model
    import tools as tool_registry

    message = params["message"]
    fast_groups  = _classify_task_groups_fast(message)
    ollama_groups = _classify_task_groups_ollama(message)
    model = _select_model(message)

    fast_tools   = tool_registry.get_tool_definitions_for_groups(fast_groups)
    ollama_tools = tool_registry.get_tool_definitions_for_groups(ollama_groups)
    total_tools  = len(tool_registry.get_tool_definitions())

    return (
        f"Keyword routing  : groups={fast_groups or ['core']}, tools={len(fast_tools)}/{total_tools}\n"
        f"Ollama routing   : groups={ollama_groups or ['core']}, tools={len(ollama_tools)}/{total_tools}\n"
        f"Model selected   : {model}\n"
        f"Token est savings: ~{(total_tools - len(ollama_tools)) * 80} tokens vs full tool list"
    )


TOOLS = [(TOOL_DEFINITION, run)]
