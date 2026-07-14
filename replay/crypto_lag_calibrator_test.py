"""
Offline test for CryptoLagCalibrator: deterministic synthetic candle
series with a KNOWN lag structure, verifying the calibrator finds it —
and honestly refuses to calibrate when there is nothing to find.
"""
from ai.crypto_lag_calibrator import CryptoLagCalibrator

print("=== CRYPTO LAG CALIBRATOR TEST ===")


def candles_from_closes(closes, start_ms=1_784_000_000_000, step_ms=60_000):
    return [
        {"timestamp_ms": start_ms + i * step_ms, "open": c, "high": c,
         "low": c, "close": c, "volume": 1.0}
        for i, c in enumerate(closes)
    ]


def build_lagged_series(n_events=40):
    """
    REF jumps +0.30% at even steps; TGT follows with +0.25% one candle
    later. Between events both are flat. This is a textbook lag with
    strong forward capture.
    """
    ref_closes = [100.0]
    tgt_closes = [100.0]
    for _ in range(n_events):
        # event candle: ref jumps, tgt flat
        ref_closes.append(ref_closes[-1] * 1.0030)
        tgt_closes.append(tgt_closes[-1] * 1.0000001)  # epsilon: same UP direction
        # follow candle: ref flat, tgt catches up
        ref_closes.append(ref_closes[-1])
        tgt_closes.append(tgt_closes[-1] * 1.0025)
    return candles_from_closes(ref_closes), candles_from_closes(tgt_closes)


calibrator = CryptoLagCalibrator(round_trip_cost_pct=0.12, min_samples=30, min_win_rate=0.5)

# 1. Known lag structure is found and fitted at a sensible threshold
ref, tgt = build_lagged_series()
result = calibrator.calibrate_pair("REF", "TGT", ref, tgt)
fitted = result["fitted_threshold"]
stats = result["fitted_stats"]
print(f"fitted threshold: {fitted} | events={stats['events']} "
      f"win_rate={stats['win_rate']:.2f} mean_capture={stats['mean_capture_pct']:.3f}%")
assert result["is_historically_calibrated"] is True
assert fitted is not None and fitted <= 0.30, "should fit at or below the true 0.30% jump"
assert stats["events"] >= 30
assert stats["win_rate"] >= 0.5
assert stats["mean_capture_pct"] > 0.12

# 2. Pure noise-free flat series -> zero events -> honestly NOT calibrated
flat_a = candles_from_closes([100.0] * 100)
flat_b = candles_from_closes([200.0] * 100)
result = calibrator.calibrate_pair("A", "B", flat_a, flat_b)
print("flat series calibrated:", result["is_historically_calibrated"])
assert result["is_historically_calibrated"] is False
assert result["fitted_threshold"] is None
assert all(row["events"] == 0 for row in result["threshold_table"])

# 3. Anti-correlated series (opposite directions) -> no same-direction lag
up = candles_from_closes([100.0 * (1.003 ** i) for i in range(80)])
down = candles_from_closes([100.0 / (1.003 ** i) for i in range(80)])
result = calibrator.calibrate_pair("UP", "DOWN", up, down)
print("anti-correlated calibrated:", result["is_historically_calibrated"])
assert result["is_historically_calibrated"] is False

# 4. Lag exists but follow-through never beats costs -> not calibrated
ref_closes = [100.0]
tgt_closes = [100.0]
for _ in range(50):
    ref_closes.append(ref_closes[-1] * 1.0030)
    tgt_closes.append(tgt_closes[-1] * 1.0000001)
    ref_closes.append(ref_closes[-1])
    tgt_closes.append(tgt_closes[-1] * 1.0003)  # +0.03% capture < 0.12% cost
weak_ref = candles_from_closes(ref_closes)
weak_tgt = candles_from_closes(tgt_closes)
result = calibrator.calibrate_pair("REF", "WEAK", weak_ref, weak_tgt)
print("weak-capture calibrated:", result["is_historically_calibrated"])
assert result["is_historically_calibrated"] is False

# 5. Universe calibration: conservative (largest fitted across pairs), and
#    non-qualifying pairs don't poison qualifying ones
ref, tgt = build_lagged_series()
universe = calibrator.calibrate_universe({
    "REF": ref, "TGT": tgt, "FLAT": candles_from_closes([300.0] * len(ref))
})
print(f"universe: {universe['pairs_calibrated']}/{universe['pairs_total']} pairs, "
      f"fitted={universe['fitted_min_gap_percent']}")
assert universe["pairs_total"] == 6
assert universe["pairs_calibrated"] >= 1
assert universe["is_historically_calibrated"] is True
assert universe["fitted_min_gap_percent"] is not None
assert universe["scope"] == "crypto_lag_detection_only"
assert "Steel/gold" in universe["not_calibrated_note"]

# 6. Misaligned timestamps are dropped, not misused
short = candles_from_closes([100, 101, 102], start_ms=999)  # disjoint times
result = calibrator.calibrate_pair("A", "B", ref, short)
assert result["aligned_return_rows"] == 0
assert result["is_historically_calibrated"] is False
print("misaligned timestamps handled: OK")

# 7. Config validation
for bad in [
    {"threshold_grid": []},
    {"threshold_grid": [0.0, 0.1]},
    {"round_trip_cost_pct": -1},
    {"min_samples": 0},
    {"min_win_rate": 1.5},
]:
    try:
        CryptoLagCalibrator(**bad)
        raise AssertionError(f"expected ValueError for {bad}")
    except ValueError:
        pass
print("config validation: OK")

print("\nALL CRYPTO LAG CALIBRATOR TESTS PASSED")
