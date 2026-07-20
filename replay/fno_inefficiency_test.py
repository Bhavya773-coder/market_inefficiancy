"""Offline test: F&O math, lag gate, detection pass, dashboard state."""
import json
import pathlib
import shutil
from datetime import datetime, timedelta

from inefficiency.fno_inefficiency_checker import (
    futures_basis_candidate, put_call_parity_candidate
)
from scripts.check_fno_inefficiencies import detect
from live.fno_dashboard import build_state

print("=== F&O INEFFICIENCY TEST ===")

# --- futures basis math ---
# spot 1000, 30d @6% -> fair = 1000*(1+0.06*30/365) = 1004.93
c = futures_basis_candidate("X", 1000.0, 1020.0, 30, lot_size=500)
assert c["metadata"]["direction"] == "CASH_AND_CARRY"
assert abs(c["buy_price"] - 1004.9315068493) < 1e-6
assert c["sell_price"] == 1020.0
assert c["quantity"] == 500
assert c["annual_financing_rate_pct"] == 0.0  # no double count

c = futures_basis_candidate("X", 1000.0, 990.0, 30, lot_size=500)
assert c["metadata"]["direction"] == "REVERSE_CASH_AND_CARRY"
assert c["buy_price"] == 990.0
assert futures_basis_candidate("X", 0, 990.0, 30, 500) is None
assert futures_basis_candidate("X", 1000.0, 990.0, 0, 500) is None
print("futures basis math: OK")

# --- put-call parity math ---
# S=1000, C=50, P=30, K=1000, 30d: cost=(1000+30-50)*1.004931=984.83 < 1000 -> CONVERSION
c = put_call_parity_candidate("X", 1000.0, 50.0, 30.0, 1000.0, 30, lot_size=500)
assert c["metadata"]["direction"] == "CONVERSION"
assert c["sell_price"] == 1000.0
assert abs(c["buy_price"] - (980.0 * (1 + 0.06 * 30 / 365))) < 1e-9

c = put_call_parity_candidate("X", 1000.0, 20.0, 80.0, 1000.0, 30, lot_size=500)
assert c["metadata"]["direction"] == "REVERSAL"  # cost 1060*1.0049 > 1000
assert put_call_parity_candidate("X", 1000.0, -1, 30.0, 1000.0, 30, 500) is None
print("put-call parity math: OK")

# --- detection pass with lag gate ---
now = datetime(2026, 7, 20, 11, 0)
universe = {"RELIANCE": {
    "spot_id": 1, "future_id": 2, "lot_size": 500.0,
    "expiry": now + timedelta(days=8),
    "strikes": {1400.0: {"CE": 3, "PE": 4}}
}}


def q(sec_id, price, ts, volume=1e6):
    return {sec_id: {"security_id": sec_id, "last_price": price,
                     "volume": volume, "timestamp": ts}}


T = "20/07/2026 11:00:0{}"
spot = q(1, 1400.0, T.format(0))
# future 1% above fair, options at parity gap
fno = {**q(2, 1420.0, T.format(1)), **q(3, 40.0, T.format(2)), **q(4, 25.0, T.format(1))}
result = detect(universe, spot, fno, now=now)
strategies = {e["strategy"] for e in result["detections"]}
assert "futures_basis" in strategies and "put_call_parity" in strategies
assert result["lag_skipped"] == []
assert all("net_profit" in e and "is_executable" in e for e in result["detections"])
print("detection pass:", [(e["strategy"], e["direction"], e["is_executable"])
                          for e in result["detections"]])

# stale future (30s lag) -> futures check skipped, parity still runs
fno_stale = {**q(2, 1420.0, "20/07/2026 11:00:30"), **q(3, 40.0, T.format(2)), **q(4, 25.0, T.format(1))}
result = detect(universe, spot, fno_stale, now=now)
assert ("RELIANCE", "futures_basis") in result["lag_skipped"]
assert {e["strategy"] for e in result["detections"]} == {"put_call_parity"}
print("lag gate per-leg: OK")

# --- dashboard state ---
d = pathlib.Path("storage/test_fno_dash")
shutil.rmtree(d, ignore_errors=True)
d.mkdir(parents=True)
(d / "inefficiencies.jsonl").write_text(json.dumps({
    "timestamp": "2026-07-20T11:00:00", "asset": "RELIANCE",
    "strategy": "futures_basis", "direction": "CASH_AND_CARRY",
    "net_profit": 1200.0, "net_profit_pct": 0.17,
    "is_executable": True, "rejection_reasons": []}) + "\n")
(d / "paper_trades.jsonl").write_text(
    json.dumps({"type": "capture", "net_profit": 1200.0}) + "\n" +
    json.dumps({"type": "session_summary", "captures": 1, "total_paper_pnl": 1200.0}) + "\n")
s = build_state(d)
assert len(s["rows"]) == 1 and s["total_pnl"] == 1200.0 and s["captures"] == 1
shutil.rmtree(d)
print("dashboard state: OK")

print("\nALL F&O INEFFICIENCY TESTS PASSED")
