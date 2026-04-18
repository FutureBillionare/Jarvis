# ============================================================
# MAIN BOT — Entry point. Run: python main_bot.py
# ============================================================

import logging
import time
import sys
import os
from datetime import datetime

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))

from database import init_db, get_pnl_summary, log_opportunity
from matcher import scan_opportunities
from executor import execute_arb, check_and_resolve_trades
from notifier import send_telegram
from config import POLL_INTERVAL_SECONDS, DRY_RUN, AUTO_EXECUTE

# ── LOGGING ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("arb_bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("arb_bot.main")

BANNER = """
+==================================================+
|          A R B   B O T   v 1 . 0               |
|     Prediction Market Arbitrage Engine          |
+==================================================+
"""


def run_scan_cycle():
    logger.info("-" * 60)
    logger.info("Starting scan cycle...")

    opportunities = scan_opportunities()

    if not opportunities:
        logger.info("No actionable opportunities this cycle.")
        return

    logger.info(f"Found {len(opportunities)} opportunities.")

    for opp in opportunities:
        log_opportunity(
            market_title=opp["market_title"],
            poly_market_id=opp["poly_market_id"],
            kalshi_market_id=opp["kalshi_market_id"],
            poly_yes=opp["poly_yes_price"],
            kalshi_no=opp["kalshi_no_price"],
            gross_spread=opp["gross_spread"],
            est_net=opp["est_net_spread"],
            poly_liq=opp["poly_liquidity"],
            kalshi_liq=opp["kalshi_liquidity"],
            action="detected"
        )

    # Print summary table
    print("\n" + "-" * 95)
    print(f"{'MARKET':<45} {'GROSS':>8} {'NET':>8} {'POLY YES':>10} {'K NO':>8} {'SIM':>6}")
    print("-" * 95)
    for opp in opportunities[:10]:
        print(
            f"{opp['market_title'][:44]:<45} "
            f"{opp['gross_spread']*100:>7.2f}% "
            f"{opp['est_net_spread']*100:>7.2f}% "
            f"{opp['poly_yes_price']:>10.4f} "
            f"{opp['kalshi_no_price']:>8.4f} "
            f"{opp['similarity']:>6.2f}"
        )
    print("-" * 95 + "\n")

    if AUTO_EXECUTE:
        top = opportunities[0]
        logger.info(f"AUTO_EXECUTE ON - entering: {top['market_title']}")
        execute_arb(top)
    else:
        logger.info("AUTO_EXECUTE is OFF - dry scan only, no orders placed.")

    check_and_resolve_trades()

    pnl = get_pnl_summary()
    logger.info(f"PnL snapshot: {pnl}")


def main():
    print(BANNER)
    mode_str = "DRY RUN" if DRY_RUN else "LIVE"
    exec_str = "AUTO EXECUTE ON" if AUTO_EXECUTE else "Observe-only"
    logger.info(f"Mode: {mode_str} | {exec_str} | Poll: {POLL_INTERVAL_SECONDS}s")

    init_db()

    startup_msg = (
        f"ARB BOT v1.0 Started\n"
        f"Mode: {mode_str}\n"
        f"Execute: {exec_str}\n"
        f"Poll interval: {POLL_INTERVAL_SECONDS}s\n"
        f"Started: {datetime.utcnow().isoformat()}Z"
    )
    send_telegram(startup_msg)

    try:
        while True:
            run_scan_cycle()
            logger.info(f"Sleeping {POLL_INTERVAL_SECONDS}s until next cycle...")
            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt - shutting down.")
        pnl = get_pnl_summary()
        send_telegram(f"ARB BOT stopped. Final PnL: {pnl}")
        print("\nBot stopped.")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        send_telegram(f"FATAL ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
