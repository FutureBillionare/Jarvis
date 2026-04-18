"""
Tool: swarm_bridge
Description: Spawn lightweight parallel Claude sub-agents for independent tasks.
Each agent runs with its own minimal context (no full history) — faster and
cheaper than doing everything in HUBERT's main loop. Results are aggregated
and returned together. Use whenever tasks are independent and can run in parallel.
"""
import sys, threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from ollama_core import OllamaCore as _OllamaCore
    _ollama = _OllamaCore()
except Exception:
    _ollama = None

from config import get_api_key

# Model tiers
MODELS = {
    "fast":    "claude-haiku-4-5-20251001",   # cheapest + fastest
    "smart":   "claude-sonnet-4-6",            # same as HUBERT
}


TOOL_DEFINITION = {
    "name": "swarm_bridge_parallel",
    "description": (
        "Spawn multiple parallel sub-agents, each handling one independent task. "
        "Use when you have 2-6 independent research, analysis, or writing tasks. "
        "TIER GUIDE — pick the cheapest tier that can handle the work:\n"
        "  'ollama' = local Llama3, ZERO Anthropic tokens (summarise, format, classify, Q&A)\n"
        "  'fast'   = Haiku (default) — Ollama-first, Haiku fallback if Ollama fails\n"
        "  'smart'  = Sonnet — only for tasks requiring deep reasoning or code generation"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": "List of independent task descriptions (2-6 tasks)",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 6,
            },
            "tier": {
                "type": "string",
                "description": "Agent tier: 'ollama' (free/local), 'fast' (Haiku, default), 'smart' (Sonnet)",
                "enum": ["ollama", "fast", "smart"],
            },
            "max_tokens": {
                "type": "integer",
                "description": "Max tokens per agent response (default 512)",
            },
            "system": {
                "type": "string",
                "description": "Optional system prompt for all sub-agents",
            },
        },
        "required": ["tasks"],
    },
}


def run(params: dict) -> str:
    tasks      = params["tasks"][:6]
    tier_key   = params.get("tier", "fast")
    model      = MODELS.get(tier_key, MODELS["fast"])
    max_tokens = params.get("max_tokens", 512)
    system     = params.get("system", "Be concise and direct. Answer only what is asked.")

    # For "ollama" tier, check availability before even loading Anthropic
    if tier_key == "ollama":
        if _ollama is None or not _ollama.ollama_available():
            return "Error: Ollama tier requested but Ollama is not running. Start with: ollama serve"

    api_key = get_api_key() if tier_key != "ollama" else None

    # Notify swarm panel if UI is running
    tier_label = {"ollama": "ollama/free", "fast": "haiku", "smart": "sonnet"}.get(tier_key, tier_key)
    try:
        import ui_bridge
        for i in range(len(tasks)):
            ui_bridge.push("add_agent", name=f"sub-{i+1}")
        ui_bridge.push("log", type="sys",
                       text=f"Swarm: {len(tasks)} agents [{tier_label}]")
    except Exception:
        pass

    results = {}
    errors  = {}
    lock    = threading.Lock()

    def _run_agent(idx: int, task: str):
        text = None

        # ── Ollama path ───────────────────────────────────────────────────────
        if tier_key == "ollama":
            # Pure-Ollama: no Claude API calls at all
            try:
                text = _ollama.run_task(system, task, max_tokens)
            except Exception as e:
                with lock:
                    errors[idx] = f"Ollama error: {e}"
                return
        elif tier_key != "smart" and _ollama is not None and _ollama.ollama_available():
            # fast tier: try Ollama first, fall through to Haiku on failure
            try:
                text = _ollama.run_task(system, task, max_tokens)
            except Exception:
                text = None

        # ── Claude fallback (fast/smart tiers only) ───────────────────────────
        if text is None:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                resp   = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": task}],
                )
                text = resp.content[0].text.strip() if resp.content else "(no response)"
                with lock:
                    results[idx] = text
            except Exception as e:
                with lock:
                    errors[idx] = str(e)
                return
        else:
            with lock:
                results[idx] = text

        try:
            import ui_bridge
            ui_bridge.push("add_comm",
                           **{"from": f"sub-{idx+1}", "to": "HUBERT",
                              "msg": text[:60]})
        except Exception:
            pass

    threads = []
    for i, task in enumerate(tasks):
        t = threading.Thread(target=_run_agent, args=(i, task), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=45)

    # Aggregate results in order
    parts = []
    for i, task in enumerate(tasks):
        label = f"[Agent {i+1}]"
        if i in results:
            parts.append(f"{label}\n{results[i]}")
        elif i in errors:
            parts.append(f"{label}\nError: {errors[i]}")
        else:
            parts.append(f"{label}\nTimed out after 45s.")

    return "\n\n---\n\n".join(parts)


TOOLS = [(TOOL_DEFINITION, run)]
