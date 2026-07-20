"""
Real two-market inefficiency check: same stock, NSE vs BSE, right now.

For every dual-listed stock in inefficiency/nse_bse_dual_listed_universe.py:
  1. Pull live last_price/volume/timestamp from BOTH exchanges (Dhan).
  2. Check the two quotes aren't stale relative to each other (the "lag" --
     if NSE and BSE ticks are too far apart in time, any price gap is
     noise, not a tradeable inefficiency, so it's skipped, not flagged).
  3. Run the survivors through OpportunityRankingEngine (existing,
     tested): round-trip cost + settlement + capital + liquidity decide
     whether the gap is actually executable.

No crypto. No commodities (gold/silver/steel physical aren't dual-listed
on NSE/BSE -- only single-exchange MCX data would show that, and we
don't have a real feed for it).

Usage: PYTHONPATH=. python scripts/check_nse_bse_inefficiencies.py
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from connectors.dhan_connector import DhanConnector
from ai.quote_freshness_validator import QuoteFreshnessValidator
from ai.live_opportunity_gate import DEFAULT_GATE_CONFIG
from inefficiency.opportunity_ranking_engine import OpportunityRankingEngine
from inefficiency.nse_bse_dual_listed_universe import DUAL_LISTED_STOCKS

MAX_LAG_SECONDS = 10.0       # quotes older apart than this = not comparable
QUANTITY = 100                # fixed paper-trade size per candidate
AVAILABLE_CAPITAL = 1_000_000


def build_candidate(symbol, nse_q, bse_q):
    if bse_q["last_price"] > nse_q["last_price"]:
        buy_market, buy_price = "NSE", nse_q["last_price"]
        sell_market, sell_price = "BSE", bse_q["last_price"]
    elif nse_q["last_price"] > bse_q["last_price"]:
        buy_market, buy_price = "BSE", bse_q["last_price"]
        sell_market, sell_price = "NSE", nse_q["last_price"]
    else:
        return None  # identical price, no edge to evaluate

    cfg = DEFAULT_GATE_CONFIG
    gross_buy_value = buy_price * QUANTITY

    def pct_cost(pct):
        return gross_buy_value * (pct / 100.0)

    return {
        "opportunity_id": f"{symbol}@{nse_q['timestamp']}",
        "opportunity_type": "arbitrage",  # real same-instrument, two-market gap
        "asset": symbol,
        "buy_market": buy_market,
        "sell_market": sell_market,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "quantity": QUANTITY,
        "buy_settlement_days": 1,   # NSE/BSE equity: T+1 both legs
        "sell_settlement_days": 1,
        "holding_period_days": 0.0,
        "annual_financing_rate_pct": cfg["annual_financing_rate_pct"],
        "buy_side_available_quantity": nse_q["volume"] or cfg["default_available_quantity"],
        "sell_side_available_quantity": bse_q["volume"] or cfg["default_available_quantity"],
        "buy_spread_pct": cfg["default_spread_pct"],
        "sell_spread_pct": cfg["default_spread_pct"],
        "max_participation_rate": cfg["max_participation_rate"],
        "slippage_pct_at_full_participation": cfg["slippage_pct_at_full_participation"],
        "min_fill_ratio": cfg["min_fill_ratio"],
        "min_annualized_return_pct": cfg["min_annualized_return_pct"],
        "buy_brokerage": pct_cost(cfg["buy_brokerage_pct"]),
        "sell_brokerage": pct_cost(cfg["sell_brokerage_pct"]),
        "buy_tax": pct_cost(cfg["buy_tax_pct"]),
        "sell_tax": pct_cost(cfg["sell_tax_pct"]),
        "handling_cost": pct_cost(cfg["latency_buffer_pct"])
    }


def check(nse_quotes, bse_quotes, universe=DUAL_LISTED_STOCKS,
          max_lag_seconds=MAX_LAG_SECONDS, ranking_engine=None):
    """
    Pure function so it can be tested without live Dhan. Returns
    {"ranked": [...], "rejected": [...], "lag_skipped": [(symbol, lag_seconds), ...]}
    """
    validator = QuoteFreshnessValidator()
    ranking_engine = ranking_engine or OpportunityRankingEngine()
    candidates = []
    lag_skipped = []

    for stock in universe:
        symbol = stock["symbol"]
        nse_q = nse_quotes.get(symbol)
        bse_q = bse_quotes.get(symbol)
        if not nse_q or not bse_q:
            continue

        ts_a = validator.parse_timestamp(nse_q["timestamp"])
        ts_b = validator.parse_timestamp(bse_q["timestamp"])
        lag_seconds = abs((ts_a - ts_b).total_seconds()) if ts_a and ts_b else None

        if lag_seconds is None or lag_seconds > max_lag_seconds:
            lag_skipped.append((symbol, lag_seconds))
            continue

        candidate = build_candidate(symbol, nse_q, bse_q)
        if candidate:
            candidates.append(candidate)

    result = ranking_engine.rank(candidates, available_capital=AVAILABLE_CAPITAL)
    result["lag_skipped"] = lag_skipped
    return result


def main():
    print("==========================================================")
    print("   NSE vs BSE DUAL-LISTED STOCK INEFFICIENCY CHECK        ")
    print(f"   ({len(DUAL_LISTED_STOCKS)} instruments, real two-market data)  ")
    print("==========================================================")

    connector = DhanConnector()
    nse_ids = [s["nse_security_id"] for s in DUAL_LISTED_STOCKS]
    bse_ids = [s["bse_security_id"] for s in DUAL_LISTED_STOCKS]
    by_nse_id = {s["nse_security_id"]: s["symbol"] for s in DUAL_LISTED_STOCKS}
    by_bse_id = {s["bse_security_id"]: s["symbol"] for s in DUAL_LISTED_STOCKS}

    nse_raw = connector.get_last_prices("NSE_EQ", nse_ids)
    bse_raw = connector.get_last_prices("BSE_EQ", bse_ids)
    nse_quotes = {by_nse_id[q["security_id"]]: q for q in nse_raw["quotes"]}
    bse_quotes = {by_bse_id[q["security_id"]]: q for q in bse_raw["quotes"]}

    result = check(nse_quotes, bse_quotes)

    print(f"\n{len(result['lag_skipped'])} skipped (NSE/BSE ticks not in sync, lag > {MAX_LAG_SECONDS}s):")
    for symbol, lag in result["lag_skipped"]:
        print(f"  {symbol}: lag={lag}")

    print(f"\n{len(result['ranked'])} EXECUTABLE inefficiencies (cost+settlement+capital+liquidity all pass):")
    for e in result["ranked"]:
        print(f"  {e['asset']}: buy {e['buy_market']} -> sell {e['sell_market']} | "
              f"net {e['net_profit_pct']:.4f}% | annualized {e['annualized_return_pct']:.2f}% | "
              f"liquidity {e['liquidity_score']:.3f}")

    print(f"\n{len(result['rejected'])} rejected after cost/settlement/capital/liquidity check:")
    for e in result["rejected"]:
        print(f"  {e['asset']}: {e['rejection_reasons']}")


if __name__ == "__main__":
    main()
