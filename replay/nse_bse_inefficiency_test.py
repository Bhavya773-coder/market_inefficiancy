"""
Offline test for scripts/check_nse_bse_inefficiencies.py -- proves the
lag gate and the direction/ranking logic without live Dhan.
"""
from scripts.check_nse_bse_inefficiencies import check, build_candidate

print("=== NSE vs BSE INEFFICIENCY CHECK TEST ===")

UNIVERSE = [{"symbol": "RELIANCE", "nse_security_id": 1, "bse_security_id": 2}]


def q(price, ts, volume=100000):
    return {"last_price": price, "volume": volume, "timestamp": ts}


# 1. Real price gap, synchronized ticks -> executable
result = check(
    {"RELIANCE": q(1400.0, "18/07/2026 10:00:00")},
    {"RELIANCE": q(1410.0, "18/07/2026 10:00:02")},  # 2s apart, well in sync
    universe=UNIVERSE
)
print("synced gap:", len(result["ranked"]), "ranked,", len(result["rejected"]), "rejected,",
      len(result["lag_skipped"]), "lag-skipped")
assert result["lag_skipped"] == []
assert len(result["ranked"]) + len(result["rejected"]) == 1
if result["ranked"]:
    assert result["ranked"][0]["buy_market"] == "NSE"  # cheaper leg
    assert result["ranked"][0]["opportunity_type"] == "arbitrage"

# 2. Same gap, but ticks 30s apart -> LAG TOO HIGH, must be skipped not flagged
result = check(
    {"RELIANCE": q(1400.0, "18/07/2026 10:00:00")},
    {"RELIANCE": q(1410.0, "18/07/2026 10:00:30")},  # 30s apart
    universe=UNIVERSE, max_lag_seconds=10.0
)
print("desynced gap:", result["lag_skipped"])
assert result["ranked"] == [] and result["rejected"] == []
assert result["lag_skipped"] == [("RELIANCE", 30.0)]

# 3. Identical price -> no candidate built at all
cand = build_candidate("RELIANCE", q(1400.0, "x"), q(1400.0, "y"))
assert cand is None
print("zero-gap produces no candidate: OK")

# 4. Direction flips correctly when BSE is cheaper
result = check(
    {"RELIANCE": q(1410.0, "18/07/2026 10:00:00")},
    {"RELIANCE": q(1400.0, "18/07/2026 10:00:01")},
    universe=UNIVERSE
)
all_evals = result["ranked"] + result["rejected"]
assert len(all_evals) == 1
assert all_evals[0]["buy_market"] == "BSE"
print("direction flips to cheaper leg: OK")

# 5. Missing quote on one side is just skipped, no crash
result = check({"RELIANCE": q(1400.0, "18/07/2026 10:00:00")}, {}, universe=UNIVERSE)
assert result == {"ranked": [], "rejected": [], "evaluated_count": 0, "lag_skipped": []}
print("missing-side quote handled: OK")

print("\nALL NSE/BSE INEFFICIENCY TESTS PASSED")
