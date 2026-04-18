"""
Tool: eonet
Description: NASA EONET (Earth Observatory Natural Event Tracker) — real-time
natural events: storms, wildfires, floods, earthquakes, volcanic activity, sea ice.
Free public API, no key required.
"""
import json
from datetime import datetime, timedelta

try:
    import requests
    _available = True
except ImportError:
    _available = False

BASE = "https://eonet.gsfc.nasa.gov/api/v3"

CATEGORY_NAMES = {
    "drought":            "Drought",
    "dustHaze":           "Dust & Haze",
    "earthquakes":        "Earthquakes",
    "floods":             "Floods",
    "landslides":         "Landslides",
    "manmade":            "Manmade",
    "seaLakeIce":         "Sea & Lake Ice",
    "severeStorms":       "Severe Storms",
    "snow":               "Snow",
    "tempExtremes":       "Temperature Extremes",
    "volcanoes":          "Volcanoes",
    "waterColor":         "Water Color",
    "wildfires":          "Wildfires",
}


def _get(path: str, params: dict = None) -> dict:
    r = requests.get(BASE + path, params=params or {}, timeout=15)
    r.raise_for_status()
    return r.json()


def run_events(params: dict) -> str:
    if not _available:
        return "requests not installed."
    limit      = params.get("limit", 20)
    days       = params.get("days", 7)
    category   = params.get("category", "")
    status     = params.get("status", "open")   # open | closed | all

    query = {"limit": limit, "status": status}
    if days:
        start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        query["start"] = start
    if category:
        query["category"] = category

    data   = _get("/events", query)
    events = data.get("events", [])
    if not events:
        return f"No {status} natural events found in the last {days} days."

    lines = [f"NASA EONET — {len(events)} event(s) | last {days}d | status={status}\n"]
    for ev in events:
        title    = ev.get("title", "Unknown")
        cats     = ", ".join(c["title"] for c in ev.get("categories", []))
        geometry = ev.get("geometry", [])
        date_str = geometry[0].get("date", "?")[:10] if geometry else "?"
        closed   = ev.get("closed")
        status_s = f"closed {closed[:10]}" if closed else "OPEN"
        lines.append(f"  [{status_s}]  {date_str}  {title}  ({cats})")

    return "\n".join(lines)


def run_event_detail(params: dict) -> str:
    if not _available:
        return "requests not installed."
    event_id = params["event_id"]
    ev = _get(f"/events/{event_id}")
    title    = ev.get("title", "?")
    cats     = ", ".join(c["title"] for c in ev.get("categories", []))
    src_urls = [s["url"] for s in ev.get("sources", []) if s.get("url")]
    geo      = ev.get("geometry", [])

    lines = [f"Event: {title}", f"Categories: {cats}"]
    if src_urls:
        lines.append(f"Sources: {', '.join(src_urls)}")
    lines.append(f"Geometry points: {len(geo)}")
    if geo:
        latest = geo[-1]
        lines.append(f"Latest: {latest.get('date','?')[:16]}  coords={latest.get('coordinates')}")
    return "\n".join(lines)


def run_categories(params: dict) -> str:
    if not _available:
        return "requests not installed."
    data = _get("/categories")
    cats = data.get("categories", [])
    lines = [f"EONET Categories ({len(cats)}):"]
    for c in cats:
        lines.append(f"  {c['id']:20s}  {c['title']}")
    return "\n".join(lines)


TOOL_DEFINITION_EVENTS = {
    "name": "eonet_events",
    "description": (
        "Fetch current or recent natural events from NASA EONET: wildfires, storms, "
        "floods, earthquakes, volcanoes, etc. No API key needed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "limit":    {"type": "integer", "description": "Max events to return (default 20)"},
            "days":     {"type": "integer", "description": "How many days back to look (default 7)"},
            "category": {"type": "string",  "description": "Filter by category ID e.g. wildfires, severeStorms, volcanoes"},
            "status":   {"type": "string",  "description": "open (default), closed, or all", "enum": ["open", "closed", "all"]},
        },
    },
}

TOOL_DEFINITION_DETAIL = {
    "name": "eonet_event_detail",
    "description": "Get full details of a specific EONET event by its ID.",
    "input_schema": {
        "type": "object",
        "properties": {
            "event_id": {"type": "string", "description": "EONET event ID e.g. EONET_6089"},
        },
        "required": ["event_id"],
    },
}

TOOL_DEFINITION_CATS = {
    "name": "eonet_categories",
    "description": "List all available EONET event categories.",
    "input_schema": {"type": "object", "properties": {}},
}

TOOLS = [
    (TOOL_DEFINITION_EVENTS, run_events),
    (TOOL_DEFINITION_DETAIL, run_event_detail),
    (TOOL_DEFINITION_CATS,   run_categories),
]
