"""Offline test: MCX calendar detection + unified row collection."""
from datetime import datetime, timedelta

from scripts.run_inefficiency_session import detect_mcx, collect_rows

print("=== MCX + UNIFIED SESSION TEST ===")

universe = {"GOLD": {"near_id": 1, "far_id": 2, "lot_size": 1.0, "days_between": 30}}


def q(sec_id, price, ts, volume=1e6):
    return {sec_id: {"security_id": sec_id, "last_price": price,
                     "volume": volume, "timestamp": ts}}


# far 1% above fair(near) -> calendar inefficiency, synced ticks
quotes = {**q(1, 100000.0, "20/07/2026 11:00:00"),
          **q(2, 101500.0, "20/07/2026 11:00:02")}
res = detect_mcx(universe, quotes)
assert res["lag_skipped"] == []
assert len(res["detections"]) == 1
d = res["detections"][0]
assert d["strategy"] == "mcx_calendar"
assert d["asset"] == "GOLD"
assert d["direction"] in ("CASH_AND_CARRY", "REVERSE_CASH_AND_CARRY")
assert "net_profit" in d and "is_executable" in d
print("mcx calendar detect:", d["direction"], "net", round(d["net_profit"], 2),
      "executable", d["is_executable"])

# desynced near/far (30s) -> skipped, not flagged
quotes_stale = {**q(1, 100000.0, "20/07/2026 11:00:00"),
                **q(2, 101500.0, "20/07/2026 11:00:30")}
res = detect_mcx(universe, quotes_stale)
assert res["detections"] == [] and res["lag_skipped"] == [("GOLD", "mcx_calendar")]
print("mcx lag gate: OK")

# missing far leg -> skipped, no crash
res = detect_mcx(universe, q(1, 100000.0, "20/07/2026 11:00:00"))
assert res["detections"] == [] and res["lag_skipped"] == []
print("mcx missing leg: OK")

# unified row collection normalizes all three sources into one shape
class Ev(dict):
    pass


nse_bse = {
    "ranked": [{"opportunity_id": "RELIANCE|nse", "asset": "RELIANCE",
                "buy_market": "NSE", "sell_market": "BSE", "net_profit": 500.0,
                "net_profit_pct": 0.3, "annualized_return_pct": 40.0,
                "is_executable": True, "rejection_reasons": []}],
    "rejected": []
}
fno = {"detections": [{"opportunity_id": "TCS|futures_basis|CASH_AND_CARRY",
                       "asset": "TCS", "strategy": "futures_basis",
                       "direction": "CASH_AND_CARRY", "net_profit": -10.0,
                       "net_profit_pct": -0.01, "annualized_return_pct": -1.0,
                       "is_executable": False, "rejection_reasons": ["below_min_annualized_return"]}]}
mcx = detect_mcx(universe, quotes)
rows = collect_rows("2026-07-20T11:00:00", nse_bse, fno, mcx)
strategies = {r["strategy"] for r in rows}
assert strategies == {"nse_bse_arb", "futures_basis", "mcx_calendar"}, strategies
assert all({"timestamp", "asset", "strategy", "direction", "action", "net_profit",
            "net_profit_pct", "is_executable", "rejection_reasons"} <= set(r) for r in rows)
assert next(r for r in rows if r["asset"] == "RELIANCE")["direction"] == "NSE->BSE"

# action must literally say buy/sell, not a raw enum
reliance = next(r for r in rows if r["asset"] == "RELIANCE")
assert reliance["action"] == "BUY @ NSE / SELL @ BSE"
tcs = next(r for r in rows if r["asset"] == "TCS")
assert tcs["action"] == "BUY SPOT / SELL FUTURE"
gold = next(r for r in rows if r["asset"] == "GOLD")
assert gold["action"] in ("BUY NEAR MONTH / SELL FAR MONTH", "SELL NEAR MONTH / BUY FAR MONTH")
print("unified rows:", [(r["asset"], r["strategy"], r["action"]) for r in rows])

print("\nALL MCX + SESSION TESTS PASSED")
