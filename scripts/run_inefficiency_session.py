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


def detect_mcx(universe, quotes, max_lag_seconds=MAX_LAG_SECONDS, ranking_engine=None,
               available_capital=AVAILABLE_CAPITAL):
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
        ev = ranking_engine.evaluate(cand, available_capital=available_capital)
        ev["strategy"] = "mcx_calendar"
        ev["direction"] = cand["metadata"]["direction"]
        ev["metadata"] = cand["metadata"]
        detections.append(ev)
    return {"detections": detections, "lag_skipped": lag_skipped}


# ---------- normalize every source into one row shape ----------

# What to literally buy/sell for each strategy+direction pair. Reuses the
# same direction labels the detectors already compute -- no new logic.
ACTION_TEMPLATES = {
    ("futures_basis", "CASH_AND_CARRY"): "BUY SPOT / SELL FUTURE",
    ("futures_basis", "REVERSE_CASH_AND_CARRY"): "SELL SPOT / BUY FUTURE",
    ("put_call_parity", "CONVERSION"): "BUY SPOT + BUY PUT / SELL CALL",
    ("put_call_parity", "REVERSAL"): "SELL SPOT + SELL PUT / BUY CALL",
    ("mcx_calendar", "CASH_AND_CARRY"): "BUY NEAR MONTH / SELL FAR MONTH",
    ("mcx_calendar", "REVERSE_CASH_AND_CARRY"): "SELL NEAR MONTH / BUY FAR MONTH",
}


def action_text(strategy, direction):
    if strategy == "nse_bse_arb":
        buy_mkt, sell_mkt = direction.split("->")
        return f"BUY @ {buy_mkt} / SELL @ {sell_mkt}"
    return ACTION_TEMPLATES.get((strategy, direction), direction)


def _row(ts, opp_id, asset, strategy, direction, ev):
    return {
        "timestamp": ts, "opportunity_id": opp_id, "asset": asset,
        "strategy": strategy, "direction": direction,
        "action": action_text(strategy, direction),
        "net_profit": ev["net_profit"], "net_profit_pct": ev["net_profit_pct"],
        "annualized_return_pct": ev.get("annualized_return_pct", 0.0),
        # capital_required is set from liquidity-capped quantity, not from
        # available_capital, so it is the same number at any capital level.
        # Logging it makes "would this have qualified at capital X?" an
        # offline question — Dhan's rate limit will not tolerate running a
        # second session just to compare capital levels.
        "capital_required": ev.get("capital_required"),
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

def poll_once(connector, fno_universe, mcx_universe,
              available_capital=AVAILABLE_CAPITAL):
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
    nse_bse_res = nse_bse_check(nse_quotes, bse_quotes,
                                available_capital=available_capital)

    # F&O (its own spot + fno batch calls)
    spot_q, fno_q = fetch_fno_quotes(connector, fno_universe)
    fno_res = detect_fno(fno_universe, spot_q, fno_q,
                         available_capital=available_capital)

    # MCX commodities
    mcx_ids = [u["near_id"] for u in mcx_universe.values()] + \
              [u["far_id"] for u in mcx_universe.values()]
    mcx_q = {q["security_id"]: q for q in connector.get_last_prices("MCX_COMM", mcx_ids)["quotes"]} \
        if mcx_ids else {}
    mcx_res = detect_mcx(mcx_universe, mcx_q,
                         available_capital=available_capital)

    return ts, collect_rows(ts, nse_bse_res, fno_res, mcx_res)


def watch(connector, fno_universe, mcx_universe, output_dir, poll_interval=5.0,
          available_capital=AVAILABLE_CAPITAL, capital=None, leverage=1.0):
    out = pathlib.Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ineff_log = open(out / "inefficiencies.jsonl", "a", encoding="utf-8")
    trade_log = open(out / "paper_trades.jsonl", "a", encoding="utf-8")
    captured = {}

    def log(h, p):
        h.write(json.dumps(p, sort_keys=True, default=str) + "\n"); h.flush()

    # Stamp the funding basis into the session itself. Without this a
    # leveraged run is indistinguishable from an unleveraged one when the
    # report is generated days later, and the P&L would read as if it came
    # from cash on hand.
    log(trade_log, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "session_config",
        "capital": capital if capital is not None else available_capital,
        "leverage": leverage,
        "buying_power": available_capital,
        "note": ("Leverage applied uniformly to every strategy. In reality "
                 "only futures-vs-futures legs (mcx_calendar) are genuinely "
                 "margined; cash_and_carry / conversion legs require buying "
                 "the actual shares and cannot be levered this way."
                 if leverage > 1 else "No leverage; capital is cash on hand."),
    })

    print(f"Session started; output {out}. Ctrl+C to stop.")
    try:
        while True:
            open_now, reason = is_market_open_now()  # ponytail: NSE hours; MCX runs later, session stops at NSE close
            if not open_now:
                print(f"Market closed ({reason}); stopping.")
                break
            try:
                ts, rows = poll_once(connector, fno_universe, mcx_universe,
                                    available_capital=available_capital)
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
    p.add_argument("--capital", type=float, default=AVAILABLE_CAPITAL,
                   help="paper capital in INR the ranking engine may deploy "
                        "per opportunity. Caps position size and drives the "
                        "insufficient_capital rejection.")
    p.add_argument("--leverage", type=float, default=1.0,
                   help="multiplier on --capital for buying power, i.e. F&O "
                        "margin. 10 means 1L of cash can carry 10L of "
                        "notional. NOTE: only legs that are genuinely "
                        "margined (futures vs futures) get this in reality; "
                        "cash-and-carry and conversion legs require buying "
                        "the actual shares. See the leverage note logged into "
                        "the session.")
    args = p.parse_args()
    if args.leverage <= 0:
        p.error("--leverage must be > 0")
    buying_power = args.capital * args.leverage

    fno_universe = load_fno_universe()
    mcx_universe = load_mcx_universe()
    print(f"F&O underlyings: {list(fno_universe)}")
    print(f"MCX commodities: {list(mcx_universe)}")
    # ponytail: Dhan's quote endpoint throttles well below our default
    # per-request spacing when 4 batch calls fire back-to-back each poll;
    # 1.1s keeps every call comfortably under 1 req/sec.
    connector = DhanConnector(min_request_interval_seconds=1.1)

    if args.watch:
        print(f"Capital: {args.capital:,.0f} INR x {args.leverage:g} leverage "
              f"= {buying_power:,.0f} INR buying power")
        watch(connector, fno_universe, mcx_universe, args.output_dir,
              args.poll_interval, available_capital=buying_power,
              capital=args.capital, leverage=args.leverage)
    else:
        ts, rows = poll_once(connector, fno_universe, mcx_universe,
                             available_capital=buying_power)
        execu = [r for r in rows if r["is_executable"]]
        print(f"\n{len(rows)} checked, {len(execu)} executable:")
        for r in rows:
            flag = "EXECUTABLE" if r["is_executable"] else ",".join(r["rejection_reasons"])
            print(f"  {r['asset']:<10} {r['strategy']:<16} {r['direction']:<22} "
                  f"net {r['net_profit']:>10.2f} ({r['net_profit_pct']:+.4f}%)  [{flag}]")


if __name__ == "__main__":
    main()
