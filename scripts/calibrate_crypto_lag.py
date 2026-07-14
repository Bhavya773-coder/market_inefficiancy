"""
Fits the crypto lag-detection threshold from REAL Crypto.com historical
candles and writes the evidence-carrying result to
storage/calibration/crypto_lag_calibration.json.

Usage:
    PYTHONPATH=. python scripts/calibrate_crypto_lag.py \
        [--instruments BTC_USDT,ETH_USDT,...] [--timeframe 1m] [--count 300]

The output file is only marked is_historically_calibrated=True when at
least one instrument pair genuinely qualified on real data. Steel/gold
are out of scope by design — they have no real data source.
"""
import argparse
import json
import pathlib

from connectors.crypto_connector import CryptoConnector
from ai.crypto_lag_calibrator import CryptoLagCalibrator

DEFAULT_INSTRUMENTS = "BTC_USDT,ETH_USDT,SOL_USDT,XRP_USDT,LTC_USDT"
OUTPUT_PATH = "storage/calibration/crypto_lag_calibration.json"


def main():
    parser = argparse.ArgumentParser(description="Calibrate crypto lag threshold from real candles")
    parser.add_argument("--instruments", default=DEFAULT_INSTRUMENTS)
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--round-trip-cost-pct", type=float, default=0.12)
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--min-win-rate", type=float, default=0.5)
    parser.add_argument("--output", default=OUTPUT_PATH)
    args = parser.parse_args()

    instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
    connector = CryptoConnector()

    print(f"Fetching {args.count} x {args.timeframe} candles for {len(instruments)} instruments...")
    candles = {}
    for name in instruments:
        candles[name] = connector.get_candlesticks(name, args.timeframe, args.count)
        print(f"  {name}: {len(candles[name])} candles "
              f"({candles[name][0]['timestamp_ms']} .. {candles[name][-1]['timestamp_ms']})")

    calibrator = CryptoLagCalibrator(
        round_trip_cost_pct=args.round_trip_cost_pct,
        min_samples=args.min_samples,
        min_win_rate=args.min_win_rate
    )
    result = calibrator.calibrate_universe(candles)
    result["timeframe"] = args.timeframe
    result["candles_per_instrument"] = args.count

    out = pathlib.Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\npairs calibrated: {result['pairs_calibrated']}/{result['pairs_total']}")
    print(f"fitted_min_gap_percent: {result['fitted_min_gap_percent']}")
    print(f"is_historically_calibrated: {result['is_historically_calibrated']}")
    for pair in result["pair_results"]:
        tag = pair["fitted_threshold"] if pair["fitted_threshold"] is not None else "-"
        print(f"  {pair['reference']:>9} -> {pair['target']:<9} rows={pair['aligned_return_rows']:<4} fitted={tag}")
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
