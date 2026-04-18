"""
Tool: ollama_swarm
Description: Run up to 20 independent tasks in parallel on local Ollama — zero Anthropic tokens.
Fastest and cheapest option for batch summarization, categorization, formatting, and simple Q&A.
"""
import sys
import threading
import queue
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

TOOL_DEFINITION = {
    "name": "ollama_swarm",
    "description": (
        "⭐ ZERO TOKENS: Run up to 20 independent tasks in parallel on local Ollama (llama3). "
        "Completely free — no Anthropic API calls at all. "
        "Use this FIRST for any batch of lightweight tasks before considering swarm_dispatch or "
        "swarm_bridge_parallel. Best for: summarising text, categorising items, formatting data, "
        "generating short descriptions, simple Q&A, drafting outlines, translating, tagging. "
        "Falls back with an error if Ollama is not running (start with: ollama serve). "
        "Returns all results inline — nothing is written to Obsidian unless you ask."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": "List of independent tasks to run on Ollama (2-20 items)",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 20,
            },
            "system": {
                "type": "string",
                "description": "System prompt for all workers (default: concise task worker)",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Max tokens per response (default: 300)",
            },
            "model": {
                "type": "string",
                "description": "Ollama model to use (default: llama3). Other options: mistral, phi3, gemma2",
            },
        },
        "required": ["tasks"],
    },
}


def run(params: dict) -> str:
    from ollama_core import OllamaCore

    tasks      = params.get("tasks", [])[:20]
    system     = params.get("system", "Be concise and direct. Complete the task in 1-3 sentences.")
    max_tokens = params.get("max_tokens", 300)
    model_name = params.get("model", None)  # None → use OllamaCore default

    if not tasks:
        return "Error: No tasks provided."

    oc = OllamaCore()
    if model_name:
        oc.model = model_name

    if not oc.ollama_available():
        return "Error: Ollama is not running. Start it with: ollama serve"

    # Notify swarm panel
    try:
        import ui_bridge
        for i in range(len(tasks)):
            ui_bridge.push("add_agent", name=f"ollama-{i+1:02d}")
        ui_bridge.push("log", type="sys",
                       text=f"OllamaSwarm: {len(tasks)} tasks → {oc.model} [FREE]")
    except Exception:
        pass

    result_q: queue.Queue = queue.Queue()

    def _worker(idx: int, task: str):
        try:
            text = oc.run_task(system, task, max_tokens)
            result_q.put((idx, task, text, None))
        except Exception as e:
            result_q.put((idx, task, None, str(e)))
        # Notify swarm panel
        try:
            import ui_bridge
            ui_bridge.push("add_comm",
                           **{"from": f"ollama-{idx+1:02d}", "to": "HUBERT",
                              "msg": (text[:60] if text else "error")})
        except Exception:
            pass

    threads = []
    for i, task in enumerate(tasks):
        t = threading.Thread(target=_worker, args=(i, task), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=60)

    # Collect results
    raw: dict[int, tuple] = {}
    while not result_q.empty():
        idx, task, text, err = result_q.get_nowait()
        raw[idx] = (task, text, err)

    parts = []
    errors = 0
    for i in range(len(tasks)):
        if i not in raw:
            parts.append(f"[{i+1}] TIMEOUT")
            errors += 1
            continue
        task, text, err = raw[i]
        if err:
            parts.append(f"[{i+1}] ERROR: {err}")
            errors += 1
        else:
            parts.append(f"[{i+1}] {text}")

    header = f"OllamaSwarm: {len(tasks)-errors}/{len(tasks)} completed on {oc.model} (0 Anthropic tokens)\n"
    return header + "\n".join(parts)


TOOLS = [(TOOL_DEFINITION, run)]
