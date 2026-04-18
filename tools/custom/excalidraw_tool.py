"""
Tool: excalidraw_tool
Description: Create and manage Excalidraw diagrams — generate flowcharts, mind maps,
system diagrams, and open them directly in the browser.
"""
import json, os, tempfile, webbrowser
from pathlib import Path

DIAGRAMS_DIR = Path(__file__).parent.parent.parent / "diagrams"
DIAGRAMS_DIR.mkdir(exist_ok=True)


def _base_file(elements=None, app_state=None):
    """Return a valid Excalidraw file structure."""
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements or [],
        "appState": app_state or {
            "gridSize": None,
            "viewBackgroundColor": "#ffffff",
        },
        "files": {},
    }


def _rect(id_, x, y, w, h, label, bg="#e7f5ff", stroke="#1971c2"):
    return {
        "id": id_, "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid", "strokeWidth": 2,
        "roughness": 1, "opacity": 100,
        "boundElements": [{"type": "text", "id": f"t{id_}"}],
        "text": label,
    }, {
        "id": f"t{id_}", "type": "text",
        "x": x + w//2, "y": y + h//2,
        "width": w, "height": 20,
        "angle": 0, "strokeColor": "#1e1e1e",
        "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1,
        "roughness": 1, "opacity": 100,
        "text": label, "fontSize": 14,
        "fontFamily": 1, "textAlign": "center",
        "verticalAlign": "middle",
        "containerId": id_,
    }


def _arrow(id_, x1, y1, x2, y2, label=""):
    el = {
        "id": id_, "type": "arrow",
        "x": x1, "y": y1,
        "width": abs(x2-x1), "height": abs(y2-y1),
        "angle": 0, "strokeColor": "#1e1e1e",
        "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 2,
        "roughness": 1, "opacity": 100,
        "points": [[0, 0], [x2-x1, y2-y1]],
        "lastCommittedPoint": None,
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": "arrow",
    }
    return [el]


def run_create_flowchart(params):
    name  = params["name"]
    steps = params["steps"]   # list of strings
    title = params.get("title", name)

    elements = []
    x, y, w, h, gap = 300, 80, 200, 60, 40

    for i, step in enumerate(steps):
        rid = f"r{i}"
        rect, text = _rect(rid, x, y + i*(h+gap), w, h, step)
        elements.extend([rect, text])
        if i > 0:
            elements.extend(_arrow(f"a{i}", x+w//2, y+(i-1)*(h+gap)+h,
                                            x+w//2, y+i*(h+gap)))

    data = _base_file(elements)
    path = DIAGRAMS_DIR / f"{name}.excalidraw"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"Flowchart '{title}' created with {len(steps)} steps.\nSaved: {path}"


def run_create_mindmap(params):
    name     = params["name"]
    center   = params["center"]
    branches = params["branches"]   # list of {label, children: [str]}

    elements = []
    cx, cy = 500, 400
    w, h   = 160, 50

    # Center node
    rect, text = _rect("center", cx - w//2, cy - h//2, w, h,
                        center, bg="#fff3bf", stroke="#e67700")
    elements.extend([rect, text])

    angle_step = 360 / max(len(branches), 1)
    import math
    for i, branch in enumerate(branches):
        angle = math.radians(i * angle_step)
        bx = cx + int(250 * math.cos(angle)) - w//2
        by = cy + int(200 * math.sin(angle)) - h//2
        bid = f"b{i}"
        rect, text = _rect(bid, bx, by, w, h, branch["label"],
                            bg="#d3f9d8", stroke="#2f9e44")
        elements.extend([rect, text])
        elements.extend(_arrow(f"ba{i}", cx, cy, bx + w//2, by + h//2))

        for j, child in enumerate(branch.get("children", [])):
            ca = math.radians(i * angle_step + (j - 1) * 20)
            cx2 = bx + w//2 + int(180 * math.cos(ca)) - w//2
            cy2 = by + h//2 + int(150 * math.sin(ca)) - h//2
            cid = f"c{i}_{j}"
            rect2, text2 = _rect(cid, cx2, cy2, w, h, child,
                                  bg="#e7f5ff", stroke="#1971c2")
            elements.extend([rect2, text2])
            elements.extend(_arrow(f"ca{i}_{j}", bx+w//2, by+h//2, cx2+w//2, cy2+h//2))

    data = _base_file(elements)
    path = DIAGRAMS_DIR / f"{name}.excalidraw"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"Mind map '{center}' created.\nSaved: {path}"


def run_open_diagram(params):
    name = params["name"]
    path = DIAGRAMS_DIR / f"{name}.excalidraw"
    if not path.exists():
        # Search
        matches = list(DIAGRAMS_DIR.glob(f"*{name}*.excalidraw"))
        if not matches:
            return f"No diagram named '{name}' found in {DIAGRAMS_DIR}."
        path = matches[0]
    # Open in browser via excalidraw.com or local file
    webbrowser.open(f"https://excalidraw.com#{path.as_uri()}")
    return f"Opening {path.name} in browser.\nNote: Drag the file onto excalidraw.com to load it."


def run_list_diagrams(params):
    diagrams = sorted(DIAGRAMS_DIR.glob("*.excalidraw"))
    if not diagrams:
        return f"No diagrams found in {DIAGRAMS_DIR}."
    lines = [f"Diagrams ({len(diagrams)} total):\n"]
    for d in diagrams:
        size = d.stat().st_size
        lines.append(f"  {d.stem:<40} ({size} bytes)")
    return "\n".join(lines)


def run_create_blank(params):
    name = params["name"]
    data = _base_file()
    path = DIAGRAMS_DIR / f"{name}.excalidraw"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"Blank diagram created: {path}\nOpen it at https://excalidraw.com by dragging the file."


TOOLS = [
    ({"name": "excalidraw_flowchart",
      "description": "Create a vertical flowchart diagram with a sequence of steps.",
      "input_schema": {"type": "object", "properties": {
          "name":  {"type": "string", "description": "File name (no extension)"},
          "title": {"type": "string"},
          "steps": {"type": "array", "items": {"type": "string"},
                    "description": "List of step labels in order"},
      }, "required": ["name", "steps"]}}, run_create_flowchart),

    ({"name": "excalidraw_mindmap",
      "description": "Create a mind map diagram with a center node and branches.",
      "input_schema": {"type": "object", "properties": {
          "name":     {"type": "string"},
          "center":   {"type": "string", "description": "Central topic"},
          "branches": {"type": "array", "description": "List of {label, children:[str]} objects"},
      }, "required": ["name", "center", "branches"]}}, run_create_mindmap),

    ({"name": "excalidraw_open",
      "description": "Open an Excalidraw diagram in the browser.",
      "input_schema": {"type": "object", "properties": {
          "name": {"type": "string", "description": "Diagram name"}
      }, "required": ["name"]}}, run_open_diagram),

    ({"name": "excalidraw_list",
      "description": "List all saved Excalidraw diagrams.",
      "input_schema": {"type": "object", "properties": {}}}, run_list_diagrams),

    ({"name": "excalidraw_blank",
      "description": "Create a blank Excalidraw file ready for manual editing.",
      "input_schema": {"type": "object", "properties": {
          "name": {"type": "string"}
      }, "required": ["name"]}}, run_create_blank),
]
