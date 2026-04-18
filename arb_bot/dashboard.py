# ============================================================
# DASHBOARD — Lightweight stdlib HTTP server on port 8765
# Run standalone: python dashboard.py
# Or call start_dashboard() from main_bot.py
# ============================================================

import threading
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

try:
    from database import get_pnl_summary, get_recent_opportunities, get_open_trades
    from config import DRY_RUN
except ImportError:
    def get_pnl_summary(): return {}
    def get_recent_opportunities(limit=20): return []
    def get_open_trades(): return []
    DRY_RUN = True


def _row(cells: list, header=False) -> str:
    tag = "th" if header else "td"
    return "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"


class DashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # suppress default access logs

    def do_GET(self):
        if self.path != "/":
            self.send_response(404); self.end_headers(); return

        pnl     = get_pnl_summary() or {}
        opps    = get_recent_opportunities(20) if callable(get_recent_opportunities) else get_recent_opportunities()
        trades  = get_open_trades()

        mode    = "🟡 DRY RUN" if DRY_RUN else "🔴 LIVE"
        now     = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # PnL rows
        pnl_body = _row(["Total Trades", pnl.get("total_trades", 0)]) + \
                   _row(["Resolved",     pnl.get("resolved", 0)]) + \
                   _row(["Open Positions", pnl.get("open_positions", 0)]) + \
                   _row(["Total P&L",    f"${pnl.get('total_pnl', 0) or 0:.2f}"]) + \
                   _row(["Avg P&L / trade", f"${pnl.get('avg_pnl_per_trade', 0) or 0:.2f}"])

        # Opportunities rows
        opp_header = _row(["Detected", "Market", "Gross %", "Net %", "Action"], header=True)
        opp_body = "".join(_row([
            o.get("detected_at", "")[:16],
            o.get("market_title", "")[:50],
            f"{(o.get('gross_spread') or 0)*100:.2f}%",
            f"{(o.get('est_net_spread') or 0)*100:.2f}%",
            o.get("action", "")
        ]) for o in opps) or "<tr><td colspan='5'>No opportunities yet.</td></tr>"

        # Trades rows
        trade_header = _row(["Opened", "Market", "Legs", "Stake", "Status", "P&L"], header=True)
        trade_body = "".join(_row([
            t.get("opened_at", "")[:16],
            t.get("market_title", "")[:40],
            f"Poly {t.get('poly_leg','?')} / Kalshi {t.get('kalshi_leg','?')}",
            f"${t.get('stake_usd', 0) or 0:.2f}",
            t.get("status", ""),
            f"${t.get('pnl_usd', '') or '--'}"
        ]) for t in trades[:10]) or "<tr><td colspan='6'>No open trades.</td></tr>"

        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="30">
  <title>ARB BOT Dashboard</title>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{background:#0a0a0a;color:#e0e0e0;font-family:'Courier New',monospace;padding:24px}}
    h1{{color:#00ff88;text-align:center;font-size:2em;margin-bottom:6px;text-shadow:0 0 8px #00ff88}}
    .sub{{text-align:center;color:#555;font-size:.85em;margin-bottom:28px}}
    .mode{{display:inline-block;padding:4px 14px;border:1px solid #00ff88;border-radius:4px;color:#00ff88;margin-bottom:20px}}
    h2{{color:#00ff88;margin:28px 0 10px;border-bottom:1px solid #00ff88;padding-bottom:6px}}
    table{{width:100%;border-collapse:collapse;margin-bottom:30px;background:#111}}
    th{{background:#1a1a1a;color:#00ff88;padding:10px 14px;text-align:left;border-bottom:2px solid #00ff88}}
    td{{padding:9px 14px;border-bottom:1px solid #1e1e1e;font-size:.9em}}
    tr:hover td{{background:#1a1a1a}}
  </style>
</head>
<body>
  <h1>⚡ ARB BOT Dashboard</h1>
  <div class="sub">Last refresh: {now} — auto-refreshes every 30s</div>
  <div class="mode">{mode}</div>

  <h2>📊 P&L Summary</h2>
  <table><tbody>{pnl_body}</tbody></table>

  <h2>🔍 Recent Opportunities (last 20)</h2>
  <table>{opp_header}<tbody>{opp_body}</tbody></table>

  <h2>📈 Open / Recent Trades</h2>
  <table>{trade_header}<tbody>{trade_body}</tbody></table>
</body>
</html>"""

        encoded = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def start_dashboard(port: int = 8765):
    """Start dashboard server in a daemon thread."""
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[Dashboard] Running at http://localhost:{port}")
    return server


if __name__ == "__main__":
    print("[Dashboard] Starting standalone on http://localhost:8765 ...")
    start_dashboard()
    import time
    while True:
        time.sleep(60)
