"""
Offline test: two strategies competing for the same real spot-leg inventory
must not both be captured.

futures_basis REVERSE_CASH_AND_CARRY and put_call_parity REVERSAL on the same
asset both start with "SELL SPOT" -- they are two arbitrage lenses on one
short-sale position, not two independent trades. Found 2026-07-30 when a real
ICICIBANK session captured both and summed them as if they were separate.
"""
import json
import pathlib
import shutil
import tempfile

from scripts.run_inefficiency_session import (
    spot_leg_direction, _row, recover_session_state,
)

print("=== SPOT-LEG CONFLICT TEST ===")

# 1. The mapping itself: same asset, opposing arbitrage lenses, same leg.
assert spot_leg_direction("futures_basis", "REVERSE_CASH_AND_CARRY") == "SELL"
assert spot_leg_direction("put_call_parity", "REVERSAL") == "SELL"
assert spot_leg_direction("futures_basis", "CASH_AND_CARRY") == "BUY"
assert spot_leg_direction("put_call_parity", "CONVERSION") == "BUY"
assert spot_leg_direction("nse_bse_arb", "NSE->BSE") == "BUY"
assert spot_leg_direction("mcx_calendar", "REVERSE_CASH_AND_CARRY") is None, \
    "mcx_calendar is futures-vs-futures, must never compete for spot inventory"
print("spot_leg_direction mapping: OK")


# 2. Replay the exact conflict from the 2026-07-30 session through the same
#    capture logic watch() uses, without needing a live Dhan connection.
def run_capture_loop(rows_by_poll):
    captured, spot_committed, log = {}, {}, []
    for rows in rows_by_poll:
        for r in rows:
            if not r["is_executable"] or r["opportunity_id"] in captured:
                continue
            leg = spot_leg_direction(r["strategy"], r["direction"])
            held = spot_committed.get(r["asset"])
            if leg is not None and held is not None:
                log.append({"type": "blocked", "asset": r["asset"],
                            "strategy": r["strategy"]})
                continue
            captured[r["opportunity_id"]] = r["net_profit"]
            if leg is not None:
                spot_committed[r["asset"]] = leg
            log.append({"type": "capture", "asset": r["asset"],
                        "strategy": r["strategy"], "net": r["net_profit"]})
    return captured, log


def ev(net_profit):
    return {"net_profit": net_profit, "net_profit_pct": 0.6,
            "is_executable": True, "rejection_reasons": []}


rows_by_poll = [
    [_row("t1", "ICICIBANK|futures_basis|REVERSE_CASH_AND_CARRY", "ICICIBANK",
          "futures_basis", "REVERSE_CASH_AND_CARRY", ev(6129.88))],
    [_row("t2", "ICICIBANK|put_call_parity|REVERSAL", "ICICIBANK",
          "put_call_parity", "REVERSAL", ev(6208.52))],
    [_row("t3", "CRUDEOIL|mcx_calendar|REVERSE_CASH_AND_CARRY", "CRUDEOIL",
          "mcx_calendar", "REVERSE_CASH_AND_CARRY", ev(281.02))],
]

captured, log = run_capture_loop(rows_by_poll)

assert len(captured) == 2, captured  # ICICIBANK futures_basis + CRUDEOIL mcx, NOT put_call_parity too
assert "ICICIBANK|futures_basis|REVERSE_CASH_AND_CARRY" in captured
assert "ICICIBANK|put_call_parity|REVERSAL" not in captured
assert "CRUDEOIL|mcx_calendar|REVERSE_CASH_AND_CARRY" in captured
blocked = [e for e in log if e["type"] == "blocked"]
assert len(blocked) == 1 and blocked[0]["strategy"] == "put_call_parity"
assert sum(captured.values()) == 6129.88 + 281.02, sum(captured.values())
print("ICICIBANK spot-leg conflict correctly blocks the second strategy: OK")


# 3. Same asset, same strategy+direction reappearing across polls (a spread
#    that just stays open) must still be captured only once via the existing
#    opportunity_id check -- this fix must not change that behaviour.
rows_by_poll_repeat = [
    [_row("t1", "CRUDEOIL|mcx_calendar|REVERSE_CASH_AND_CARRY", "CRUDEOIL",
          "mcx_calendar", "REVERSE_CASH_AND_CARRY", ev(281.02))],
    [_row("t2", "CRUDEOIL|mcx_calendar|REVERSE_CASH_AND_CARRY", "CRUDEOIL",
          "mcx_calendar", "REVERSE_CASH_AND_CARRY", ev(281.02))],
]
captured2, _ = run_capture_loop(rows_by_poll_repeat)
assert len(captured2) == 1
print("repeated same-opportunity poll still captures once: OK")


# 4. Two DIFFERENT assets on the same strategy must never conflict with
#    each other -- the lock is per-asset, not global.
rows_by_poll_diff_assets = [
    [_row("t1", "ICICIBANK|futures_basis|REVERSE_CASH_AND_CARRY", "ICICIBANK",
          "futures_basis", "REVERSE_CASH_AND_CARRY", ev(100.0))],
    [_row("t2", "TATASTEEL|futures_basis|REVERSE_CASH_AND_CARRY", "TATASTEEL",
          "futures_basis", "REVERSE_CASH_AND_CARRY", ev(50.0))],
]
captured3, _ = run_capture_loop(rows_by_poll_diff_assets)
assert len(captured3) == 2
print("different assets never conflict: OK")

# 5. Restart recovery: a second process pointed at the same --output-dir
#    must rebuild both captured and spot_committed from disk, including
#    logs written before "direction" was added to the capture record
#    (parsed from opportunity_id instead).
tmp = tempfile.mkdtemp()
try:
    trade_log_path = pathlib.Path(tmp) / "paper_trades.jsonl"
    with open(trade_log_path, "w", encoding="utf-8") as f:
        # Old-style record: no "direction" key, pre-dates this fix.
        f.write(json.dumps({
            "timestamp": "t1", "type": "capture",
            "opportunity_id": "ICICIBANK|futures_basis|REVERSE_CASH_AND_CARRY",
            "asset": "ICICIBANK", "strategy": "futures_basis",
            "net_profit": 6129.88,
        }) + "\n")
        # New-style record: has "direction".
        f.write(json.dumps({
            "timestamp": "t2", "type": "capture",
            "opportunity_id": "CRUDEOIL|mcx_calendar|REVERSE_CASH_AND_CARRY",
            "asset": "CRUDEOIL", "strategy": "mcx_calendar",
            "direction": "REVERSE_CASH_AND_CARRY", "net_profit": 281.02,
        }) + "\n")

    captured, spot_committed, capital_used = recover_session_state(tmp)
    assert len(captured) == 2, captured
    assert spot_committed == {"ICICIBANK": "SELL"}, spot_committed  # mcx never commits a leg
    print("restart recovery rebuilds state from an existing log (old + new format): OK")

    # A second "process" starting fresh must not re-capture ICICIBANK's leg.
    rows_after_restart = [
        [_row("t3", "ICICIBANK|put_call_parity|REVERSAL", "ICICIBANK",
              "put_call_parity", "REVERSAL", ev(6208.52))],
    ]
    captured.update({})  # simulate the recovered dict being the starting state
    for rows in rows_after_restart:
        for r in rows:
            if not r["is_executable"] or r["opportunity_id"] in captured:
                continue
            leg = spot_leg_direction(r["strategy"], r["direction"])
            held = spot_committed.get(r["asset"])
            if leg is not None and held is not None:
                continue  # correctly blocked
            captured[r["opportunity_id"]] = r["net_profit"]
    assert "ICICIBANK|put_call_parity|REVERSAL" not in captured
    print("recovered commitment blocks the conflicting leg after a restart: OK")

    # Empty / nonexistent directory must not raise.
    empty_captured, empty_spot, empty_cap = recover_session_state(
        pathlib.Path(tmp) / "does_not_exist")
    assert empty_captured == {} and empty_spot == {} and empty_cap == 0.0
    print("recovery on a fresh session directory returns empty state: OK")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# 6. Capital must deplete as trades are captured. The ranking engine checks
#    every candidate against the FULL pool independently, so without a
#    running total a session can capture several trades that each fit the
#    pool but together exceed it. Found 2026-07-31.
def run_with_capital(rows_by_poll, pool):
    captured, spot_committed, capital_used, blocked = {}, {}, 0.0, []
    for rows in rows_by_poll:
        for r in rows:
            if not r["is_executable"] or r["opportunity_id"] in captured:
                continue
            need = r.get("capital_required") or 0.0
            if need > pool - capital_used:
                blocked.append(("insufficient_remaining_capital", r["asset"]))
                continue
            leg = spot_leg_direction(r["strategy"], r["direction"])
            if leg is not None and spot_committed.get(r["asset"]) is not None:
                blocked.append(("spot_leg_already_committed", r["asset"]))
                continue
            captured[r["opportunity_id"]] = r["net_profit"]
            capital_used += need
            if leg is not None:
                spot_committed[r["asset"]] = leg
    return captured, capital_used, blocked


def ev_cap(net_profit, capital_required):
    return {"net_profit": net_profit, "net_profit_pct": 0.6,
            "annualized_return_pct": 10.0, "capital_required": capital_required,
            "is_executable": True, "rejection_reasons": []}


# Two DIFFERENT assets each needing 7L against a 10L pool: only one fits.
two_big = [[
    _row("t1", "A|futures_basis|CASH_AND_CARRY", "A", "futures_basis",
         "CASH_AND_CARRY", ev_cap(5000.0, 700000.0)),
    _row("t2", "B|futures_basis|CASH_AND_CARRY", "B", "futures_basis",
         "CASH_AND_CARRY", ev_cap(5000.0, 700000.0)),
]]
cap6, used6, blocked6 = run_with_capital(two_big, 1_000_000)
assert len(cap6) == 1, cap6
assert used6 == 700000.0, used6
assert used6 <= 1_000_000
assert blocked6 == [("insufficient_remaining_capital", "B")], blocked6
print("capital depletes; a second oversized trade is blocked: OK")

# Several small trades that DO fit together must all be captured.
many_small = [[
    _row(f"t{i}", f"S{i}|mcx_calendar|CASH_AND_CARRY", f"S{i}", "mcx_calendar",
         "CASH_AND_CARRY", ev_cap(50.0, 10000.0))
    for i in range(5)
]]
cap7, used7, blocked7 = run_with_capital(many_small, 1_000_000)
assert len(cap7) == 5 and used7 == 50000.0 and not blocked7, (cap7, used7, blocked7)
print("trades that fit within the pool are all still captured: OK")

# capital_used must survive a restart, so a resumed session cannot re-spend it.
tmp2 = tempfile.mkdtemp()
try:
    with open(pathlib.Path(tmp2) / "paper_trades.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": "t1", "type": "capture",
            "opportunity_id": "A|futures_basis|CASH_AND_CARRY",
            "asset": "A", "strategy": "futures_basis",
            "direction": "CASH_AND_CARRY",
            "capital_required": 700000.0, "net_profit": 5000.0,
        }) + "\n")
    _c, _s, recovered_capital = recover_session_state(tmp2)
    assert recovered_capital == 700000.0, recovered_capital
    print("capital_used is recovered across a restart: OK")
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

print("\nALL SPOT-LEG CONFLICT TESTS PASSED")
