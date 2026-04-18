import requests
import logging
from typing import Dict, Any, Optional
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not configured, skipping notification")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def notify_opportunity(opp: Dict[str, Any]) -> bool:
    message = (
        f"<b>🔍 Arbitrage Opportunity Detected</b>\n\n"
        f"<b>Market:</b> {opp.get('market_title', 'N/A')}\n"
        f"<b>Gross Spread:</b> {opp.get('gross_spread', 0)*100:.2f}%\n"
        f"<b>Est. Net Spread:</b> {opp.get('est_net_spread', 0)*100:.2f}%\n\n"
        f"<b>Prices:</b>\n"
        f"  Polymarket YES: ${opp.get('poly_yes_price', 0):.4f}\n"
        f"  Kalshi NO: ${opp.get('kalshi_no_price', 0):.4f}\n\n"
        f"<b>Liquidity:</b>\n"
        f"  Polymarket: ${opp.get('poly_liquidity', 0):.2f}\n"
        f"  Kalshi: ${opp.get('kalshi_liquidity', 0):.2f}\n\n"
        f"<b>Suggested Stake:</b> ${opp.get('stake_suggestion', 0):.2f}"
    )
    return send_telegram(message)


def notify_trade_opened(trade: Dict[str, Any]) -> bool:
    message = (
        f"<b>📈 Trade Opened</b>\n\n"
        f"<b>Market:</b> {trade.get('market_title', 'N/A')}\n"
        f"<b>Poly Leg:</b> YES @ ${trade.get('poly_price', 0):.4f}\n"
        f"<b>Kalshi Leg:</b> NO @ ${trade.get('kalshi_price', 0):.4f}\n"
        f"<b>Stake:</b> ${trade.get('stake_usd', 0):.2f}"
    )
    return send_telegram(message)


def notify_trade_resolved(trade: Dict[str, Any]) -> bool:
    pnl = trade.get('pnl_usd', 0) or 0
    emoji = "✅" if pnl >= 0 else "❌"
    message = (
        f"{emoji} <b>Trade Resolved</b>\n\n"
        f"<b>Market:</b> {trade.get('market_title', 'N/A')}\n"
        f"<b>PnL:</b> ${pnl:.2f}"
    )
    return send_telegram(message)


def notify_error(context: str, error: str) -> bool:
    message = (
        f"<b>⚠️ Error Occurred</b>\n\n"
        f"<b>Context:</b> {context}\n"
        f"<b>Error:</b> <code>{error}</code>"
    )
    return send_telegram(message)
