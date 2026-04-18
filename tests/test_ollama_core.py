"""Tests for ollama_core.OllamaCore."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch, MagicMock
import pytest
import requests

from ollama_core import OllamaCore


def _make_response(text: str, status=200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = {
        "message": {"content": text}
    }
    m.raise_for_status = MagicMock()
    return m


class TestOllamaAvailable:
    def test_returns_true_when_server_responds(self):
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200)
            core = OllamaCore()
            assert core.ollama_available() is True

    def test_returns_false_on_connection_error(self):
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("refused")):
            core = OllamaCore()
            assert core.ollama_available() is False


class TestAssessTask:
    def test_returns_true_for_yes_response(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value = _make_response("YES, this is straightforward")
            core = OllamaCore()
            assert core.assess_task("Summarise this paragraph") is True

    def test_returns_false_for_no_response(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value = _make_response("NO, needs real-time data")
            core = OllamaCore()
            assert core.assess_task("What is today's stock price?") is False

    def test_returns_false_on_error(self):
        with patch("requests.post", side_effect=Exception("timeout")):
            core = OllamaCore()
            assert core.assess_task("anything") is False


class TestRunTask:
    def test_returns_response_text(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value = _make_response("Paris is the capital of France.")
            core = OllamaCore()
            result = core.run_task("Be concise.", "What is the capital of France?")
            assert result == "Paris is the capital of France."

    def test_raises_on_connection_error(self):
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("no server")):
            core = OllamaCore()
            with pytest.raises(ConnectionError):
                core.run_task("sys", "task")
