"""
Tool: ui_control
Description: Control HUBERT's live UI in real time — add agents to the swarm
panel, log communications, register tools, or post events to the activity feed.
No restart needed; changes appear instantly via ui_bridge.
"""
import sys
from pathlib import Path

# Ensure Jarvis root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import ui_bridge
    _available = True
except ImportError:
    _available = False


TOOL_DEFINITION = {
    "name": "ui_control",
    "description": (
        "Send a live command to HUBERT's UI. "
        "Use to: show a new agent node (add_agent), animate a communication "
        "between two agents (add_comm), post a custom event to the activity "
        "feed (log), highlight a tool node (add_tool), or clear all tool nodes "
        "(clear_tools). Changes appear immediately without restart."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cmd": {
                "type": "string",
                "description": "Command to execute",
                "enum": ["add_agent", "add_comm", "log", "add_tool", "clear_tools"],
            },
            "name": {
                "type": "string",
                "description": "Agent or tool name (required for add_agent, add_tool)",
            },
            "from_agent": {
                "type": "string",
                "description": "Sender name for add_comm (default: HUBERT)",
            },
            "to_agent": {
                "type": "string",
                "description": "Receiver name for add_comm",
            },
            "msg": {
                "type": "string",
                "description": "Message text for add_comm or log",
            },
            "log_type": {
                "type": "string",
                "description": "Log entry style: tool | agent | comm | sys | err",
                "enum": ["tool", "agent", "comm", "sys", "err"],
            },
        },
        "required": ["cmd"],
    },
}


def run(params: dict) -> str:
    if not _available:
        return "ui_bridge not available — is the HUBERT UI running?"

    cmd = params["cmd"]

    if cmd == "add_agent":
        name = params.get("name", "unnamed_agent")
        ui_bridge.push("add_agent", name=name)
        return f"Agent '{name}' added to swarm panel."

    elif cmd == "add_comm":
        ui_bridge.push(
            "add_comm",
            **{
                "from": params.get("from_agent", "HUBERT"),
                "to":   params.get("to_agent",   "HUBERT"),
                "msg":  params.get("msg", ""),
            },
        )
        return "Communication logged in swarm panel."

    elif cmd == "log":
        ui_bridge.push(
            "log",
            type=params.get("log_type", "sys"),
            text=params.get("msg", ""),
        )
        return "Event logged in activity feed."

    elif cmd == "add_tool":
        name = params.get("name", "unnamed_tool")
        ui_bridge.push("add_tool", name=name)
        return f"Tool '{name}' shown in swarm panel."

    elif cmd == "clear_tools":
        ui_bridge.push("clear_tools")
        return "Tool nodes cleared from swarm panel."

    return f"Unknown command: {cmd}"


TOOLS = [(TOOL_DEFINITION, run)]
