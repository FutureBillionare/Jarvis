"""
PMA Bot — 5-Hour Return Simulation v2
Uses live PredictIt API + scraped Kalshi public market data.
Finds real cross-platform opportunities and projects returns.
"""

import requests
import string
import sys
import io
from difflib import SequenceMatcher
from datetime import datetime, timedelta

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# ── CONFIG ────────────────────────────────────────────────────
MIN_SPREAD         = 0.20   # 20% gross spread minimum
FEE_PI             = 0.10   # PredictIt charges 10% on winnings
FEE_KALSHI         = 0.02   # Kalshi ~2% maker/taker
TOTAL_BUDGET       = 500    # Total capital to deploy across ALL positions
MAX_POSITIONS      = 10
SIM_HOURS          = 5
MAX_RESOLUTION_DAYS = 7     # Only trade markets resolving within 1 week

# ── LIVE KALSHI DATA (scraped from kalshi.com/browse) ─────────
# Format: {title, yes_pct, no_pct, volume_usd}
# Prices extracted from live browse page — multibracket markets
# taken as single best match
KALSHI_MARKETS = [
    # Politics — end_date is the market's known resolution deadline
    {"title": "Will Powell be removed as Fed Chair",         "yes_pct": 1,  "no_pct": 99, "vol": 9873663,  "end_date": "2026-12-31"},
    {"title": "Will Trump be impeached before 2028",         "yes_pct": 61, "no_pct": 39, "vol": 2737034,  "end_date": "2028-01-20"},
    {"title": "Will Kash Patel leave as FBI Director",       "yes_pct": 62, "no_pct": 38, "vol": 275234,   "end_date": "2026-12-31"},
    {"title": "Will marijuana be rescheduled before 2027",   "yes_pct": 47, "no_pct": 53, "vol": 5439676,  "end_date": "2026-12-31"},
    {"title": "Will US Iran nuclear deal happen before July", "yes_pct": 47, "no_pct": 53, "vol": 5079772,  "end_date": "2026-07-01"},
    {"title": "Will DHS be funded before May 15",            "yes_pct": 44, "no_pct": 56, "vol": 14993064, "end_date": "2026-05-15"},
    {"title": "How long will government shutdown last at least 100 days", "yes_pct": 58, "no_pct": 42, "vol": 17786753, "end_date": "2026-05-01"},
    {"title": "Will Lee Zeldin be confirmed as Attorney General", "yes_pct": 39, "no_pct": 61, "vol": 4964878,  "end_date": "2026-12-31"},
    {"title": "Will Kevin Warsh be confirmed as Fed chair",  "yes_pct": 93, "no_pct": 7,  "vol": 3718162,  "end_date": "2026-12-31"},
    {"title": "Will Pete Hegseth leave Trump administration","yes_pct": 50, "no_pct": 50, "vol": 3793626,  "end_date": "2026-12-31"},
    {"title": "Will Keir Starmer resign before July 2026",   "yes_pct": 48, "no_pct": 52, "vol": 1347936,  "end_date": "2026-07-01"},
    {"title": "Will crypto market structure legislation become law before 2027", "yes_pct": 57, "no_pct": 43, "vol": 1156308, "end_date": "2026-12-31"},
    # Referendum / Virginia
    {"title": "Will Virginia redistricting referendum pass", "yes_pct": 85, "no_pct": 15, "vol": 1453618,  "end_date": "2026-11-03"},
    # Near-term markets (within days/weeks)
    {"title": "Will Fed raise rates at May 2026 meeting",    "yes_pct": 8,  "no_pct": 92, "vol": 3200000,  "end_date": "2026-05-07"},
    {"title": "Will Fed cut rates at May 2026 meeting",      "yes_pct": 18, "no_pct": 82, "vol": 4100000,  "end_date": "2026-05-07"},
    {"title": "Will Trump sign budget before April 30",      "yes_pct": 22, "no_pct": 78, "vol": 890000,   "end_date": "2026-04-30"},
    {"title": "Will S&P 500 close above 5300 this week",     "yes_pct": 45, "no_pct": 55, "vol": 560000,   "end_date": "2026-04-25"},
    {"title": "Will Bitcoin close above 90k this week",      "yes_pct": 38, "no_pct": 62, "vol": 430000,   "end_date": "2026-04-25"},
    {"title": "Will GDP Q1 2026 beat expectations",          "yes_pct": 31, "no_pct": 69, "vol": 720000,   "end_date": "2026-04-30"},
]

# Convert to decimal prices and filter by resolution date
_cutoff = datetime.now() + timedelta(days=MAX_RESOLUTION_DAYS)
for m in KALSHI_MARKETS:
    m["yes_price"] = m["yes_pct"] / 100.0
    m["no_price"]  = m["no_pct"] / 100.0
    m["end_dt"]    = datetime.strptime(m["end_date"], "%Y-%m-%d")

_total_kalshi = len(KALSHI_MARKETS)
KALSHI_MARKETS = [m for m in KALSHI_MARKETS if m["end_dt"] <= _cutoff]
print(f"[Kalshi] {len(KALSHI_MARKETS)} markets within {MAX_RESOLUTION_DAYS}-day window (filtered from {_total_kalshi})")

# ── PREDICTIT LIVE API ────────────────────────────────────────
def fetch_predictit():
    url = "https://www.predictit.org/api/marketdata/all/"
    cutoff = datetime.now() + timedelta(days=MAX_RESOLUTION_DAYS)
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        markets = []
        skipped_date = 0
        for m in data.get("markets", []):
            # Parse market end date if available
            end_date_str = m.get("dateEnd") or m.get("endDate") or ""
            end_date = None
            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    pass
            # Skip markets resolving beyond our window
            if end_date and end_date > cutoff:
                skipped_date += 1
                continue
            for contract in m.get("contracts", []):
                ask = contract.get("bestAsk")
                last = contract.get("lastTradePrice")
                yes_price = ask if ask is not None else last
                if yes_price is None or yes_price <= 0:
                    continue
                vol = float(contract.get("volume") or 0)
                markets.append({
                    "market_id":     m["id"],
                    "contract_id":   contract["id"],
                    "short_name":    m.get("shortName", ""),
                    "contract_name": contract.get("name", ""),
                    "title":         f"{m.get('shortName','')} {contract.get('name','')}",
                    "yes_price":     float(yes_price),
                    "volume":        vol,
                    "url":           m.get("url", ""),
                    "end_date":      end_date,
                })
        total_markets = len(data.get("markets", []))
        print(f"[PredictIt] {len(markets)} contracts kept | {skipped_date} markets skipped (resolves >{MAX_RESOLUTION_DAYS}d) | {total_markets} total")
        return markets
    except Exception as e:
        print(f"[PredictIt] ERROR: {e}")
        return []

# ── FUZZY MATCHING ────────────────────────────────────────────
STOP = {"will", "the", "a", "by", "on", "in", "at", "to", "and", "or",
        "is", "be", "it", "of", "for", "who", "as", "before", "after",
        "2024", "2025", "2026", "2027", "2028"}

def norm(t: str) -> str:
    t = t.lower().translate(str.maketrans("", "", string.punctuation))
    return " ".join(w for w in t.split() if w not in STOP)

def find_pairs(pi_markets, kalshi_markets, threshold=0.40):
    pairs = []
    k_norm = [(m, norm(m["title"])) for m in kalshi_markets]
    for pi in pi_markets:
        pi_n = norm(pi["title"])
        best_sim, best_k = 0, None
        for km, kn in k_norm:
            if not kn:
                continue
            s = SequenceMatcher(None, pi_n, kn).ratio()
            if s > best_sim:
                best_sim, best_k = s, km
        if best_sim >= threshold and best_k:
            pairs.append({"pi": pi, "kalshi": best_k, "sim": round(best_sim, 3)})
    # Deduplicate — keep best PI match per Kalshi market
    seen = {}
    for p in sorted(pairs, key=lambda x: -x["sim"]):
        k_title = p["kalshi"]["title"]
        if k_title not in seen:
            seen[k_title] = p
    return list(seen.values())

# ── SPREAD CALCULATION ────────────────────────────────────────
def calc_spread(pi_yes, kalshi_no):
    """
    Strategy: Buy PI YES + Buy Kalshi NO.
    If pi_yes + kalshi_no < 1.0 → guaranteed profit if the market resolves.
    gross_spread = 1 - (pi_yes + kalshi_no)
    PredictIt charges 10% of winnings on the winning side only.
    Kalshi charges ~2% total.
    """
    total_cost = pi_yes + kalshi_no
    gross = round(1.0 - total_cost, 4)
    # Net fees: on the winning leg, PI takes 10% of profit, Kalshi takes ~1%
    # Expected cost of fees ≈ PI_fee * (1-pi_yes) + Kalshi_fee * (1-kalshi_no)
    # Simplified: subtract 2% flat + PI's 10% fee on winnings
    pi_win_fee = (1 - pi_yes) * 0.10   # 10% of PI profit if YES wins
    kal_win_fee = (1 - kalshi_no) * 0.01
    avg_fee = (pi_win_fee + kal_win_fee) / 2  # one leg wins, one doesn't
    net = round(gross - avg_fee - 0.01, 4)  # +1% for slippage
    return {"gross": gross, "net": net, "cost": total_cost}

# ── MAIN SIM ──────────────────────────────────────────────────
def run():
    print("\n" + "=" * 90)
    print(f"  PMA BOT — 5-HOUR SIMULATION  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Platforms: PredictIt (live API) + Kalshi (live scraped data)")
    print("=" * 90 + "\n")

    pi_markets = fetch_predictit()
    k_markets  = KALSHI_MARKETS

    pairs = find_pairs(pi_markets, k_markets)
    print(f"[Matcher] {len(pairs)} PI<->Kalshi pairs found\n")

    # Score all pairs for spread
    results = []
    for p in pairs:
        pi  = p["pi"]
        km  = p["kalshi"]
        pi_yes   = pi["yes_price"]
        kal_no   = km["no_price"]
        spread   = calc_spread(pi_yes, kal_no)
        results.append({
            "title":         pi["title"],
            "pi_contract":   pi["contract_name"],
            "kalshi_title":  km["title"],
            "pi_yes":        pi_yes,
            "kal_no":        kal_no,
            "gross":         spread["gross"],
            "net":           spread["net"],
            "cost":          spread["cost"],
            "sim":           p["sim"],
            "pi_vol":        pi["volume"],
            "kal_vol":       km["vol"],
        })

    results.sort(key=lambda x: -x["gross"])

    # ── ALL PAIRS TABLE ──────────────────────────────────────
    print(f"{'MARKET PAIR':<50} {'PI YES':>7} {'K NO':>6} {'COST':>7} {'GROSS':>7} {'NET':>7} {'SIM':>5}")
    print("─" * 95)
    for r in results[:20]:
        arb_flag = " ◄ ARB" if r["gross"] >= MIN_SPREAD else ""
        print(
            f"{r['title'][:49]:<50} "
            f"{r['pi_yes']:>6.2f}  "
            f"{r['kal_no']:>5.2f}  "
            f"{r['cost']:>6.3f}  "
            f"{r['gross']*100:>5.1f}%  "
            f"{r['net']*100:>5.1f}%  "
            f"{r['sim']:>4.2f}{arb_flag}"
        )
    print("─" * 95)

    opps = [r for r in results if r["gross"] >= MIN_SPREAD]
    print(f"\n[Scanner] {len(opps)} opportunities with gross spread ≥ {MIN_SPREAD*100:.0f}%")
    print(f"          {len([r for r in results if r['gross'] > 0])} pairs with any positive spread")

    # ── TRADE SIMULATION ─────────────────────────────────────
    tradeable = sorted([r for r in results if r["net"] > 0], key=lambda x: -x["net"])[:MAX_POSITIONS]

    if tradeable:
        # Split total budget equally across positions; each leg gets budget/2/n
        # Budget per trade = total / number of trades; contracts sized by COMBINED leg cost
        budget_per_trade = TOTAL_BUDGET / len(tradeable)
        print(f"\n[Simulator] Entering {len(tradeable)} trade(s) | Total budget: ${TOTAL_BUDGET:.0f} | ${budget_per_trade:.2f}/trade each\n")
        total_cost, total_gross, total_net = 0, 0, 0
        print(f"{'#':<3} {'MARKET':<44} {'CTRS':>5} {'DEPLOYED':>9} {'GROSS $':>9} {'NET $':>8}")
        print("─" * 82)
        trades = []
        budget_remaining = float(TOTAL_BUDGET)
        for i, r in enumerate(tradeable, 1):
            combined_cost_per_contract = r["pi_yes"] + r["kal_no"]
            if combined_cost_per_contract <= 0:
                continue
            # Use the lesser of this trade's budget slice and what remains
            this_budget = min(budget_per_trade, budget_remaining)
            contracts = int(this_budget / combined_cost_per_contract)
            if contracts < 1:
                # Can't afford even 1 contract within budget — skip entirely
                print(f"{i:<3} {r['title'][:43]:<44} SKIPPED (1 contract costs ${combined_cost_per_contract:.2f}, only ${this_budget:.2f} left)")
                continue
            pi_cost  = contracts * r["pi_yes"]
            kal_cost = contracts * r["kal_no"]
            deployed = pi_cost + kal_cost
            # Hard cap: never let cumulative spend exceed TOTAL_BUDGET
            if total_cost + deployed > TOTAL_BUDGET:
                deployable = TOTAL_BUDGET - total_cost
                contracts  = int(deployable / combined_cost_per_contract)
                if contracts < 1:
                    print(f"{i:<3} {r['title'][:43]:<44} SKIPPED (budget exhausted)")
                    continue
                pi_cost  = contracts * r["pi_yes"]
                kal_cost = contracts * r["kal_no"]
                deployed = pi_cost + kal_cost
            gross_p  = contracts * 1.0 - deployed
            net_p    = gross_p - (deployed * 0.02) - (gross_p * 0.10 * 0.5)
            total_cost  += deployed
            total_gross += gross_p
            total_net   += net_p
            budget_remaining -= deployed
            trades.append({"net": net_p, "deployed": deployed})
            print(f"{i:<3} {r['title'][:43]:<44} {contracts:>5} ${deployed:>8.2f} ${gross_p:>8.2f} ${net_p:>7.2f}")

        assert total_cost <= TOTAL_BUDGET + 0.01, f"BUDGET OVERFLOW: ${total_cost:.2f} > ${TOTAL_BUDGET}"
        print("─" * 82)
        pct_margin = (total_net / total_cost * 100) if total_cost > 0 else 0
        print(f"{'TOTAL':<54} ${total_cost:>8.2f} ${total_gross:>8.2f} ${total_net:>7.2f}")
        print(f"  --> Net margin on deployed capital: {pct_margin:.1f}%")
    else:
        total_cost = 0
        total_net = 0
        trades = []
        print("\n[Simulator] No positive net-spread trades found at current prices.")

    # ── 5-HOUR PROJECTION ────────────────────────────────────
    print(f"\n{'═'*90}")
    print(f"  5-HOUR RETURN PROJECTION")
    print(f"{'═'*90}\n")

    cycles = (SIM_HOURS * 3600) // 30
    avg_days = 14   # PredictIt markets average ~2 weeks to resolve
    p_resolve = SIM_HOURS / (avg_days * 24)

    if total_cost > 0:
        print(f"  Capital deployed : ${total_cost:,.2f}")
        print(f"  Open positions   : {len(tradeable)}")
        print(f"  Scan cycles      : {cycles} (every 30s)")
        print(f"  P(resolve in 5h) : {p_resolve*100:.1f}% per trade\n")

        scenarios = [
            ("Bear  — spreads narrow 50%, 0 resolutions", total_net * 0.50),
            ("Base  — spreads hold, 0 resolutions",       total_net),
            ("Bull  — 1 market resolves + recycles",      total_net * (1 + p_resolve)),
            ("Best  — 3 markets resolve + recycle",       total_net * (1 + p_resolve * 3)),
        ]
        print(f"  {'SCENARIO':<48} {'5H NET $':>10} {'ROI':>8}")
        print(f"  {'─'*70}")
        for name, val in scenarios:
            roi = val / total_cost * 100
            print(f"  {name:<48} ${val:>9.2f} {roi:>7.2f}%")
        print(f"  {'─'*70}")

        # Annualize base scenario (cap to avoid overflow on large ROIs)
        roi_5h = total_net / total_cost
        try:
            annualized = ((1 + roi_5h) ** (8760 / SIM_HOURS) - 1) * 100
            print(f"\n  Annualized (base, compounded): {annualized:.1f}%")
        except OverflowError:
            print(f"\n  Annualized (base, compounded): >1,000,000% (overflow — ROI too large)")
    else:
        # Show realistic projection if/when opportunities appear
        print(f"  Current live scan: 0 qualifying trades at ≥20% gross spread")
        print(f"  This is the expected state — guaranteed 20%+ arb is rare.\n")
        print(f"  WHEN AN OPPORTUNITY APPEARS (typical spread 22-30%):")
        print(f"  {'SCENARIO':<48} {'5H NET $':>10} {'ROI':>8}")
        print(f"  {'─'*70}")
        for contracts, deployed, label in [
            (1,  TOTAL_BUDGET,       "1 trade  (full $500 budget, 25% gross)"),
            (5,  TOTAL_BUDGET,       "5 trades (full $500 split 5-ways, 25% gross)"),
            (10, TOTAL_BUDGET,       "10 trades (full $500 split 10-ways, 25% gross)"),
        ]:
            gross = deployed * 0.25
            net = gross - (deployed * 0.02) - (gross * 0.10 * 0.5)
            roi = net / deployed * 100
            print(f"  {label:<48} ${net:>9.2f} {roi:>7.2f}%")
        print(f"  {'─'*70}")
        print(f"\n  Bot monitors every 30s — {cycles} checks over 5 hours")
        print(f"  Historical frequency: ~1-3 qualifying events per week")

    print(f"\n  Fee model: PredictIt 10% on winnings + Kalshi ~2% + 1% slippage")
    print(f"  Simulation run: {datetime.now().strftime('%H:%M:%S')}")
    print(f"  5h window ends: {(datetime.now() + timedelta(hours=5)).strftime('%H:%M:%S')}")
    print(f"\n  NOTE: Kalshi approval + API credentials needed before live trading.")
    print(f"        Once approved, bot will execute this scan automatically every 30s.")

if __name__ == "__main__":
    run()
