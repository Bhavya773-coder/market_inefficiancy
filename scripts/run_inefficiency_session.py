"""
ONE session runner covering every Dhan-reachable market, writing one
dashboard-compatible session so you see stocks AND commodities (gold,
silver, crude...) in a single table with one P&L line at the end.

Markets checked each poll (all via your single Dhan token):
  - NSE vs BSE      same stock, two exchanges          (geographic)
  - NSE spot vs F&O futures basis + put-call parity     (time / instrument)
  - MCX calendar    near-month vs far-month commodity   (time)  <- gold etc.

Every leg pair is lag-gated per instrument; survivors go through the
existing cost+settlement+capital+liquidity ranking engine. Executable
catches are locked in as paper P&L (both legs assumed filled at quotes).

Run tomorrow:
  PYTHONPATH=. python scripts/run_inefficiency_session.py --watch \
      --output-dir storage/session_20260720
  PYTHONPATH=. python live/fno_dashboard.py --session-dir storage/session_20260720
  -> http://127.0.0.1:8730

One-shot snapshot (no loop):
  PYTHONPATH=. python scripts/run_inefficiency_session.py
"""
import argparse
import json
import os
import pathlib
import sys
import time
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from connectors.dhan_connector import DhanConnector
from ai.quote_freshness_validator import QuoteFreshnessValidator
from inefficiency.opportunity_ranking_engine import OpportunityRankingEngine
from inefficiency.fno_inefficiency_checker import futures_basis_candidate
from inefficiency.nse_bse_dual_listed_universe import DUAL_LISTED_STOCKS
from scripts.check_nse_bse_inefficiencies import check as nse_bse_check
from scripts.check_fno_inefficiencies import (
    load_universe as load_fno_universe, fetch_quotes as fetch_fno_quotes, detect as detect_fno
)
from live.run_live_paper_trading import is_market_open_now

MCX_COMMODITIES = ["GOLD", "SILVER", "CRUDEOIL", "COPPER", "NATURALGAS"]
MAX_LAG_SECONDS = 10.0
AVAILABLE_CAPITAL = 1_000_000


# ---------- MCX calendar-spread universe + detection ----------

def load_mcx_universe(commodities=MCX_COMMODITIES, csv_path="security_id_list.csv", now=None):
    """Near-month + next-month FUTCOM per commodity."""
    import pandas as pd
    now = now or datetime.now()
    df = pd.read_csv(csv_path, low_memory=False)
    fut = df[(df.SEM_EXM_EXCH_ID == "MCX") & (df.SEM_INSTRUMENT_NAME == "FUTCOM")]
    universe = {}
    for comm in commodities:
        rows = fut[fut.SEM_TRADING_SYMBOL.str.startswith(comm + "-")].copy()
        rows["e"] = pd.to_datetime(rows.SEM_EXPIRY_DATE)
        rows = rows[rows.e > now].sort_values("e")
        if len(rows) < 2:
            continue
        near, far = rows.iloc[0], rows.iloc[1]
        universe[comm] = {
            "near_id": int(near.SEM_SMST_SECURITY_ID),
            "far_id": int(far.SEM_SMST_SECURITY_ID),
            "lot_size": float(near.SEM_LOT_UNITS),
            "days_between": (far.e - near.e).days or 30,
        }
    return universe


def detect_mcx(universe, quotes, max_lag_seconds=MAX_LAG_SECONDS, ranking_engine=None):
    """Calendar spread = far vs fair(near). Reuses cost-of-carry math."""
    validator = QuoteFreshnessValidator()
    ranking_engine = ranking_engine or OpportunityRankingEngine()
    detections, lag_skipped = [], []
    for comm, u in universe.items():
        near_q, far_q = quotes.get(u["near_id"]), quotes.get(u["far_id"])
        if not near_q or not far_q:
            continue
        if not validator.timestamps_close(near_q["timestamp"], far_q["timestamp"],
                                          max_gap_seconds=max_lag_seconds):
            lag_skipped.append((comm, "mcx_calendar"))
            continue
        cand = futures_basis_candidate(
            comm, near_q["last_price"], far_q["last_price"], u["days_between"],
            u["lot_size"], available_qty=far_q.get("volume") or 100000.0)
        if not cand:
            continue
        cand["opportunity_id"] = f"{comm}|mcx_calendar|{cand['metadata']['direction']}"
        ev = ranking_engine.evaluate(cand, available_capital=AVAILABLE_CAPITAL)
        ev["strategy"] = "mcx_calendar"
        ev["direction"] = cand["metadata"]["direction"]
        ev["metadata"] = cand["metadata"]
        detections.append(ev)
    return {"detections": detections, "lag_skipped": lag_skipped}


# ---------- normalize every source into one row shape ----------

def _row(ts, opp_id, asset, strategy, direction, ev):
    return {
        "timestamp": ts, "opportunity_id": opp_id, "asset": asset,
        "strategy": strategy, "direction": direction,
        "net_profit": ev["net_profit"], "net_profit_pct": ev["net_profit_pct"],
        "annualized_return_pct": ev.get("annualized_return_pct", 0.0),
        "is_executable": ev["is_executable"], "rejection_reasons": ev["rejection_reasons"],
    }


def collect_rows(ts, nse_bse_res, fno_res, mcx_res):
    rows = []
    for ev in nse_bse_res["ranked"] + nse_bse_res["rejected"]:
        rows.append(_row(ts, ev["opportunity_id"], ev["asset"], "nse_bse_arb",
                         f"{ev['buy_market']}->{ev['sell_market']}", ev))
    for ev in fno_res["detections"] + mcx_res["detections"]:
        rows.append(_row(ts, ev["opportunity_id"], ev["asset"], ev["strategy"],
                         ev["direction"], ev))
    return rows


# ---------- one poll ----------

def poll_once(connector, fno_universe, mcx_universe):
    ts = datetime.now(timezone.utc).isoformat()

    # NSE + BSE stock quotes keyed by symbol
    nse_ids = [s["nse_security_id"] for s in DUAL_LISTED_STOCKS]
    bse_ids = [s["bse_security_id"] for s in DUAL_LISTED_STOCKS]
    by_nse = {s["nse_security_id"]: s["symbol"] for s in DUAL_LISTED_STOCKS}
    by_bse = {s["bse_security_id"]: s["symbol"] for s in DUAL_LISTED_STOCKS}
    nse_raw = connector.get_last_prices("NSE_EQ", nse_ids)
    bse_raw = connector.get_last_prices("BSE_EQ", bse_ids)
    nse_quotes = {by_nse[q["security_id"]]: q for q in nse_raw["quotes"]}
    bse_quotes = {by_bse[q["security_id"]]: q for q in bse_raw["quotes"]}
    nse_bse_res = nse_bse_check(nse_quotes, bse_quotes)

    # F&O (its own spot + fno batch calls)
    spot_q, fno_q = fetch_fno_quotes(connector, fno_universe)
    fno_res = detect_fno(fno_universe, spot_q, fno_q)

    # MCX commodities
    mcx_ids = [u["near_id"] for u in mcx_universe.values()] + \
              [u["far_id"] for u in mcx_universe.values()]
    mcx_q = {q["security_id"]: q for q in connector.get_last_prices("MCX_COMM", mcx_ids)["quotes"]} \
        if mcx_ids else {}
    mcx_res = detect_mcx(mcx_universe, mcx_q)

    return ts, collect_rows(ts, nse_bse_res, fno_res, mcx_res)


def watch(connector, fno_universe, mcx_universe, output_dir, poll_interval=5.0):
    out = pathlib.Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ineff_log = open(out / "inefficiencies.jsonl", "a", encoding="utf-8")
    trade_log = open(out / "paper_trades.jsonl", "a", encoding="utf-8")
    captured = {}

    def log(h, p):
        h.write(json.dumps(p, sort_keys=True, default=str) + "\n"); h.flush()

    print(f"Session started; output {out}. Ctrl+C to stop.")
    try:
        while True:
            open_now, reason = is_market_open_now()  # ponytail: NSE hours; MCX runs later, session stops at NSE close
            if not open_now:
                print(f"Market closed ({reason}); stopping.")
                break
            try:
                ts, rows = poll_once(connector, fno_universe, mcx_universe)
            except Exception as e:
                print(f"poll error: {e}")
                time.sleep(poll_interval); continue
            for r in rows:
                log(ineff_log, r)
                if r["is_executable"] and r["opportunity_id"] not in captured:
                    captured[r["opportunity_id"]] = r["net_profit"]
                    log(trade_log, {"timestamp": r["timestamp"], "type": "capture",
                                    "opportunity_id": r["opportunity_id"], "asset": r["asset"],
                                    "strategy": r["strategy"], "net_profit": r["net_profit"]})
            print(f"{ts[11:19]}  rows={len(rows)}  captures={len(captured)}  "
                  f"running_pnl={sum(captured.values()):+.2f}")
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("Ctrl+C — closing.")
    finally:
        total = sum(captured.values())
        log(trade_log, {"timestamp": datetime.now(timezone.utc).isoformat(),
                        "type": "session_summary", "captures": len(captured),
                        "total_paper_pnl": total})
        print(f"SESSION CLOSE: {len(captured)} captures, total paper P&L: {total:+.2f} INR")
        ineff_log.close(); trade_log.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--watch", action="store_true")
    p.add_argument("--poll-interval", type=float, default=5.0)
    p.add_argument("--output-dir", default="storage/session")
    args = p.parse_args()

    fno_universe = load_fno_universe()
    mcx_universe = load_mcx_universe()
    print(f"F&O underlyings: {list(fno_universe)}")
    print(f"MCX commodities: {list(mcx_universe)}")
    # ponytail: Dhan's quote endpoint throttles well below our default
    # per-request spacing when 4 batch calls fire back-to-back each poll;
    # 1.1s keeps every call comfortably under 1 req/sec.
    connector = DhanConnector(min_request_interval_seconds=1.1)

    if args.watch:
        watch(connector, fno_universe, mcx_universe, args.output_dir, args.poll_interval)
    else:
        ts, rows = poll_once(connector, fno_universe, mcx_universe)
        execu = [r for r in rows if r["is_executable"]]
        print(f"\n{len(rows)} checked, {len(execu)} executable:")
        for r in rows:
            flag = "EXECUTABLE" if r["is_executable"] else ",".join(r["rejection_reasons"])
            print(f"  {r['asset']:<10} {r['strategy']:<16} {r['direction']:<22} "
                  f"net {r['net_profit']:>10.2f} ({r['net_profit_pct']:+.4f}%)  [{flag}]")


if __name__ == "__main__":
    main()
