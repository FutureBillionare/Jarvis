"""
Self-extension tools — Jarvis can write and load new capabilities for itself.
"""
import re
from pathlib import Path

CUSTOM_DIR = Path(__file__).parent / "custom"
CUSTOM_DIR.mkdir(exist_ok=True)


def _write_new_tool(p):
    """Let Jarvis create a new tool by writing Python code."""
    name = p["name"]
    description = p["description"]
    parameters_schema = p["parameters_schema"]
    code = p["code"]

    # Validate name
    if not re.match(r"^[a-z][a-z0-9_]{1,49}$", name):
        return "Error: tool name must be lowercase letters/numbers/underscores, 2-50 chars, start with letter."

    # Build the module content
    module_content = f'''"""
Auto-generated tool: {name}
Description: {description}
"""

TOOL_DEFINITION = {{
    "name": "{name}",
    "description": {repr(description)},
    "input_schema": {repr(parameters_schema)},
}}


def run(params: dict) -> str:
{_indent(code, 4)}


TOOLS = [(TOOL_DEFINITION, run)]
'''

    file_path = CUSTOM_DIR / f"{name}.py"

    # Test-compile the code before saving
    try:
        compile(module_content, f"<{name}>", "exec")
    except SyntaxError as e:
        return f"Syntax error in tool code: {e}"

    file_path.write_text(module_content, encoding="utf-8")

    # Dynamically load it now
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(f"tools.custom.{name}", file_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        from tools import register_tool
        for definition, handler in mod.TOOLS:
            register_tool(definition, handler)
        return f"New tool '{name}' created and loaded successfully! It is now available."
    except Exception as e:
        return f"Tool saved to {file_path} but failed to load: {e}"


def _indent(code: str, spaces: int) -> str:
    prefix = " " * spaces
    lines = code.split("\n")
    result = []
    for line in lines:
        if line.strip() == "":
            result.append("")
        else:
            result.append(prefix + line)
    return "\n".join(result)


def _list_tools(p):
    from tools import get_tool_definitions
    tools = get_tool_definitions()
    lines = [f"Available tools ({len(tools)} total):", ""]
    for t in sorted(tools, key=lambda x: x["name"]):
        lines.append(f"  • {t['name']}")
        lines.append(f"    {t['description'][:100]}")
    return "\n".join(lines)


def _delete_custom_tool(p):
    name = p["name"]
    file_path = CUSTOM_DIR / f"{name}.py"
    if not file_path.exists():
        return f"No custom tool named '{name}' found."
    file_path.unlink()
    # Remove from registry
    from tools import _tool_definitions, _tool_handlers
    _tool_definitions[:] = [t for t in _tool_definitions if t["name"] != name]
    _tool_handlers.pop(name, None)
    return f"Custom tool '{name}' deleted."


def _show_tool_code(p):
    name = p["name"]
    file_path = CUSTOM_DIR / f"{name}.py"
    if not file_path.exists():
        return f"No custom tool file for '{name}'."
    return file_path.read_text(encoding="utf-8")


TOOLS = [
    (
        {
            "name": "write_new_tool",
            "description": (
                "Create a new tool for yourself by writing Python code. "
                "The code must define the tool's logic. Use this to add new capabilities. "
                "The 'code' parameter is the body of a function that receives 'params: dict' and returns a string. "
                "Example: to add a weather tool, write code that calls a weather API."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Tool name (lowercase, underscores, e.g. 'get_weather')",
                    },
                    "description": {
                        "type": "string",
                        "description": "Clear description of what the tool does",
                    },
                    "parameters_schema": {
                        "type": "object",
                        "description": "JSON Schema object describing the tool's input parameters",
                    },
                    "code": {
                        "type": "string",
                        "description": (
                            "Python code for the function body. Receives 'params' dict. "
                            "Must return a string. Can import standard library and installed packages. "
                            "Example: 'import requests\\nresp = requests.get(params[\"url\"])\\nreturn resp.text[:1000]'"
                        ),
                    },
                },
                "required": ["name", "description", "parameters_schema", "code"],
            },
        },
        _write_new_tool,
    ),
    (
        {
            "name": "list_tools",
            "description": "List all tools currently available to Jarvis",
            "input_schema": {"type": "object", "properties": {}},
        },
        _list_tools,
    ),
    (
        {
            "name": "delete_custom_tool",
            "description": "Delete a custom tool that was previously created",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Tool name to delete"}},
                "required": ["name"],
            },
        },
        _delete_custom_tool,
    ),
    (
        {
            "name": "show_tool_code",
            "description": "Show the Python code of a custom tool",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
        _show_tool_code,
    ),
]
