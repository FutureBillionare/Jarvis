# ============================================================
# PREDICTION MARKET ARBITRAGE BOT — CONFIG
# Edit this file to plug in your credentials and preferences
# ============================================================

import os

# ─── POLYMARKET ──────────────────────────────────────────────
POLYMARKET_API_KEY        = os.getenv("POLYMARKET_API_KEY", "")          # L2 CLOB API Key
POLYMARKET_API_SECRET     = os.getenv("POLYMARKET_API_SECRET", "")       # L2 CLOB API Secret
POLYMARKET_API_PASSPHRASE = os.getenv("POLYMARKET_API_PASSPHRASE", "")   # L2 CLOB Passphrase
POLYMARKET_WALLET_ADDRESS = os.getenv("POLYMARKET_WALLET_ADDRESS", "")   # Your Polygon wallet
POLYMARKET_PRIVATE_KEY    = os.getenv("POLYMARKET_PRIVATE_KEY", "")      # Wallet private key (NEVER share)

# ─── KALSHI ──────────────────────────────────────────────────
KALSHI_EMAIL              = os.getenv("KALSHI_EMAIL", "")                 # Kalshi account email
KALSHI_PASSWORD           = os.getenv("KALSHI_PASSWORD", "")              # Kalshi account password
KALSHI_API_KEY            = os.getenv("KALSHI_API_KEY", "")              # Kalshi API key (from dashboard)
KALSHI_API_SECRET         = os.getenv("KALSHI_API_SECRET", "")           # Kalshi API secret

# ─── NOTIFICATIONS ───────────────────────────────────────────
TELEGRAM_BOT_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN", "")          # BotFather token
TELEGRAM_CHAT_ID          = os.getenv("TELEGRAM_CHAT_ID", "")            # Your chat ID

# ─── STRATEGY SETTINGS ───────────────────────────────────────
MIN_SPREAD                = 0.05     # Minimum gross spread to consider (5%)
TARGET_SPREAD             = 0.06     # Ideal spread to enter (6%)
MIN_LIQUIDITY_USD         = 500      # Min $ liquidity on each side
MAX_POSITION_USD          = 500      # Max $ per leg per trade
MAX_OPEN_POSITIONS        = 10       # Max simultaneous open trades
POLL_INTERVAL_SECONDS     = 30       # How often to scan for opportunities
AUTO_EXECUTE              = False    # Set True to auto-place orders (requires real API keys!)
DRY_RUN                   = True     # If True: log opportunities but don't place real trades

# ─── DATABASE (local SQLite) ─────────────────────────────────
DB_PATH                   = "arb_bot.db"

# ─── LOGGING ─────────────────────────────────────────────────
LOG_FILE                  = "arb_bot.log"
LOG_LEVEL                 = "INFO"   # DEBUG | INFO | WARNING | ERROR
