# ============================================================
# DATABASE — SQLite persistence for trades, positions, P&L
# ============================================================

import sqlite3
import json
from datetime import datetime
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # Opportunities table — every arb spread we detect
    c.execute("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_at TEXT NOT NULL,
            market_title TEXT NOT NULL,
            poly_market_id TEXT,
            kalshi_market_id TEXT,
            poly_yes_price  REAL,
            kalshi_no_price REAL,
            gross_spread    REAL,
            est_net_spread  REAL,
            poly_liquidity  REAL,
            kalshi_liquidity REAL,
            action          TEXT DEFAULT 'detected',  -- detected | skipped | entered
            notes           TEXT
        )
    """)

    # Trades table — actual positions entered
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id  INTEGER REFERENCES opportunities(id),
            opened_at       TEXT NOT NULL,
            market_title    TEXT NOT NULL,
            poly_order_id   TEXT,
            kalshi_order_id TEXT,
            poly_leg        TEXT,   -- YES or NO
            kalshi_leg      TEXT,   -- YES or NO
            poly_price      REAL,
            kalshi_price    REAL,
            stake_usd       REAL,
            gross_spread    REAL,
            status          TEXT DEFAULT 'open',  -- open | resolved | cancelled
            resolved_at     TEXT,
            pnl_usd         REAL,
            notes           TEXT
        )
    """)

    # PnL summary view
    c.execute("""
        CREATE VIEW IF NOT EXISTS pnl_summary AS
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) as resolved,
            SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) as open_positions,
            SUM(CASE WHEN pnl_usd IS NOT NULL THEN pnl_usd ELSE 0 END) as total_pnl,
            AVG(CASE WHEN pnl_usd IS NOT NULL THEN pnl_usd ELSE NULL END) as avg_pnl_per_trade
        FROM trades
    """)

    conn.commit()
    conn.close()
    print("[DB] Initialized successfully.")


def log_opportunity(market_title, poly_market_id, kalshi_market_id,
                    poly_yes, kalshi_no, gross_spread, est_net,
                    poly_liq, kalshi_liq, action="detected", notes=""):
    conn = get_conn()
    conn.execute("""
        INSERT INTO opportunities
        (detected_at, market_title, poly_market_id, kalshi_market_id,
         poly_yes_price, kalshi_no_price, gross_spread, est_net_spread,
         poly_liquidity, kalshi_liquidity, action, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (datetime.utcnow().isoformat(), market_title, poly_market_id, kalshi_market_id,
          poly_yes, kalshi_no, gross_spread, est_net, poly_liq, kalshi_liq, action, notes))
    opp_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return opp_id


def log_trade(opportunity_id, market_title, poly_order_id, kalshi_order_id,
              poly_leg, kalshi_leg, poly_price, kalshi_price, stake_usd, gross_spread, notes=""):
    conn = get_conn()
    conn.execute("""
        INSERT INTO trades
        (opportunity_id, opened_at, market_title, poly_order_id, kalshi_order_id,
         poly_leg, kalshi_leg, poly_price, kalshi_price, stake_usd, gross_spread, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (opportunity_id, datetime.utcnow().isoformat(), market_title,
          poly_order_id, kalshi_order_id, poly_leg, kalshi_leg,
          poly_price, kalshi_price, stake_usd, gross_spread, notes))
    conn.commit()
    conn.close()


def resolve_trade(trade_id, pnl_usd, notes=""):
    conn = get_conn()
    conn.execute("""
        UPDATE trades SET status='resolved', resolved_at=?, pnl_usd=?, notes=?
        WHERE id=?
    """, (datetime.utcnow().isoformat(), pnl_usd, notes, trade_id))
    conn.commit()
    conn.close()


def get_open_trades():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM trades WHERE status='open'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pnl_summary():
    conn = get_conn()
    row = conn.execute("SELECT * FROM pnl_summary").fetchone()
    conn.close()
    return dict(row) if row else {}


def get_recent_opportunities(limit=20):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM opportunities ORDER BY detected_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
