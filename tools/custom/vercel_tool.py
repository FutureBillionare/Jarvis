"""
Tool: vercel_tool
Description: Interact with Vercel — list deployments, trigger deploys, manage projects and env vars.
Requires: VERCEL_TOKEN environment variable.
"""
import os, json, subprocess
import requests


def _headers():
    token = os.environ.get("VERCEL_TOKEN", "")
    if not token:
        raise RuntimeError("Set the VERCEL_TOKEN environment variable.")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


BASE = "https://api.vercel.com"


def run_list_projects(params):
    resp = requests.get(f"{BASE}/v9/projects", headers=_headers(), timeout=10)
    resp.raise_for_status()
    projects = resp.json().get("projects", [])
    if not projects:
        return "No projects found."
    lines = [f"{'NAME':<30} {'FRAMEWORK':<15} {'UPDATED'}"]
    lines.append("─" * 65)
    for p in projects:
        fw  = p.get("framework") or "—"
        upd = (p.get("updatedAt") or "")[:10]
        lines.append(f"{p['name']:<30} {fw:<15} {upd}")
    return "\n".join(lines)


def run_list_deployments(params):
    project = params.get("project", "")
    limit   = params.get("limit", 10)
    url     = f"{BASE}/v6/deployments?limit={limit}"
    if project:
        url += f"&projectId={project}"
    resp = requests.get(url, headers=_headers(), timeout=10)
    resp.raise_for_status()
    deployments = resp.json().get("deployments", [])
    if not deployments:
        return "No deployments found."
    lines = [f"{'UID':<26} {'STATE':<12} {'URL':<35} {'CREATED'}"]
    lines.append("─" * 90)
    for d in deployments:
        state   = d.get("state", "?")
        dep_url = d.get("url", "")
        created = (d.get("createdAt") or "")
        if isinstance(created, int):
            import datetime
            created = datetime.datetime.fromtimestamp(created/1000).strftime("%Y-%m-%d %H:%M")
        lines.append(f"{d['uid']:<26} {state:<12} {dep_url:<35} {str(created)[:16]}")
    return "\n".join(lines)


def run_get_deployment(params):
    uid  = params["uid"]
    resp = requests.get(f"{BASE}/v13/deployments/{uid}", headers=_headers(), timeout=10)
    resp.raise_for_status()
    d = resp.json()
    return (
        f"UID:     {d.get('uid')}\n"
        f"URL:     {d.get('url')}\n"
        f"State:   {d.get('state')}\n"
        f"Branch:  {d.get('meta', {}).get('githubCommitRef', '—')}\n"
        f"Commit:  {d.get('meta', {}).get('githubCommitMessage', '—')}\n"
        f"Created: {d.get('createdAt')}"
    )


def run_deploy_project(params):
    """Trigger a deploy using the Vercel CLI (must be installed)."""
    project_dir = params.get("directory", ".")
    prod        = params.get("production", False)
    cmd         = f"vercel deploy {project_dir}"
    if prod:
        cmd += " --prod"
    cmd += f" --token {os.environ.get('VERCEL_TOKEN', '')}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    output = result.stdout or result.stderr
    return output[:2000] if output else "Deploy command ran (no output)."


def run_list_env_vars(params):
    project = params["project"]
    resp    = requests.get(f"{BASE}/v9/projects/{project}/env", headers=_headers(), timeout=10)
    resp.raise_for_status()
    envs = resp.json().get("envs", [])
    if not envs:
        return f"No env vars for project '{project}'."
    lines = [f"{'KEY':<35} {'TARGET':<15} {'TYPE'}"]
    lines.append("─" * 60)
    for e in envs:
        targets = ", ".join(e.get("target", []))
        lines.append(f"{e['key']:<35} {targets:<15} {e.get('type','')}")
    return "\n".join(lines)


TOOLS = [
    ({"name": "vercel_list_projects",
      "description": "List all Vercel projects in your account.",
      "input_schema": {"type": "object", "properties": {}}}, run_list_projects),

    ({"name": "vercel_list_deployments",
      "description": "List recent Vercel deployments, optionally filtered by project.",
      "input_schema": {"type": "object", "properties": {
          "project": {"type": "string", "description": "Project name or ID (optional)"},
          "limit":   {"type": "integer", "description": "Max results, default 10"},
      }}}, run_list_deployments),

    ({"name": "vercel_get_deployment",
      "description": "Get details of a specific Vercel deployment by UID.",
      "input_schema": {"type": "object", "properties": {
          "uid": {"type": "string", "description": "Deployment UID"}
      }, "required": ["uid"]}}, run_get_deployment),

    ({"name": "vercel_deploy",
      "description": "Trigger a Vercel deployment using the Vercel CLI.",
      "input_schema": {"type": "object", "properties": {
          "directory":  {"type": "string", "description": "Project directory (default: current)"},
          "production": {"type": "boolean", "description": "Deploy to production (default: false)"},
      }}}, run_deploy_project),

    ({"name": "vercel_list_env",
      "description": "List environment variables for a Vercel project.",
      "input_schema": {"type": "object", "properties": {
          "project": {"type": "string", "description": "Project name or ID"}
      }, "required": ["project"]}}, run_list_env_vars),
]
