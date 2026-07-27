"""
F&O inefficiency detector: spot vs futures basis + put-call parity,
lag-gated, verdict by OpportunityRankingEngine.

One-shot:  PYTHONPATH=. python scripts/check_fno_inefficiencies.py
Monitor:   PYTHONPATH=. python scripts/check_fno_inefficiencies.py --watch \
               --output-dir storage/fno_session_YYYYMMDD
           (loops until 15:30 IST market close, writes inefficiencies.jsonl,
            paper_trades.jsonl and a session_summary with total paper P&L —
            the P&L is the locked-in net edge assuming both legs filled at
            the quoted prices; view with live/fno_dashboard.py)
"""
import argparse
import json
import pathlib
import sys
import os
import time
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from connectors.dhan_connector import DhanConnector
from ai.quote_freshness_validator import QuoteFreshnessValidator
from inefficiency.opportunity_ranking_engine import OpportunityRankingEngine
from inefficiency.fno_inefficiency_checker import (
    futures_basis_candidate, put_call_parity_candidate
)
from inefficiency.nse_bse_dual_listed_universe import DUAL_LISTED_STOCKS
from live.run_live_paper_trading import is_market_open_now

UNDERLYINGS = ["RELIANCE", "TCS", "SBIN", "ICICIBANK", "HDFCBANK", "TATASTEEL", "JSWSTEEL"]
MAX_LAG_SECONDS = 10.0
AVAILABLE_CAPITAL = 1_000_000


def load_universe(symbols=UNDERLYINGS, csv_path="security_id_list.csv", now=None):
    """Spot id + nearest-expiry future + that expiry's option strikes, per symbol."""
    import pandas as pd
    now = now or datetime.now()
    df = pd.read_csv(csv_path, low_memory=False)
    spot_ids = {s["symbol"]: s["nse_security_id"] for s in DUAL_LISTED_STOCKS}
    fno = df[(df.SEM_EXM_EXCH_ID == "NSE")]
    universe = {}
    for symbol in symbols:
        if symbol not in spot_ids:
            continue
        futs = fno[(fno.SEM_INSTRUMENT_NAME == "FUTSTK")
                   & (fno.SEM_TRADING_SYMBOL.str.startswith(symbol + "-"))].copy()
        futs["expiry"] = pd.to_datetime(futs.SEM_EXPIRY_DATE)
        futs = futs[futs.expiry > now].sort_values("expiry")
        if futs.empty:
            continue
        fut = futs.iloc[0]
        expiry = fut.expiry.to_pydatetime()
        opts = fno[(fno.SEM_INSTRUMENT_NAME == "OPTSTK")
                   & (fno.SEM_TRADING_SYMBOL.str.startswith(symbol + "-"))
                   & (fno.SEM_EXPIRY_DATE == fut.SEM_EXPIRY_DATE)]
        strikes = {}
        for _, o in opts.iterrows():
            strikes.setdefault(float(o.SEM_STRIKE_PRICE), {})[o.SEM_OPTION_TYPE] = \
                int(o.SEM_SMST_SECURITY_ID)
        universe[symbol] = {
            "spot_id": spot_ids[symbol],
            "future_id": int(fut.SEM_SMST_SECURITY_ID),
            "lot_size": float(fut.SEM_LOT_UNITS),
            "expiry": expiry,
            # only strikes with both CE and PE are usable for parity
            "strikes": {k: v for k, v in strikes.items() if "CE" in v and "PE" in v}
        }
    return universe


def detect(universe, spot_quotes, fno_quotes, now=None,
           max_lag_seconds=MAX_LAG_SECONDS, ranking_engine=None,
           available_capital=AVAILABLE_CAPITAL):
    """
    Pure detection pass (testable offline). quotes keyed by security_id.
    Returns {"detections": [evaluation+metadata dicts], "lag_skipped": [...]}
    """
    validator = QuoteFreshnessValidator()
    ranking_engine = ranking_engine or OpportunityRankingEngine()
    now = now or datetime.now()
    detections, lag_skipped = [], []

    def in_sync(q_a, q_b):
        return validator.timestamps_close(
            q_a["timestamp"], q_b["timestamp"], max_gap_seconds=max_lag_seconds)

    for symbol, u in universe.items():
        spot_q = spot_quotes.get(u["spot_id"])
        if not spot_q:
            continue
        days = (u["expiry"] - now).total_seconds() / 86400.0
        candidates = []

        fut_q = fno_quotes.get(u["future_id"])
        if fut_q:
            if in_sync(spot_q, fut_q):
                c = futures_basis_candidate(
                    symbol, spot_q["last_price"], fut_q["last_price"], days,
                    u["lot_size"],
                    available_qty=fut_q.get("volume") or 100000.0)
                if c:
                    candidates.append(c)
            else:
                lag_skipped.append((symbol, "futures_basis"))

        if u["strikes"]:
            atm = min(u["strikes"], key=lambda k: abs(k - spot_q["last_price"]))
            ce_q = fno_quotes.get(u["strikes"][atm]["CE"])
            pe_q = fno_quotes.get(u["strikes"][atm]["PE"])
            if ce_q and pe_q:
                if in_sync(spot_q, ce_q) and in_sync(spot_q, pe_q) and in_sync(ce_q, pe_q):
                    c = put_call_parity_candidate(
                        symbol, spot_q["last_price"], ce_q["last_price"],
                        pe_q["last_price"], atm, days, u["lot_size"],
                        available_qty=min(ce_q.get("volume") or 100000.0,
                                          pe_q.get("volume") or 100000.0))
                    if c:
                        candidates.append(c)
                else:
                    lag_skipped.append((symbol, "put_call_parity"))

        for cand in candidates:
            ev = ranking_engine.evaluate(cand, available_capital=available_capital)
            ev["strategy"] = cand["opportunity_id"].split("|")[1]
            ev["direction"] = cand["metadata"]["direction"]
            ev["metadata"] = cand["metadata"]
            detections.append(ev)

    detections.sort(key=lambda e: -e["rank_score"])
    return {"detections": detections, "lag_skipped": lag_skipped}


def fetch_quotes(connector, universe, spot_prices_hint=None):
    """Two batch calls: all spots, then futures + ATM option legs."""
    spot_ids = [u["spot_id"] for u in universe.values()]
    spot_raw = connector.get_last_prices("NSE_EQ", spot_ids)
    spot_quotes = {q["security_id"]: q for q in spot_raw["quotes"]}

    fno_ids = []
    for u in universe.values():
        fno_ids.append(u["future_id"])
        spot_q = spot_quotes.get(u["spot_id"])
        if spot_q and u["strikes"]:
            atm = min(u["strikes"], key=lambda k: abs(k - spot_q["last_price"]))
            fno_ids += [u["strikes"][atm]["CE"], u["strikes"][atm]["PE"]]
    fno_raw = connector.get_last_prices("NSE_FNO", fno_ids)
    fno_quotes = {q["security_id"]: q for q in fno_raw["quotes"]}
    return spot_quotes, fno_quotes


def print_detections(result):
    print(f"\n{len(result['lag_skipped'])} lag-skipped: {result['lag_skipped']}")
    print(f"{len(result['detections'])} detections:")
    for e in result["detections"]:
        flag = "EXECUTABLE" if e["is_executable"] else f"rejected: {','.join(e['rejection_reasons'])}"
        print(f"  {e['asset']:<10} {e['strategy']:<16} {e['direction']:<24} "
              f"net {e['net_profit']:>10.2f} INR ({e['net_profit_pct']:+.4f}%)  [{flag}]")


def watch(connector, universe, output_dir, poll_interval=5.0):
    out = pathlib.Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ineff_log = open(out / "inefficiencies.jsonl", "a", encoding="utf-8")
    trade_log = open(out / "paper_trades.jsonl", "a", encoding="utf-8")
    captured = {}  # opportunity_id -> net_profit, first executable detection wins

    def log(handle, payload):
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
        handle.flush()

    print(f"Watching {len(universe)} underlyings until market close; output: {out}")
    try:
        while True:
            open_now, reason = is_market_open_now()
            if not open_now:
                print(f"Market closed ({reason}); stopping.")
                break
            ts = datetime.now(timezone.utc).isoformat()
            try:
                spot_quotes, fno_quotes = fetch_quotes(connector, universe)
            except Exception as e:
                print(f"poll error: {e}")
                time.sleep(poll_interval)
                continue
            result = detect(universe, spot_quotes, fno_quotes)
            for e in result["detections"]:
                log(ineff_log, {"timestamp": ts, **{k: e[k] for k in (
                    "opportunity_id", "asset", "strategy", "direction",
                    "net_profit", "net_profit_pct", "annualized_return_pct",
                    "is_executable", "rejection_reasons", "metadata")}})
                if e["is_executable"] and e["opportunity_id"] not in captured:
                    captured[e["opportunity_id"]] = e["net_profit"]
                    log(trade_log, {"timestamp": ts, "type": "capture",
                                    "opportunity_id": e["opportunity_id"],
                                    "asset": e["asset"], "strategy": e["strategy"],
                                    "direction": e["direction"],
                                    "net_profit": e["net_profit"],
                                    "note": "locked-in edge, both legs assumed filled at quoted prices"})
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("Ctrl+C — closing.")
    finally:
        total = sum(captured.values())
        log(trade_log, {"timestamp": datetime.now(timezone.utc).isoformat(),
                        "type": "session_summary", "captures": len(captured),
                        "total_paper_pnl": total})
        print(f"SESSION CLOSE: {len(captured)} captures, total paper P&L: {total:+.2f} INR")
        ineff_log.close()
        trade_log.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--watch", action="store_true")
    p.add_argument("--poll-interval", type=float, default=5.0)
    p.add_argument("--output-dir", default="storage/fno_session")
    args = p.parse_args()

    universe = load_universe()
    print(f"F&O universe: { {s: {'fut': u['future_id'], 'expiry': str(u['expiry'].date()), 'strikes': len(u['strikes'])} for s, u in universe.items()} }")
    connector = DhanConnector()

    if args.watch:
        watch(connector, universe, args.output_dir, args.poll_interval)
    else:
        spot_quotes, fno_quotes = fetch_quotes(connector, universe)
        print_detections(detect(universe, spot_quotes, fno_quotes))


if __name__ == "__main__":
    main()
