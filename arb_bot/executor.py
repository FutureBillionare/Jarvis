# ============================================================
# EXECUTOR — Place arb trades, resolve positions
# ============================================================

import logging

from polymarket_client import place_order as poly_place
from kalshi_client import place_order as kalshi_place
from database import log_trade, get_open_trades, resolve_trade, log_opportunity
from notifier import notify_trade_opened, notify_trade_resolved, notify_error
from config import MAX_POSITION_USD, AUTO_EXECUTE, DRY_RUN, MAX_OPEN_POSITIONS

logger = logging.getLogger(__name__)


def execute_arb(opportunity: dict) -> dict | None:
    """
    Execute a two-legged arb: buy YES on Polymarket + buy NO on Kalshi.
    Returns trade dict if entered, None if skipped.
    """
    try:
        open_trades = get_open_trades()
        if len(open_trades) >= MAX_OPEN_POSITIONS:
            logger.info(f"[Executor] Max open positions ({MAX_OPEN_POSITIONS}) reached — skipping.")
            return None

        poly_liq   = opportunity.get("poly_liquidity", 0)
        kalshi_liq = opportunity.get("kalshi_liquidity", 0)
        stake = min(MAX_POSITION_USD, poly_liq, kalshi_liq)

        if stake < 50:
            logger.info(f"[Executor] Stake too small (${stake:.2f}) — skipping.")
            return None

        poly_yes   = opportunity["poly_yes_price"]
        kalshi_no  = opportunity["kalshi_no_price"]
        poly_id    = opportunity["poly_market_id"]
        kalshi_id  = opportunity["kalshi_market_id"]
        title      = opportunity.get("market_title", "Unknown")

        # Place both legs
        poly_result   = poly_place(token_id=poly_id, side="BUY", price=poly_yes,   size=stake, dry_run=DRY_RUN)
        kalshi_result = kalshi_place(ticker=kalshi_id, side="no",  price=kalshi_no, count=int(stake), dry_run=DRY_RUN)

        poly_order_id   = (poly_result   or {}).get("order_id", "")
        kalshi_order_id = (kalshi_result or {}).get("order_id", "")

        # Log to DB
        opp_id = log_opportunity(
            market_title=title,
            poly_market_id=poly_id,
            kalshi_market_id=kalshi_id,
            poly_yes=poly_yes,
            kalshi_no=kalshi_no,
            gross_spread=opportunity["gross_spread"],
            est_net=opportunity["est_net_spread"],
            poly_liq=poly_liq,
            kalshi_liq=kalshi_liq,
            action="entered"
        )

        log_trade(
            opportunity_id=opp_id,
            market_title=title,
            poly_order_id=poly_order_id,
            kalshi_order_id=kalshi_order_id,
            poly_leg="YES",
            kalshi_leg="NO",
            poly_price=poly_yes,
            kalshi_price=kalshi_no,
            stake_usd=stake,
            gross_spread=opportunity["gross_spread"]
        )

        trade = {
            "market_title":      title,
            "poly_order_id":     poly_order_id,
            "kalshi_order_id":   kalshi_order_id,
            "poly_price":        poly_yes,
            "kalshi_price":      kalshi_no,
            "stake_usd":         stake,
            "gross_spread":      opportunity["gross_spread"],
            "est_net_spread":    opportunity["est_net_spread"],
        }
        notify_trade_opened(trade)
        logger.info(f"[Executor] Trade opened: {title} | stake=${stake:.2f}")
        return trade

    except Exception as e:
        logger.error(f"[Executor] execute_arb failed: {e}")
        notify_error("execute_arb", str(e))
        return None


def check_and_resolve_trades() -> None:
    """
    Loop open trades and resolve any that have settled.
    Resolution logic is a placeholder — extend when market APIs support it.
    """
    try:
        open_trades = get_open_trades()
        for trade in open_trades:
            trade_id = trade.get("id")
            logger.info(f"[Executor] Resolution check not yet implemented for trade #{trade_id}.")
            # TODO: call Polymarket/Kalshi to check settlement, then:
            # pnl = calculate_pnl(trade)
            # resolve_trade(trade_id, pnl)
            # notify_trade_resolved({...})
    except Exception as e:
        logger.error(f"[Executor] check_and_resolve_trades failed: {e}")
        notify_error("check_and_resolve_trades", str(e))
