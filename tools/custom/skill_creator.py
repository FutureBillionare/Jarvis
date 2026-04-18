"""
Tool: skill_creator
Description: Meta-skill — guided creation of new HUBERT skills with templates,
validation, and auto-loading. More user-friendly than write_new_tool.
"""
import re, json
from pathlib import Path

CUSTOM_DIR = Path(__file__).parent
TEMPLATES = {
    "api":      "requests + JSON — calls a REST API endpoint",
    "cli":      "subprocess — wraps a command-line tool",
    "file":     "pathlib — reads/writes local files",
    "browser":  "playwright — automates a website",
    "data":     "pandas/json — processes data",
    "notify":   "sends a notification or message",
    "blank":    "empty template — write from scratch",
}

def run_list_templates(params):
    lines = ["Available skill templates:\n"]
    for name, desc in TEMPLATES.items():
        lines.append(f"  {name:<12} — {desc}")
    return "\n".join(lines)


def run_create_skill(params):
    name        = params["name"].strip().lower().replace(" ", "_")
    description = params["description"]
    template    = params.get("template", "blank")
    parameters  = params.get("parameters", {})

    if not re.match(r"^[a-z][a-z0-9_]{1,49}$", name):
        return "Error: name must be lowercase letters/numbers/underscores."

    dest = CUSTOM_DIR / f"{name}.py"
    if dest.exists():
        return f"Skill '{name}' already exists at {dest}. Use show_tool_code to view it."

    param_props = json.dumps(parameters.get("properties", {}), indent=8)
    param_req   = json.dumps(parameters.get("required", []))

    if template == "api":
        body = (
            "    import requests, os\n"
            "    url = params['url']\n"
            "    headers = {'Authorization': f'Bearer {os.environ.get(\"API_KEY\",\"\")}'}\n"
            "    resp = requests.get(url, headers=headers, timeout=10)\n"
            "    return resp.text[:2000]"
        )
    elif template == "cli":
        body = (
            "    import subprocess\n"
            "    cmd = params['command']\n"
            "    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)\n"
            "    return result.stdout or result.stderr"
        )
    elif template == "file":
        body = (
            "    from pathlib import Path\n"
            "    path = Path(params['path'])\n"
            "    if params.get('write'):\n"
            "        path.write_text(params['content'])\n"
            "        return f'Written to {path}'\n"
            "    return path.read_text()"
        )
    elif template == "browser":
        body = (
            "    from playwright.sync_api import sync_playwright\n"
            "    url = params['url']\n"
            "    with sync_playwright() as p:\n"
            "        b = p.chromium.launch(headless=True)\n"
            "        page = b.new_page()\n"
            "        page.goto(url)\n"
            "        text = page.inner_text('body')[:3000]\n"
            "        b.close()\n"
            "    return text"
        )
    else:
        body = "    # TODO: implement this skill\n    return 'Not yet implemented'"

    code = f'''"""
Skill: {name}
Description: {description}
"""

TOOL_DEFINITION = {{
    "name": "{name}",
    "description": {repr(description)},
    "input_schema": {{
        "type": "object",
        "properties": {param_props},
        "required": {param_req}
    }}
}}


def run(params: dict) -> str:
{body}


TOOLS = [(TOOL_DEFINITION, run)]
'''

    try:
        compile(code, name, "exec")
    except SyntaxError as e:
        return f"Template generated invalid syntax: {e}"

    dest.write_text(code, encoding="utf-8")

    # Trigger hot-reload
    try:
        import tools as tr
        names = tr.load_single_custom_file(dest)
        loaded = ", ".join(names) if names else "none"
    except Exception as e:
        loaded = f"(load error: {e})"

    return (
        f"Skill '{name}' created at {dest}\n"
        f"Loaded tools: {loaded}\n"
        f"Edit the file to implement the logic, then save — HUBERT will auto-reload it."
    )


def run_scaffold_from_description(params):
    """Use an AI-style heuristic to pick the best template."""
    desc = params["description"].lower()
    name = params["name"]
    if any(w in desc for w in ["api", "http", "rest", "fetch", "request"]):
        template = "api"
    elif any(w in desc for w in ["browser", "website", "scrape", "click", "navigate"]):
        template = "browser"
    elif any(w in desc for w in ["file", "read", "write", "folder", "directory"]):
        template = "file"
    elif any(w in desc for w in ["command", "cli", "terminal", "run", "exec"]):
        template = "cli"
    else:
        template = "blank"
    return run_create_skill({**params, "template": template})


TOOLS = [
    ({"name": "skill_list_templates",
      "description": "List available skill creation templates (api, cli, file, browser, data, blank).",
      "input_schema": {"type": "object", "properties": {}}}, run_list_templates),

    ({"name": "skill_create",
      "description": "Create a new HUBERT skill from a template. Saves and hot-loads it immediately.",
      "input_schema": {"type": "object", "properties": {
          "name":        {"type": "string", "description": "Snake_case skill name"},
          "description": {"type": "string", "description": "What the skill does"},
          "template":    {"type": "string", "description": "api | cli | file | browser | data | blank"},
          "parameters":  {"type": "object", "description": "JSON Schema properties and required arrays"},
      }, "required": ["name", "description"]}}, run_create_skill),

    ({"name": "skill_scaffold",
      "description": "Auto-picks the best template based on description and creates the skill.",
      "input_schema": {"type": "object", "properties": {
          "name":        {"type": "string"},
          "description": {"type": "string"},
          "parameters":  {"type": "object"},
      }, "required": ["name", "description"]}}, run_scaffold_from_description),
]
