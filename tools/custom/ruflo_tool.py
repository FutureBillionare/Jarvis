"""
Tool: ruflo_tool
Description: Ruflo multi-agent orchestration — spawn agent swarms, coordinate hive-mind
tasks, manage memory, and run parallel AI workloads via the Ruflo framework.
"""
import subprocess, json, os, shutil

RUFLO = shutil.which("ruflo") or "npx ruflo@latest"


def _run(args: list[str], timeout: int = 60) -> str:
    cmd = ([RUFLO] if shutil.which("ruflo") else ["npx", "ruflo@latest"]) + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "NO_COLOR": "1"})
        out = (r.stdout or "") + (r.stderr or "")
        return out.strip()[:3000] if out.strip() else "Command ran with no output."
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s."
    except Exception as e:
        return f"Error: {e}"


def run_hive_spawn(params: dict) -> str:
    """Spawn a hive-mind swarm to tackle a complex task."""
    task    = params["task"]
    agents  = params.get("agents", 3)
    topology= params.get("topology", "hierarchical")
    return _run(["hive-mind", "spawn", task,
                 "--agents", str(agents),
                 "--topology", topology], timeout=120)


def run_agent_spawn(params: dict) -> str:
    """Spawn a single specialized agent."""
    agent_type = params["type"]   # coder, tester, researcher, analyst, etc.
    name       = params.get("name", f"{agent_type}-agent")
    task       = params.get("task", "")
    args = ["agent", "spawn", "-t", agent_type, "--name", name]
    if task:
        args += ["--task", task]
    return _run(args)


def run_swarm_status(params: dict) -> str:
    """Get status of running swarms and agents."""
    return _run(["swarm", "status"])


def run_swarm_metrics(params: dict) -> str:
    """Get performance metrics for active swarms."""
    return _run(["swarm", "metrics"])


def run_memory_store(params: dict) -> str:
    """Store a value in Ruflo's persistent memory."""
    key   = params["key"]
    value = params["value"]
    return _run(["memory", "store", "--key", key, "--value", value])


def run_memory_search(params: dict) -> str:
    """Search Ruflo's vector memory for relevant information."""
    query = params["query"]
    limit = params.get("limit", 5)
    return _run(["memory", "search", "--query", query, "--limit", str(limit)])


def run_memory_stats(params: dict) -> str:
    """Get memory system statistics."""
    return _run(["memory", "stats"])


def run_mcp_tools(params: dict) -> str:
    """List available MCP tools, optionally filtered by category."""
    args = ["mcp", "tools"]
    if params.get("category"):
        args += ["--category", params["category"]]
    return _run(args)


def run_agent_list(params: dict) -> str:
    """List all active agents."""
    return _run(["agent", "list"])


def run_hive_status(params: dict) -> str:
    """Get hive-mind status and active queen agents."""
    return _run(["hive-mind", "status"])


def run_status(params: dict) -> str:
    """Get full Ruflo system status."""
    target = params.get("target", "agents")  # agents, tasks, memory
    return _run(["status", target])


def run_hooks_intelligence(params: dict) -> str:
    """Check Ruflo's self-learning hooks and intelligence status."""
    return _run(["hooks", "intelligence", "--status"])


TOOLS = [
    ({"name": "ruflo_hive_spawn",
      "description": "Spawn a queen-led hive-mind swarm of AI agents to autonomously complete a complex multi-step task.",
      "input_schema": {"type": "object", "properties": {
          "task":     {"type": "string", "description": "The task or goal for the swarm"},
          "agents":   {"type": "integer", "description": "Number of agents (default 3)"},
          "topology": {"type": "string",  "description": "Swarm topology: hierarchical, mesh, ring, star (default: hierarchical)"},
      }, "required": ["task"]}}, run_hive_spawn),

    ({"name": "ruflo_agent_spawn",
      "description": "Spawn a single specialized Ruflo agent (coder, tester, researcher, analyst, etc.).",
      "input_schema": {"type": "object", "properties": {
          "type": {"type": "string", "description": "Agent type: coder, tester, researcher, analyst, architect, reviewer"},
          "name": {"type": "string", "description": "Agent name"},
          "task": {"type": "string", "description": "Optional task to assign immediately"},
      }, "required": ["type"]}}, run_agent_spawn),

    ({"name": "ruflo_swarm_status",
      "description": "Get status of all running Ruflo swarms and agents.",
      "input_schema": {"type": "object", "properties": {}}}, run_swarm_status),

    ({"name": "ruflo_swarm_metrics",
      "description": "Get performance metrics for active Ruflo swarms.",
      "input_schema": {"type": "object", "properties": {}}}, run_swarm_metrics),

    ({"name": "ruflo_memory_store",
      "description": "Store a key-value pair in Ruflo's persistent vector memory.",
      "input_schema": {"type": "object", "properties": {
          "key":   {"type": "string"},
          "value": {"type": "string"},
      }, "required": ["key", "value"]}}, run_memory_store),

    ({"name": "ruflo_memory_search",
      "description": "Search Ruflo's vector memory for information relevant to a query.",
      "input_schema": {"type": "object", "properties": {
          "query": {"type": "string"},
          "limit": {"type": "integer", "description": "Max results (default 5)"},
      }, "required": ["query"]}}, run_memory_search),

    ({"name": "ruflo_memory_stats",
      "description": "Get Ruflo memory system statistics.",
      "input_schema": {"type": "object", "properties": {}}}, run_memory_stats),

    ({"name": "ruflo_mcp_tools",
      "description": "List available Ruflo MCP tools, optionally filtered by category.",
      "input_schema": {"type": "object", "properties": {
          "category": {"type": "string", "description": "Filter by category e.g. agent-tools, swarm-tools, memory-tools, neural-tools"},
      }}}, run_mcp_tools),

    ({"name": "ruflo_agent_list",
      "description": "List all active Ruflo agents and their states.",
      "input_schema": {"type": "object", "properties": {}}}, run_agent_list),

    ({"name": "ruflo_hive_status",
      "description": "Get hive-mind status including active queen agents.",
      "input_schema": {"type": "object", "properties": {}}}, run_hive_status),

    ({"name": "ruflo_status",
      "description": "Get full Ruflo system status for agents, tasks, or memory.",
      "input_schema": {"type": "object", "properties": {
          "target": {"type": "string", "description": "What to check: agents, tasks, memory (default: agents)"},
      }}}, run_status),

    ({"name": "ruflo_hooks_intelligence",
      "description": "Check Ruflo's self-learning hooks and intelligence routing status.",
      "input_schema": {"type": "object", "properties": {}}}, run_hooks_intelligence),
]
