"""
Tool: swarm_dispatch
Description: Dispatch up to 50 independent tasks to parallel Haiku sub-agents.
Runs 10 workers concurrently, writes every result to Obsidian automatically,
and returns a token-cheap summary to HUBERT's main context.
"""
import os, sys, threading, queue, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from ollama_core import OllamaCore as _OllamaCore
    _ollama = _OllamaCore()
except Exception:
    _ollama = None

from config import get_api_key

VAULT_PATH   = Path(os.environ.get("OBSIDIAN_VAULT_PATH", r"C:\Users\Jake\HUBERT_Vault"))
WORKER_COUNT = 10
MODEL        = "claude-haiku-4-5-20251001"

TOOL_DEFINITION = {
    "name": "swarm_dispatch",
    "description": (
        "Dispatch up to 50 independent tasks to parallel Haiku sub-agents. "
        "All agents run concurrently in batches of 10 — much cheaper and faster than "
        "doing them serially in HUBERT's main context. Each result is automatically "
        "written to the Obsidian vault. HUBERT receives only a compact summary. "
        "Use for: summarization, research, categorization, fact extraction, writing notes, "
        "data formatting, tagging — any task that doesn't need full conversation context."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": "List of independent task strings (2–50)",
                "items": {"type": "string"},
                "maxItems": 50,
            },
            "category": {
                "type": "string",
                "description": "Obsidian subfolder: 'Research', 'Analysis', 'Memory', 'Tasks', 'General' (default: General)",
            },
            "system": {
                "type": "string",
                "description": "System prompt for all sub-agents (default: concise task worker)",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Max tokens per agent response (default: 400)",
            },
            "save_to_obsidian": {
                "type": "boolean",
                "description": "Write results to Obsidian vault (default: true)",
            },
        },
        "required": ["tasks"],
    },
}


def _write_to_obsidian(note_name: str, content: str, category: str):
    try:
        target = VAULT_PATH / "Swarm" / category / f"{note_name}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except Exception:
        pass


def _agent_worker(idx: int, task: str, model: str, max_tokens: int,
                  system: str, api_key: str, result_q: queue.Queue):
    text = None

    # ── Try Ollama first (no assess_task pre-check — just attempt, fall back on failure) ──
    if _ollama is not None and _ollama.ollama_available():
        try:
            text = _ollama.run_task(system, task, max_tokens)
        except Exception:
            text = None   # fall through to Haiku

    # ── Haiku fallback ────────────────────────────────────────────────────────
    if text is None:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": task}],
            )
            text = resp.content[0].text.strip() if resp.content else "(no response)"
        except Exception as e:
            result_q.put((idx, task, None, str(e)))
            return

    result_q.put((idx, task, text, None))
    try:
        import ui_bridge
        ui_bridge.push("add_comm",
                       **{"from": f"agent-{idx+1:02d}", "to": "HUBERT",
                          "msg": text[:60]})
    except Exception:
        pass


def run(params: dict) -> str:
    tasks    = params.get("tasks", [])[:50]
    category = params.get("category", "General")
    system   = params.get("system",
               "You are a specialist sub-agent. Complete the task concisely in 2-5 sentences. "
               "Be precise, factual, and direct. No preamble.")
    max_tok  = params.get("max_tokens", 400)
    save_obs = params.get("save_to_obsidian", True)
    api_key  = get_api_key()

    if not api_key:
        return "Error: No API key configured."
    if not tasks:
        return "Error: No tasks provided."

    total     = len(tasks)
    result_q  = queue.Queue()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")

    # Notify swarm panel
    try:
        import ui_bridge
        for i in range(min(total, WORKER_COUNT)):
            ui_bridge.push("add_agent", name=f"agent-{i+1:02d}")
        ui_bridge.push("log", type="sys",
                       text=f"Swarm: dispatching {total} tasks → {WORKER_COUNT} workers")
    except Exception:
        pass

    # Process in batches of WORKER_COUNT
    for batch_start in range(0, total, WORKER_COUNT):
        batch = tasks[batch_start: batch_start + WORKER_COUNT]
        threads = []
        for i, task in enumerate(batch):
            idx = batch_start + i
            t = threading.Thread(
                target=_agent_worker,
                args=(idx, task, MODEL, max_tok, system, api_key, result_q),
                daemon=True,
            )
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=60)

    # Collect results
    results, errors = {}, {}
    while not result_q.empty():
        idx, task, text, err = result_q.get_nowait()
        if err:
            errors[idx] = err
        else:
            results[idx] = (task, text)

    # Write individual notes to Obsidian
    if save_obs:
        for idx, (task, text) in results.items():
            note_name = f"{timestamp}_{idx+1:02d}"
            note_content = (
                f"---\n"
                f"tags: [swarm, {category.lower()}, haiku]\n"
                f"date: {timestamp}\n"
                f"agent: {idx+1}\n"
                f"---\n\n"
                f"## Task\n{task}\n\n"
                f"## Result\n{text}\n"
            )
            _write_to_obsidian(note_name, note_content, category)

        # Summary index note
        summary_lines = [
            f"# Swarm Dispatch — {timestamp}",
            f"\n**Tasks:** {total}  ·  **Completed:** {len(results)}  ·  "
            f"**Errors:** {len(errors)}  ·  **Category:** {category}\n",
            "\n## Results\n",
        ]
        for idx in sorted(results.keys()):
            task, text = results[idx]
            summary_lines.append(
                f"### [{idx+1:02d}] {task[:80]}\n{text}\n"
            )
        if errors:
            summary_lines.append("\n## Errors\n")
            for idx, err in errors.items():
                summary_lines.append(f"- Agent {idx+1}: `{err}`")

        _write_to_obsidian(f"_summary_{timestamp}", "\n".join(summary_lines), category)

        try:
            import ui_bridge
            ui_bridge.push("log", type="sys",
                           text=f"Swarm results → Obsidian/Swarm/{category}/")
        except Exception:
            pass

    # Return compact summary for HUBERT (saves main-context tokens)
    completed = len(results)
    out = [f"✓ {completed}/{total} agents completed → Obsidian/Swarm/{category}/"]
    if errors:
        out.append(f"✗ {len(errors)} errors")
    # Show first 3 inline
    for idx in sorted(results.keys())[:3]:
        task, text = results[idx]
        out.append(
            f"\n[{idx+1}] {task[:70]}{'…' if len(task)>70 else ''}\n"
            f"    → {text[:130]}{'…' if len(text)>130 else ''}"
        )
    if completed > 3:
        out.append(f"\n… {completed-3} more results in Obsidian.")
    return "\n".join(out)


TOOLS = [(TOOL_DEFINITION, run)]
