# ============================================================
# KALSHI CLIENT — REST API wrapper
# ============================================================

import time
import logging
import requests
from config import KALSHI_API_KEY, KALSHI_API_SECRET, KALSHI_EMAIL, KALSHI_PASSWORD

logger = logging.getLogger(__name__)

BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"

# Module-level token cache
_auth_token = None
_token_expiry = 0.0


def get_auth_token() -> str:
    """Login with email/password, cache token for 23 hours."""
    global _auth_token, _token_expiry
    if _auth_token and time.time() < _token_expiry:
        return _auth_token
    try:
        resp = requests.post(
            f"{BASE_URL}/log_in",
            json={"email": KALSHI_EMAIL, "password": KALSHI_PASSWORD},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        resp.raise_for_status()
        _auth_token = resp.json().get("token", "")
        _token_expiry = time.time() + 23 * 3600
        logger.info("[Kalshi] Auth token obtained.")
        return _auth_token
    except Exception as e:
        logger.error(f"[Kalshi] Auth failed: {e}")
        return ""


def _auth_headers() -> dict:
    token = get_auth_token()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_all_markets(limit: int = 200) -> list:
    """Fetch active markets from Kalshi."""
    try:
        resp = requests.get(
            f"{BASE_URL}/markets",
            params={"limit": limit, "status": "open"},
            headers=_auth_headers(),
            timeout=15
        )
        resp.raise_for_status()
        markets = resp.json().get("markets", [])
        logger.info(f"[Kalshi] Retrieved {len(markets)} markets.")
        return markets
    except Exception as e:
        logger.error(f"[Kalshi] get_all_markets failed: {e}")
        return []


def get_market(ticker: str) -> dict | None:
    """Fetch a single market by ticker."""
    try:
        resp = requests.get(
            f"{BASE_URL}/markets/{ticker}",
            headers=_auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("market")
    except Exception as e:
        logger.error(f"[Kalshi] get_market({ticker}) failed: {e}")
        return None


def get_no_price(market: dict) -> tuple[float | None, float]:
    """
    Extract best NO ask price and liquidity.
    yes_bid is in cents (0-100), so no_ask = 1 - (yes_bid / 100).
    Returns (no_ask_price, liquidity_usd).
    """
    try:
        yes_bid_cents = market.get("yes_bid", 0)
        yes_bid = yes_bid_cents / 100.0
        no_ask = round(1.0 - yes_bid, 4)
        liquidity = float(market.get("liquidity", 0) or market.get("volume", 0))
        return no_ask, liquidity
    except Exception as e:
        logger.error(f"[Kalshi] get_no_price error: {e}")
        return None, 0.0


def place_order(ticker: str, side: str, count: int, price: float, dry_run: bool = True) -> dict | None:
    """
    Place a limit order on Kalshi.
    side: 'yes' or 'no'
    count: number of contracts
    price: limit price (0-100 cents scale, pass as decimal e.g. 0.45 → 45)
    """
    price_cents = int(round(price * 100))
    if dry_run:
        logger.info(f"[Kalshi DRY RUN] {side.upper()} {count} contracts @ {price_cents}¢ on {ticker}")
        return {"order_id": f"DRY_KALSHI_{ticker[:8]}", "status": "dry_run"}

    if not KALSHI_API_KEY:
        logger.error("[Kalshi] No API credentials — cannot place order.")
        return None

    try:
        payload = {
            "ticker": ticker,
            "action": "buy",
            "side": side,
            "count": count,
            "type": "limit",
            "yes_price": price_cents if side == "yes" else None,
            "no_price": price_cents if side == "no" else None,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        resp = requests.post(
            f"{BASE_URL}/portfolio/orders",
            json=payload,
            headers=_auth_headers(),
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(f"[Kalshi] Order placed: {result}")
        return result
    except Exception as e:
        logger.error(f"[Kalshi] place_order failed: {e}")
        return None
