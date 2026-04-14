"""
Claude Code CLI backend — routes HUBERT messages through the `claude` CLI subprocess.
Uses the user's Claude.ai subscription (Pro/Max) instead of Anthropic API credits.

Streaming strategy: --output-format stream-json + --include-partial-messages emits
individual token deltas via stream_event → content_block_delta → text_delta.
Tool calls arrive as content_block_start (tool_use) → input_json_delta → content_block_stop.
Tool results arrive as user message events with tool_result content blocks.

History strategy: caller passes a list of {role, content} dicts; this module injects
them as a conversation prefix in the prompt so the stateless `claude -p` call has context.
"""
import json
import subprocess
import threading
import shutil
from typing import Callable

_HISTORY_TURNS = 24   # max turns to inject (12 exchanges)
_TURN_MAX_CHARS = 600 # truncate very long turns in the history prefix


def _find_claude_bin() -> str | None:
    return shutil.which("claude")


_EXTRA_FLAGS = [
    "--dangerously-skip-permissions",   # user-approved: skip all tool permission prompts
    "--no-session-persistence",
    "--output-format", "stream-json",
    "--include-partial-messages",
    "--verbose",
]


def _build_prompt(message: str, history: list[dict] | None,
                  last_session: str | None) -> str:
    """
    Prepend conversation history (and optional last-session recap) to the message
    so claude -p has full context despite being stateless.
    """
    parts = []

    if last_session:
        parts.append(
            f"[PREVIOUS SESSION RECAP]\n{last_session.strip()}\n[END RECAP]"
        )

    if history:
        recent = history[-_HISTORY_TURNS:]
        lines = []
        for turn in recent:
            role    = "User" if turn["role"] == "user" else "HUBERT"
            content = turn["content"]
            if len(content) > _TURN_MAX_CHARS:
                content = content[:_TURN_MAX_CHARS] + "…"
            lines.append(f"{role}: {content}")
        if lines:
            parts.append(
                "[CONVERSATION HISTORY]\n"
                + "\n".join(lines)
                + "\n[END HISTORY]"
            )

    parts.append(f"User: {message}")
    return "\n\n".join(parts)


class StreamParser:
    """
    Stateful parser for the claude CLI stream-json output.

    Call .feed(line) for each raw stdout line. Fires callbacks:
      on_text(text)             — streaming text delta
      on_tool_start(name, params) — tool call detected (name=str, params=dict)
      on_tool_result(name, result) — tool result received (result=str)
    """

    def __init__(
        self,
        on_text: Callable[[str], None] | None = None,
        on_tool_start: Callable[[str, dict], None] | None = None,
        on_tool_result: Callable[[str, str], None] | None = None,
    ):
        self._on_text        = on_text
        self._on_tool_start  = on_tool_start
        self._on_tool_result = on_tool_result
        self._current_tool: dict | None = None   # {"id": ..., "name": ...}
        self._input_buf: str = ""
        self._tool_id_to_name: dict[str, str] = {}

    def feed(self, line: str) -> None:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return

        t = event.get("type")

        if t == "stream_event":
            self._handle_stream_event(event.get("event", {}))
        elif t == "user":
            self._handle_user_message(event.get("message", {}))

    def _handle_stream_event(self, inner: dict) -> None:
        inner_type = inner.get("type")

        if inner_type == "content_block_start":
            cb = inner.get("content_block", {})
            if cb.get("type") == "tool_use":
                self._current_tool = {"id": cb["id"], "name": cb["name"]}
                self._input_buf = ""

        elif inner_type == "content_block_delta":
            delta = inner.get("delta", {})
            dtype = delta.get("type")
            if dtype == "text_delta":
                text = delta.get("text")
                if text and self._on_text:
                    self._on_text(text)
            elif dtype == "input_json_delta" and self._current_tool is not None:
                self._input_buf += delta.get("partial_json", "")

        elif inner_type == "content_block_stop":
            if self._current_tool is not None:
                name = self._current_tool["name"]
                tid  = self._current_tool["id"]
                try:
                    params = json.loads(self._input_buf) if self._input_buf else {}
                except (json.JSONDecodeError, ValueError):
                    params = {}
                self._tool_id_to_name[tid] = name
                if self._on_tool_start:
                    self._on_tool_start(name, params)
                self._current_tool = None
                self._input_buf = ""

    def _handle_user_message(self, msg: dict) -> None:
        content = msg.get("content", [])
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            tool_use_id    = block.get("tool_use_id", "")
            result_content = block.get("content", "")
            name = self._tool_id_to_name.get(tool_use_id, tool_use_id)
            if isinstance(result_content, list):
                result_text = " ".join(
                    b.get("text", "")
                    for b in result_content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                result_text = str(result_content)
            if self._on_tool_result:
                self._on_tool_result(name, result_text)


def chat_in_thread(
    message: str,
    history: list[dict] | None = None,
    last_session: str | None = None,
    on_text: Callable[[str], None] | None = None,
    on_done: Callable[[], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    on_tool_start: Callable[[str, dict], None] | None = None,
    on_tool_result: Callable[[str, str], None] | None = None,
    on_status: Callable[[str], None] | None = None,
    **kwargs,
):
    """
    Spawn `claude -p <prompt>` with conversation history injected in the prompt.
    Streams text deltas via on_text, tool events via on_tool_start/on_tool_result,
    lifecycle events via on_status, then calls on_done/on_error.
    """
    claude_bin = _find_claude_bin()
    if not claude_bin:
        if on_error:
            on_error(
                "claude CLI not found in PATH.\n"
                "Install: npm install -g @anthropic-ai/claude-code"
            )
        return

    prompt = _build_prompt(message, history, last_session)

    def _run():
        try:
            cmd = [claude_bin, "-p", prompt] + _EXTRA_FLAGS
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            if on_status:
                on_status("CC ▶ session started")
            # Drain stderr concurrently — avoids pipe deadlock when --verbose
            # produces large output while stdout is still being read
            _stderr_chunks: list[str] = []
            def _drain_stderr():
                _stderr_chunks.append(proc.stderr.read())
            _stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            _stderr_thread.start()
            parser = StreamParser(
                on_text=on_text,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
            )
            for raw_line in proc.stdout:
                parser.feed(raw_line)
            proc.wait()
            _stderr_thread.join(timeout=2.0)
            stderr_out = "".join(_stderr_chunks).strip()
            if proc.returncode == 0:
                if on_status:
                    on_status("CC ✓ done")
                if on_done:
                    on_done()
            else:
                if on_status:
                    on_status("CC ✗ error")
                if on_error:
                    on_error(stderr_out or f"claude exited with code {proc.returncode}")
        except Exception as exc:
            if on_status:
                on_status("CC ✗ error")
            if on_error:
                on_error(str(exc))

    threading.Thread(target=_run, daemon=True).start()
