"""
Alcohol Getter Popup Server — FastAPI backend, port 8878.

GET  /        → dynamically generated HTML popup
GET  /data    → JSON location + places data
GET  /status  → health check
"""

import json
import logging
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

log = logging.getLogger(__name__)

_PORT = 8878

app = FastAPI(title="HUBERT Alcohol Getter")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# Cache results after first fetch so reopening doesn't re-query
_cache: dict | None = None
_lock = threading.Lock()


def _fetch_data() -> dict:
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        import sys, os
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from alcohol_workflow.locator import get_location, query_nearby
        loc = get_location()
        bars, stores = query_nearby(loc["lat"], loc["lng"])
        _cache = {"location": loc, "bars": bars, "stores": stores}
        return _cache


# ── HTML Template ──────────────────────────────────────────────────────────────

def _badge_color(alcohol_type: str) -> str:
    t = alcohol_type.lower()
    if "beer" in t or "draft" in t or "lager" in t or "ale" in t:  return "#c9820a"
    if "wine" in t:      return "#7b2d8b"
    if "cider" in t:     return "#3a7d44"
    if "spirit" in t or "liquor" in t or "whiskey" in t or "bourbon" in t: return "#c0392b"
    if "cocktail" in t:  return "#1a6e9a"
    return "#555"


def _place_card(place: dict, index: int) -> str:
    badges = "".join(
        f'<span class="badge" style="background:{_badge_color(t)}">{t}</span>'
        for t in place["alcohol_types"]
    )
    dist   = f"{place['distance_mi']} mi"
    addr   = place["address"]
    cat    = place["category"]
    return f"""
<div class="card" style="animation-delay:{index * 0.07:.2f}s">
  <div class="card-header">
    <span class="category-chip">{cat}</span>
    <span class="distance">{dist}</span>
  </div>
  <div class="place-name">{place['name']}</div>
  <div class="place-address">{addr}</div>
  <div class="badges">{badges}</div>
  <a class="directions-btn" href="{place['maps_url']}" target="_blank">Directions</a>
</div>
"""


def _generate_html(data: dict) -> str:
    loc    = data["location"]
    bars   = data["bars"]
    stores = data["stores"]
    city   = loc.get("city", "") + (f", {loc['region']}" if loc.get("region") else "")

    bar_cards   = "".join(_place_card(p, i) for i, p in enumerate(bars))
    store_cards = "".join(_place_card(p, i) for i, p in enumerate(stores))

    if not bar_cards:
        bar_cards = '<div class="empty-state">No bars found nearby. Try venturing further.</div>'
    if not store_cards:
        store_cards = '<div class="empty-state">No stores found nearby.</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HUBERT — Alcohol Getter</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:ital,wght@1,400;1,500&display=swap');

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg:          #0a0a0c;
    --surface:     #131317;
    --surface2:    #1c1c22;
    --border:      #2a2a32;
    --gold:        #c9a227;
    --gold-light:  #e8c55a;
    --text:        #e8e8ee;
    --text-dim:    #888899;
    --accent-bar:  #c9820a;
    --accent-store:#1a6e9a;
    --satisfied:   #2a7a2a;
    --satisfied-h: #3a9a3a;
    --radius:      12px;
  }}

  html, body {{
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.5;
  }}

  body {{
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    padding: 0 0 80px;
  }}

  /* ── Header ── */
  .header {{
    background: linear-gradient(135deg, #0f0f14 0%, #1a1610 100%);
    border-bottom: 1px solid #2a2418;
    padding: 28px 40px 22px;
    text-align: center;
    position: relative;
  }}

  .hubert-badge {{
    position: absolute;
    top: 18px;
    left: 24px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.15em;
    color: var(--gold);
    opacity: 0.7;
    text-transform: uppercase;
  }}

  .quote {{
    font-family: 'Playfair Display', Georgia, serif;
    font-style: italic;
    font-size: 19px;
    color: var(--gold-light);
    max-width: 680px;
    margin: 0 auto 6px;
    line-height: 1.6;
  }}

  .quote-attr {{
    font-size: 14px;
    color: var(--text-dim);
    letter-spacing: 0.05em;
  }}

  .location-line {{
    margin-top: 14px;
    font-size: 12px;
    color: var(--text-dim);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }}

  .location-dot {{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--gold);
    display: inline-block;
    animation: pulse 2s infinite;
  }}

  @keyframes pulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50%       {{ opacity: 0.4; transform: scale(0.7); }}
  }}

  /* ── Column Labels ── */
  .columns-wrapper {{
    flex: 1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
    padding: 0;
    overflow: hidden;
  }}

  .column {{
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}

  .column-left  {{ border-right: 1px solid var(--border); }}

  .column-label {{
    padding: 16px 28px 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--bg);
  }}

  .column-label-stores {{ color: var(--accent-store); }}
  .column-label-bars   {{ color: var(--accent-bar);   }}

  .label-dot {{
    width: 8px; height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }}
  .dot-store {{ background: var(--accent-store); }}
  .dot-bar   {{ background: var(--accent-bar);   }}

  .column-scroll {{
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }}

  /* ── Cards ── */
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    transition: border-color 0.2s, transform 0.15s;
    animation: slideUp 0.35s ease both;
  }}

  .card:hover {{
    border-color: var(--gold);
    transform: translateY(-2px);
  }}

  @keyframes slideUp {{
    from {{ opacity: 0; transform: translateY(14px); }}
    to   {{ opacity: 1; transform: translateY(0);    }}
  }}

  .card-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}

  .category-chip {{
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-dim);
    background: var(--surface2);
    border: 1px solid var(--border);
    padding: 2px 8px;
    border-radius: 4px;
  }}

  .distance {{
    font-size: 12px;
    color: var(--gold);
    font-weight: 600;
  }}

  .place-name {{
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    line-height: 1.3;
  }}

  .place-address {{
    font-size: 12px;
    color: var(--text-dim);
  }}

  .badges {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }}

  .badge {{
    font-size: 10px;
    font-weight: 600;
    padding: 3px 9px;
    border-radius: 20px;
    color: #fff;
    opacity: 0.92;
    letter-spacing: 0.03em;
  }}

  .directions-btn {{
    display: inline-block;
    margin-top: 4px;
    padding: 7px 16px;
    background: transparent;
    border: 1px solid var(--gold);
    border-radius: 6px;
    color: var(--gold);
    text-decoration: none;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    transition: background 0.2s, color 0.2s;
    align-self: flex-start;
  }}

  .directions-btn:hover {{
    background: var(--gold);
    color: #000;
  }}

  .empty-state {{
    color: var(--text-dim);
    font-size: 13px;
    text-align: center;
    padding: 40px 20px;
    font-style: italic;
  }}

  /* ── Satisfied Button ── */
  .satisfied-bar {{
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: linear-gradient(to top, #0a0a0c 70%, transparent);
    padding: 16px 0 20px;
    display: flex;
    justify-content: center;
    z-index: 100;
  }}

  .satisfied-btn {{
    background: var(--satisfied);
    color: #fff;
    border: none;
    border-radius: 30px;
    padding: 13px 52px;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.06em;
    cursor: pointer;
    transition: background 0.2s, transform 0.15s, box-shadow 0.2s;
    box-shadow: 0 4px 20px rgba(42, 122, 42, 0.4);
  }}

  .satisfied-btn:hover {{
    background: var(--satisfied-h);
    transform: scale(1.04);
    box-shadow: 0 6px 28px rgba(42, 122, 42, 0.6);
  }}

  .satisfied-btn:active {{
    transform: scale(0.98);
  }}

  /* Scrollbar styling */
  .column-scroll::-webkit-scrollbar {{ width: 4px; }}
  .column-scroll::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 2px; }}
</style>
</head>
<body>

<div class="header">
  <div class="hubert-badge">HUBERT</div>
  <div class="quote">"In wine there is wisdom, in beer there is freedom, in water there is bacteria."</div>
  <div class="quote-attr">— Benjamin Franklin</div>
  <div class="location-line">
    <span class="location-dot"></span>
    <span>Located near <strong>{city}</strong></span>
  </div>
</div>

<div class="columns-wrapper">

  <!-- Left: Stores -->
  <div class="column column-left">
    <div class="column-label column-label-stores">
      <span class="label-dot dot-store"></span>
      Nearby Stores &amp; Gas Stations
    </div>
    <div class="column-scroll">
      {store_cards}
    </div>
  </div>

  <!-- Right: Bars -->
  <div class="column column-right">
    <div class="column-label column-label-bars">
      <span class="label-dot dot-bar"></span>
      5 Nearest Bars
    </div>
    <div class="column-scroll">
      {bar_cards}
    </div>
  </div>

</div>

<div class="satisfied-bar">
  <button class="satisfied-btn" id="satisfied-btn">Satisfied</button>
</div>

<script>
  document.getElementById('satisfied-btn').addEventListener('click', function() {{
    if (window.pywebview && pywebview.api && pywebview.api.close) {{
      pywebview.api.close();
    }}
  }});
</script>

</body>
</html>"""


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def serve_ui():
    try:
        data = _fetch_data()
    except Exception as e:
        log.exception("Failed to fetch alcohol data")
        return HTMLResponse(
            f"<body style='background:#0a0a0c;color:#e8e8ee;font-family:sans-serif;padding:40px'>"
            f"<h2>Failed to load data</h2><pre>{e}</pre></body>",
            status_code=500,
        )
    html = _generate_html(data)
    return HTMLResponse(html)


@app.get("/data")
def get_data():
    try:
        return JSONResponse(_fetch_data())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/status")
def status():
    return JSONResponse({"ok": True, "cached": _cache is not None})


# ── Entry Point ────────────────────────────────────────────────────────────────

def start_server(host: str = "127.0.0.1", port: int = _PORT):
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_server()
