# tests/test_cc_stream_parser.py
import json
import pytest
from claude_code_backend import StreamParser


def _lines(*events):
    """Serialize dicts to newline-separated JSON strings."""
    return [json.dumps(e) + "\n" for e in events]


def test_text_delta_fires_on_text():
    received = []
    parser = StreamParser(on_text=received.append)
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_delta", "index": 0,
                  "delta": {"type": "text_delta", "text": "hello"}}
    }))
    assert received == ["hello"]


def test_tool_use_fires_on_tool_start():
    starts = []
    parser = StreamParser(on_tool_start=lambda n, p: starts.append((n, p)))

    # content_block_start with tool_use
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_start", "index": 1,
                  "content_block": {"type": "tool_use", "id": "tu_1", "name": "Bash", "input": {}}}
    }))
    # input_json_delta
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_delta", "index": 1,
                  "delta": {"type": "input_json_delta", "partial_json": '{"command": "ls"}'}}
    }))
    # content_block_stop
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_stop", "index": 1}
    }))

    assert len(starts) == 1
    assert starts[0] == ("Bash", {"command": "ls"})


def test_tool_result_fires_on_tool_result():
    starts = []
    results = []
    parser = StreamParser(
        on_tool_start=lambda n, p: starts.append((n, p)),
        on_tool_result=lambda n, r: results.append((n, r)),
    )

    # First: register the tool call so the id is known
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_start", "index": 0,
                  "content_block": {"type": "tool_use", "id": "tu_abc", "name": "Read", "input": {}}}
    }))
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_stop", "index": 0}
    }))

    # Then: user message with tool_result
    parser.feed(json.dumps({
        "type": "user",
        "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu_abc", "content": "file contents here"}
        ]}
    }))

    assert results == [("Read", "file contents here")]


def test_tool_result_with_list_content():
    results = []
    parser = StreamParser(on_tool_result=lambda n, r: results.append((n, r)))

    # Register tool id without firing on_tool_start (just need the mapping)
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_start", "index": 0,
                  "content_block": {"type": "tool_use", "id": "tu_xyz", "name": "Grep", "input": {}}}
    }))
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_stop", "index": 0}
    }))

    parser.feed(json.dumps({
        "type": "user",
        "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu_xyz",
             "content": [{"type": "text", "text": "match line 1"}, {"type": "text", "text": "match line 2"}]}
        ]}
    }))

    assert results[0] == ("Grep", "match line 1 match line 2")


def test_invalid_json_ignored():
    received = []
    parser = StreamParser(on_text=received.append)
    parser.feed("not json at all\n")
    assert received == []


def test_non_tool_content_block_start_ignored():
    starts = []
    parser = StreamParser(on_tool_start=lambda n, p: starts.append((n, p)))
    # text content block — should not start a tool accumulation
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_start", "index": 0,
                  "content_block": {"type": "text"}}
    }))
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_stop", "index": 0}
    }))
    assert starts == []


def test_split_input_json_accumulated():
    """input_json_delta arrives in multiple chunks — final params should be complete."""
    starts = []
    parser = StreamParser(on_tool_start=lambda n, p: starts.append((n, p)))

    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_start", "index": 0,
                  "content_block": {"type": "tool_use", "id": "tu_split", "name": "Edit", "input": {}}}
    }))
    # Three partial JSON chunks
    for chunk in ['{"file_path": "/foo/bar"', ', "old_string": "x"', ', "new_string": "y"}']:
        parser.feed(json.dumps({
            "type": "stream_event",
            "event": {"type": "content_block_delta", "index": 0,
                      "delta": {"type": "input_json_delta", "partial_json": chunk}}
        }))
    parser.feed(json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_stop", "index": 0}
    }))

    assert starts == [("Edit", {"file_path": "/foo/bar", "old_string": "x", "new_string": "y"})]
