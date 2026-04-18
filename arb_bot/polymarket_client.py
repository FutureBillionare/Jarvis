# ============================================================
# POLYMARKET CLIENT — Wraps py-clob-client SDK
# ============================================================

import logging
import requests
from config import (
    POLYMARKET_API_KEY, POLYMARKET_API_SECRET, POLYMARKET_API_PASSPHRASE,
    POLYMARKET_WALLET_ADDRESS, POLYMARKET_PRIVATE_KEY
)

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = "https://clob.polymarket.com"

# ─── PUBLIC MARKET DATA (no auth needed) ─────────────────────

def get_all_markets(limit=200, offset=0):
    """Fetch active markets from Gamma API."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"limit": limit, "offset": offset, "active": "true", "closed": "false"},
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"[Polymarket] Failed to fetch markets: {e}")
        return []


def get_market_orderbook(condition_id: str):
    """Fetch best bid/ask for a market from the CLOB."""
    try:
        resp = requests.get(
            f"{CLOB_API}/book",
            params={"token_id": condition_id},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"[Polymarket] Orderbook error for {condition_id}: {e}")
        return None


def parse_best_prices(orderbook: dict):
    """Return (best_ask, best_bid, ask_liquidity, bid_liquidity) from an orderbook."""
    if not orderbook:
        return None, None, 0, 0
    try:
        asks = orderbook.get("asks", [])
        bids = orderbook.get("bids", [])
        best_ask = float(asks[0]["price"]) if asks else None
        best_bid = float(bids[0]["price"]) if bids else None
        ask_liq  = sum(float(a["size"]) for a in asks[:5])
        bid_liq  = sum(float(b["size"]) for b in bids[:5])
        return best_ask, best_bid, ask_liq, bid_liq
    except Exception as e:
        logger.error(f"[Polymarket] Price parse error: {e}")
        return None, None, 0, 0


def get_yes_price(market: dict):
    """
    Given a Gamma market object, return the current YES ask price
    and available liquidity on the YES side.
    """
    tokens = market.get("tokens", [])
    yes_token = next((t for t in tokens if t.get("outcome", "").upper() == "YES"), None)
    if not yes_token:
        return None, 0

    token_id = yes_token.get("token_id") or yes_token.get("condition_id")
    if not token_id:
        return None, 0

    ob = get_market_orderbook(token_id)
    best_ask, _, ask_liq, _ = parse_best_prices(ob)
    return best_ask, ask_liq


# ─── ORDER PLACEMENT (requires API keys) ─────────────────────

def place_order(token_id: str, side: str, price: float, size: float, dry_run=True):
    """
    Place a limit order on Polymarket CLOB.
    side: 'BUY' or 'SELL'
    dry_run: if True, just log and return fake order ID
    """
    if dry_run:
        logger.info(f"[Polymarket DRY RUN] {side} {size} shares @ {price} on token {token_id}")
        return {"order_id": f"DRY_{token_id[:8]}", "status": "dry_run"}

    if not all([POLYMARKET_API_KEY, POLYMARKET_API_SECRET, POLYMARKET_API_PASSPHRASE]):
        logger.error("[Polymarket] API credentials not configured — cannot place order.")
        return None

    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OrderArgs, OrderType

        client = ClobClient(
            host=CLOB_API,
            key=POLYMARKET_PRIVATE_KEY,
            chain_id=137,  # Polygon mainnet
            signature_type=2,
            funder=POLYMARKET_WALLET_ADDRESS
        )
        client.set_api_creds(client.create_or_derive_api_creds())

        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=side,
            order_type=OrderType.GTC
        )
        signed = client.create_order(order_args)
        result = client.post_order(signed)
        logger.info(f"[Polymarket] Order placed: {result}")
        return result

    except ImportError:
        logger.error("[Polymarket] py-clob-client not installed. Run: pip install py-clob-client")
        return None
    except Exception as e:
        logger.error(f"[Polymarket] Order placement failed: {e}")
        return None
