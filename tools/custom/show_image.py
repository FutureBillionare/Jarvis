"""
Tool: show_image
Description: Display a picture in the HUBERT chat — for any image HUBERT finds
on the web or generates locally and wants to show inline.
"""
import os
from pathlib import Path

import ui_bridge


def run_show_image(params: dict) -> str:
    src = (params.get("src") or params.get("url") or params.get("path") or "").strip()
    caption = (params.get("caption") or "").strip()

    if not src:
        return "Error: 'src' (URL or local file path) is required."

    # Accept either an http(s) URL or a local path
    is_url = src.lower().startswith(("http://", "https://"))
    if not is_url:
        p = Path(os.path.expanduser(src))
        if not p.exists():
            return f"Error: file not found: {p}"
        src = str(p.resolve())

    ui_bridge.push("chat_show_image", src=src, caption=caption)
    return f"Displayed image in chat: {src}" + (f" — {caption}" if caption else "")


TOOL_DEFINITION = {
    "name": "show_image",
    "description": (
        "Display an image inside the HUBERT chat window. Use this whenever a picture "
        "would help explain something — e.g. a diagram, a photo from search results, "
        "a generated chart, or any image referenced by URL or local file path. "
        "Accepts either an http(s) URL or an absolute local file path."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "src": {
                "type": "string",
                "description": "Image source: an http(s) URL or an absolute local file path.",
            },
            "caption": {
                "type": "string",
                "description": "Optional short caption shown below the image.",
            },
        },
        "required": ["src"],
    },
}


TOOLS = [
    (TOOL_DEFINITION, run_show_image),
]
