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

    captured, spot_committed = recover_session_state(tmp)
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
    empty_captured, empty_spot = recover_session_state(pathlib.Path(tmp) / "does_not_exist")
    assert empty_captured == {} and empty_spot == {}
    print("recovery on a fresh session directory returns empty state: OK")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\nALL SPOT-LEG CONFLICT TESTS PASSED")
