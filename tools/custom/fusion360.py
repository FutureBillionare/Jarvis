"""
Tool: fusion360
Description: Control Autodesk Fusion 360 via its local MCP server (must be running with MCPserve add-in active)
"""
import json
import time
import threading
import requests

FUSION_SSE_URL = "http://127.0.0.1:3000/sse"
FUSION_MSG_URL = "http://127.0.0.1:3000/messages"

TOOL_DEFINITION = {
    "name": "fusion360",
    "description": (
        "Send commands to Autodesk Fusion 360 via its local MCP server. "
        "Requires Fusion 360 to be open with the MCPserve add-in running. "
        "Supports creating sketches, extruding bodies, applying fillets, exporting STL/STEP/3MF, "
        "querying design structure and parameters, and running arbitrary Fusion API Python scripts."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "The MCP tool name to call. Examples: 'create_sketch', 'extrude', "
                    "'export_stl', 'get_design_info', 'run_script', 'get_active_document', "
                    "'create_box', 'apply_fillet', 'export_step'"
                )
            },
            "params": {
                "type": "object",
                "description": "Parameters for the action. Varies by action (e.g. {'sketch_plane': 'XY', 'width': 50, 'height': 30} for create_sketch)"
            },
            "check_status": {
                "type": "boolean",
                "description": "If true, just check whether the Fusion MCP server is reachable and return status (ignores action/params)"
            }
        },
        "required": []
    }
}


def _check_server() -> dict:
    """Check if the Fusion MCP server is reachable."""
    try:
        resp = requests.get(FUSION_SSE_URL, timeout=3, stream=True)
        resp.close()
        return {"running": True, "url": FUSION_SSE_URL}
    except requests.exceptions.ConnectionError:
        return {"running": False, "error": "Cannot connect to Fusion MCP server at 127.0.0.1:3000. Make sure Fusion 360 is open and the MCPserve add-in is running."}
    except Exception as e:
        return {"running": False, "error": str(e)}


def _call_tool(tool_name: str, tool_params: dict) -> str:
    """
    Send an MCP tool call to the Fusion server via HTTP+SSE.
    The MCP-over-SSE protocol:
      1. GET /sse  → server sends 'endpoint' event with a session-specific POST URL
      2. POST that URL with a JSON-RPC initialize message, then tools/call
      3. Server sends the result back over SSE
    """
    result_holder = {"done": False, "result": None, "error": None}
    session_post_url = [None]
    call_id = 1

    def listen_sse():
        try:
            with requests.get(FUSION_SSE_URL, stream=True, timeout=30) as resp:
                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data = line[5:].strip()
                        if event_type == "endpoint":
                            # Server tells us where to POST messages
                            post_path = data.strip()
                            if post_path.startswith("/"):
                                session_post_url[0] = f"http://127.0.0.1:3000{post_path}"
                            else:
                                session_post_url[0] = post_path
                            # Send initialize then tools/call
                            _send_requests(session_post_url[0])
                        elif event_type == "message":
                            try:
                                msg = json.loads(data)
                                if isinstance(msg, dict) and msg.get("id") == call_id + 1:
                                    # This is our tools/call response
                                    if "result" in msg:
                                        content = msg["result"].get("content", [])
                                        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                                        result_holder["result"] = "\n".join(texts) if texts else json.dumps(msg["result"])
                                    elif "error" in msg:
                                        result_holder["error"] = msg["error"].get("message", str(msg["error"]))
                                    result_holder["done"] = True
                                    return
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            result_holder["error"] = f"SSE connection error: {e}"
            result_holder["done"] = True

    event_type = "message"  # default, updated inline

    def _send_requests(post_url):
        nonlocal call_id
        try:
            # 1. Initialize
            init_msg = {
                "jsonrpc": "2.0",
                "id": call_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "HUBERT", "version": "1.0"}
                }
            }
            requests.post(post_url, json=init_msg, timeout=5)

            # 2. Initialized notification
            requests.post(post_url, json={"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=5)

            # 3. tools/call
            call_id_tools = call_id + 1
            tool_msg = {
                "jsonrpc": "2.0",
                "id": call_id_tools,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": tool_params
                }
            }
            requests.post(post_url, json=tool_msg, timeout=5)
        except Exception as e:
            result_holder["error"] = f"Failed to send requests: {e}"
            result_holder["done"] = True

    # Run SSE listener in background thread
    t = threading.Thread(target=listen_sse, daemon=True)
    t.start()

    # Wait up to 30 seconds for result
    deadline = time.time() + 30
    while not result_holder["done"] and time.time() < deadline:
        time.sleep(0.1)

    if not result_holder["done"]:
        return "Timeout: Fusion did not respond within 30 seconds. Make sure the add-in is running and Fusion is not busy."

    if result_holder["error"]:
        return f"Error: {result_holder['error']}"

    return result_holder["result"] or "Command completed (no output returned)"


def run(params: dict) -> str:
    check_status = params.get("check_status", False)

    if check_status:
        status = _check_server()
        if status["running"]:
            return "Fusion 360 MCP server is running at http://127.0.0.1:3000/sse"
        return status["error"]

    action = params.get("action", "").strip()
    tool_params = params.get("params", {})

    if not action:
        # Default: return status + available tools hint
        status = _check_server()
        if not status["running"]:
            return status["error"]
        return (
            "Fusion 360 MCP server is online.\n"
            "Specify an 'action' to call a tool. Common actions:\n"
            "  get_active_document, create_sketch, extrude, apply_fillet,\n"
            "  export_stl, export_step, export_3mf, run_script, get_design_structure"
        )

    # Quick reachability check before trying
    status = _check_server()
    if not status["running"]:
        return status["error"]

    return _call_tool(action, tool_params)


TOOLS = [(TOOL_DEFINITION, run)]
