# ============================================================
# MATCHER — Fuzzy-match Polymarket & Kalshi markets, scan arb
# ============================================================

import string
import logging
from difflib import SequenceMatcher

from polymarket_client import get_all_markets as poly_markets, get_yes_price
from kalshi_client import get_all_markets as kalshi_markets, get_no_price
from config import MIN_SPREAD, MIN_LIQUIDITY_USD, TARGET_SPREAD

logger = logging.getLogger(__name__)

STOP_WORDS = {"will", "the", "a", "by", "on", "in", "at", "to", "and", "or", "is", "be", "it", "of", "for"}


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, remove stop words."""
    title = title.lower()
    title = title.translate(str.maketrans("", "", string.punctuation))
    words = [w for w in title.split() if w not in STOP_WORDS]
    return " ".join(words)


def find_matches(poly_list: list, kalshi_list: list) -> list:
    """
    Fuzzy-match markets by title.
    Returns list of {poly_market, kalshi_market, similarity} where similarity > 0.72.
    """
    matches = []
    kalshi_normalized = [(m, normalize_title(m.get("title", "") or m.get("subtitle", ""))) for m in kalshi_list]

    for poly_market in poly_list:
        poly_norm = normalize_title(poly_market.get("question", "") or poly_market.get("title", ""))
        if not poly_norm:
            continue

        best_match = None
        best_ratio = 0.0

        for kalshi_market, k_norm in kalshi_normalized:
            if not k_norm:
                continue
            ratio = SequenceMatcher(None, poly_norm, k_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = kalshi_market

        if best_ratio > 0.72 and best_match:
            matches.append({
                "poly_market": poly_market,
                "kalshi_market": best_match,
                "similarity": round(best_ratio, 3)
            })

    logger.info(f"[Matcher] Found {len(matches)} cross-platform market pairs.")
    return matches


def calculate_spread(poly_yes_price: float, kalshi_no_price: float) -> dict:
    """
    Calculate gross and estimated net arbitrage spread.
    gross_spread = poly_yes + kalshi_no - 1  (profit if both sides pay out)
    est_net_spread = gross_spread - 2% fees
    """
    gross_spread = round((poly_yes_price + kalshi_no_price) - 1.0, 4)
    est_net_spread = round(gross_spread - 0.02, 4)
    return {
        "gross_spread": gross_spread,
        "est_net_spread": est_net_spread,
        "is_opportunity": est_net_spread >= MIN_SPREAD
    }


def scan_opportunities() -> list:
    """
    Full scan: fetch both markets, match, price check, return opportunities.
    """
    logger.info("[Matcher] Starting full market scan...")
    poly_all = poly_markets(limit=200)
    kalshi_all = kalshi_markets(limit=200)

    if not poly_all:
        logger.warning("[Matcher] Polymarket returned 0 markets.")
    if not kalshi_all:
        logger.warning("[Matcher] Kalshi returned 0 markets.")

    pairs = find_matches(poly_all, kalshi_all)
    opportunities = []

    for pair in pairs:
        pm = pair["poly_market"]
        km = pair["kalshi_market"]

        poly_yes, poly_liq = get_yes_price(pm)
        kalshi_no, kalshi_liq = get_no_price(km)

        if poly_yes is None or kalshi_no is None:
            continue
        if poly_liq < MIN_LIQUIDITY_USD or kalshi_liq < MIN_LIQUIDITY_USD:
            continue

        spread = calculate_spread(poly_yes, kalshi_no)
        if not spread["is_opportunity"]:
            continue

        title = pm.get("question") or pm.get("title") or "Unknown"
        poly_id = pm.get("condition_id") or pm.get("id") or ""
        kalshi_id = km.get("ticker") or km.get("id") or ""

        opportunities.append({
            "market_title": title,
            "poly_market_id": poly_id,
            "kalshi_market_id": kalshi_id,
            "poly_yes_price": poly_yes,
            "kalshi_no_price": kalshi_no,
            "gross_spread": spread["gross_spread"],
            "est_net_spread": spread["est_net_spread"],
            "poly_liquidity": poly_liq,
            "kalshi_liquidity": kalshi_liq,
            "similarity": pair["similarity"]
        })

    opportunities.sort(key=lambda x: x["est_net_spread"], reverse=True)
    logger.info(f"[Matcher] {len(opportunities)} actionable opportunities found.")
    return opportunities
