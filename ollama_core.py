"""
OllamaCore — wraps the Ollama REST API for local llama3 inference.

Used by swarm tools to attempt tasks locally before falling back to
Claude Haiku. Never used in HUBERT's main conversation path.
"""
import requests

OLLAMA_BASE  = "http://localhost:11434"
OLLAMA_MODEL = "llama3"

_ASSESS_SYSTEM = (
    "You are a capability assessor. Answer ONLY \"YES\" or \"NO\". "
    "No explanation, no punctuation beyond the word itself."
)

_ASSESS_TEMPLATE = (
    "Can a small open-source LLM (7B parameters, no internet access, no tools) "
    "complete the following task accurately?\n\n"
    "Task: {task}\n\n"
    "Answer YES only if the task requires only text reasoning, summarisation, "
    "categorisation, formatting, or simple factual recall within common knowledge. "
    "Answer NO if it requires real-time data, complex multi-step code generation, "
    "multi-step tool calls, or advanced reasoning."
)


class OllamaCore:
    def __init__(self, base_url: str = OLLAMA_BASE, model: str = OLLAMA_MODEL):
        self.base_url = base_url
        self.model    = model

    def ollama_available(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            requests.get(self.base_url, timeout=1)
            return True
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                OSError):
            return False

    def assess_task(self, task: str) -> bool:
        """
        Ask llama3 whether it can handle this task.
        Returns True (attempt locally) or False (escalate to Haiku).
        Returns False on any error — fail safe.
        """
        try:
            prompt = _ASSESS_TEMPLATE.format(task=task)
            resp   = self._chat(_ASSESS_SYSTEM, prompt, max_tokens=5)
            first_word = resp.strip().split()[0].upper().rstrip(".,!?")
            return first_word == "YES"
        except Exception:
            return False

    def run_task(self, system: str, task: str, max_tokens: int = 400) -> str:
        """
        Run a task on llama3 and return the response text.
        Raises ConnectionError if the server is unreachable.
        Raises RuntimeError on unexpected API errors.
        """
        return self._chat(system, task, max_tokens)

    def _chat(self, system: str, user: str, max_tokens: int) -> str:
        url  = f"{self.base_url}/api/chat"
        body = {
            "model":  self.model,
            "stream": False,
            "options": {"num_predict": max_tokens},
            "messages": [
                {"role": "system",  "content": system},
                {"role": "user",    "content": user},
            ],
        }
        try:
            resp = requests.post(url, json=body, timeout=30)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Ollama server unreachable: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Ollama API error: {e}") from e
