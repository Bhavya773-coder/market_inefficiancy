"""
Fits the lag-detection gap threshold (min_gap_percent) from REAL
historical candles instead of the heuristic default.

Method, deterministic and fully disclosed in the output:
- Align two instruments' candles by timestamp; compute per-candle
  close-to-close returns.
- A "lag event" at threshold g mirrors ai/lag_detector.py semantics:
  same direction, |ref return| - |tgt return| >= g.
- The event's outcome is the target's NEXT-candle return in the
  reference's direction ("forward capture") — the follow-through a
  paper trade entering at that candle's close could have captured.
- An event "wins" when forward capture exceeds the round-trip cost
  estimate.
- The fitted threshold is the SMALLEST grid value with at least
  min_samples events, win rate >= min_win_rate, and mean capture above
  cost.

If no grid threshold qualifies, the calibration honestly reports
is_historically_calibrated=False and the caller keeps the heuristic.
This calibrator is for crypto data only — steel/gold have no real data
source and must never be marked calibrated.
"""
from datetime import datetime, timezone

DEFAULT_THRESHOLD_GRID = [0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50]


class CryptoLagCalibrator:

    def __init__(
        self,
        threshold_grid=None,
        round_trip_cost_pct=0.12,
        min_samples=30,
        min_win_rate=0.5
    ):
        if threshold_grid is None:
            threshold_grid = DEFAULT_THRESHOLD_GRID
        self.threshold_grid = sorted(threshold_grid)
        if not self.threshold_grid or any(t <= 0 for t in self.threshold_grid):
            raise ValueError("threshold_grid must be non-empty with positive values")
        if round_trip_cost_pct < 0:
            raise ValueError("round_trip_cost_pct must be >= 0")
        if min_samples < 1:
            raise ValueError("min_samples must be >= 1")
        if not (0.0 <= min_win_rate <= 1.0):
            raise ValueError("min_win_rate must be in [0, 1]")
        self.round_trip_cost_pct = round_trip_cost_pct
        self.min_samples = min_samples
        self.min_win_rate = min_win_rate

    @staticmethod
    def _aligned_returns(candles_a, candles_b):
        """
        Returns list of (timestamp_ms, ret_a_pct, ret_b_pct) for
        consecutive timestamps present in BOTH series.
        """
        closes_a = {c["timestamp_ms"]: c["close"] for c in candles_a}
        closes_b = {c["timestamp_ms"]: c["close"] for c in candles_b}
        common = sorted(set(closes_a) & set(closes_b))
        rows = []
        for prev_ts, ts in zip(common, common[1:]):
            pa, ca = closes_a[prev_ts], closes_a[ts]
            pb, cb = closes_b[prev_ts], closes_b[ts]
            if pa <= 0 or pb <= 0:
                continue
            rows.append((
                ts,
                (ca - pa) / pa * 100.0,
                (cb - pb) / pb * 100.0
            ))
        return rows

    def evaluate_threshold(self, rows, threshold):
        """
        Scans aligned return rows for lag events at `threshold` and
        measures next-candle forward capture. Returns a stats dict.
        """
        def direction(x):
            # Mirrors ai/price_change_detector.py exactly.
            if x > 0:
                return "UP"
            if x < 0:
                return "DOWN"
            return "UNCHANGED"

        events = 0
        wins = 0
        captures = []
        # Need a next candle for the outcome -> stop one short.
        for i in range(len(rows) - 1):
            _, ref_ret, tgt_ret = rows[i]
            # Same lag semantics as ai/lag_detector.py: same direction and
            # reaction gap >= threshold.
            same_direction = direction(ref_ret) == direction(tgt_ret)
            gap = abs(ref_ret) - abs(tgt_ret)
            if not (same_direction and gap >= threshold and ref_ret != 0):
                continue

            events += 1
            sign = 1.0 if ref_ret > 0 else -1.0
            _, _, tgt_next = rows[i + 1]
            capture = sign * tgt_next  # % move in the lag direction
            captures.append(capture)
            if capture > self.round_trip_cost_pct:
                wins += 1

        mean_capture = sum(captures) / len(captures) if captures else 0.0
        sorted_caps = sorted(captures)
        median_capture = sorted_caps[len(sorted_caps) // 2] if sorted_caps else 0.0
        win_rate = wins / events if events else 0.0
        return {
            "threshold": threshold,
            "events": events,
            "wins": wins,
            "win_rate": win_rate,
            "mean_capture_pct": mean_capture,
            "median_capture_pct": median_capture
        }

    def calibrate_pair(self, ref_name, tgt_name, ref_candles, tgt_candles):
        rows = self._aligned_returns(ref_candles, tgt_candles)
        table = [self.evaluate_threshold(rows, t) for t in self.threshold_grid]

        fitted = None
        for stats in table:  # grid is sorted ascending -> smallest qualifying
            if (
                stats["events"] >= self.min_samples
                and stats["win_rate"] >= self.min_win_rate
                and stats["mean_capture_pct"] > self.round_trip_cost_pct
            ):
                fitted = stats
                break

        return {
            "reference": ref_name,
            "target": tgt_name,
            "aligned_return_rows": len(rows),
            "data_start_ms": rows[0][0] if rows else None,
            "data_end_ms": rows[-1][0] if rows else None,
            "round_trip_cost_pct": self.round_trip_cost_pct,
            "min_samples": self.min_samples,
            "min_win_rate": self.min_win_rate,
            "threshold_table": table,
            "fitted_threshold": fitted["threshold"] if fitted else None,
            "fitted_stats": fitted,
            "is_historically_calibrated": fitted is not None
        }

    def calibrate_universe(self, candles_by_instrument):
        """
        Calibrates every ordered pair and picks the strictest (largest)
        fitted threshold across qualifying pairs — conservative: the
        session threshold must be defensible for every traded pair.
        """
        names = sorted(candles_by_instrument)
        if len(names) < 2:
            raise ValueError("need at least 2 instruments")

        pair_results = []
        for ref in names:
            for tgt in names:
                if ref == tgt:
                    continue
                pair_results.append(self.calibrate_pair(
                    ref, tgt, candles_by_instrument[ref], candles_by_instrument[tgt]
                ))

        fitted_values = [
            r["fitted_threshold"] for r in pair_results
            if r["fitted_threshold"] is not None
        ]
        overall = max(fitted_values) if fitted_values else None

        return {
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
            "method": "next_candle_forward_capture_vs_round_trip_cost",
            "instruments": names,
            "pair_results": pair_results,
            "pairs_total": len(pair_results),
            "pairs_calibrated": len(fitted_values),
            "fitted_min_gap_percent": overall,
            "is_historically_calibrated": overall is not None,
            "scope": "crypto_lag_detection_only",
            "not_calibrated_note": (
                "Steel/gold detectors remain is_historically_calibrated=False; "
                "no real commodity data source exists."
            )
        }
