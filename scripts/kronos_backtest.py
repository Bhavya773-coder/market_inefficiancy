"""
Phase-0 validation: does a Kronos forecast filter improve the crypto lag
strategy's LONG entries?

The live strategy (live/run_live_crypto_paper_trading.py) buys a symbol that
lagged behind a reference move, then exits on take-profit / stop-loss. The
cost gate already checks "is this profitable IF it works"; nothing checks
"is it likely to work". This script measures whether Kronos's directional
forecast adds that missing edge.

Method (walk-forward over real crypto.com 1m candles, no simulated data):
  for each test point t:
    - feed Kronos candles[t-lookback : t], ask for a `horizon`-candle forecast
    - simulate a LONG entry at close[t] with the live runner's real
      take_profit_pct / stop_loss_pct, walking candles t+1..t+horizon and
      checking intrabar high/low for a touch
    - record the realized outcome and whether Kronos predicted UP
  then compare the win rate of ALL longs vs only Kronos-approved longs.

If the Kronos-approved subset is not meaningfully better, the filter is not
worth wiring into the live path.

    PYTHONPATH=. python scripts/kronos_backtest.py
"""
import argparse
import json
import time

import pandas as pd

from connectors.crypto_connector import CryptoConnector
from vendor.kronos import Kronos, KronosTokenizer, KronosPredictor

DEFAULT_SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "LTC_USDT"]
OHLCV = ["open", "high", "low", "close", "volume"]


def simulate_long(candles, entry_idx, horizon, take_profit_pct, stop_loss_pct):
    """
    Replays the live runner's exit rule on real candles.

    Returns (outcome, pnl_pct) where outcome is "win" | "loss" | "flat".
    Stop-loss is checked before take-profit within the same candle: when a
    single bar spans both levels we cannot know which printed first, so we
    assume the adverse fill. That keeps the backtest from flattering itself.
    """
    entry = candles["close"].iloc[entry_idx]
    tp = entry * (1.0 + take_profit_pct / 100.0)
    sl = entry * (1.0 - stop_loss_pct / 100.0)
    for i in range(entry_idx + 1, min(entry_idx + 1 + horizon, len(candles))):
        low = candles["low"].iloc[i]
        high = candles["high"].iloc[i]
        if low <= sl:
            return "loss", -stop_loss_pct
        if high >= tp:
            return "win", take_profit_pct
    exit_price = candles["close"].iloc[min(entry_idx + horizon, len(candles) - 1)]
    pnl = (exit_price - entry) / entry * 100.0
    return ("win" if pnl > 0 else "loss" if pnl < 0 else "flat"), pnl


def load_candles(connector, symbol, timeframe, count):
    raw = connector.get_candlesticks(symbol, timeframe=timeframe, count=count)
    df = pd.DataFrame(raw)
    df["timestamps"] = pd.to_datetime(df["timestamp_ms"], unit="ms")
    return df


def run(args):
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(model, tokenizer, device=args.device,
                                max_context=args.max_context)

    connector = CryptoConnector()
    data = {}
    for sym in args.symbols:
        data[sym] = load_candles(connector, sym, args.timeframe, args.count)
        print(f"{sym}: {len(data[sym])} candles")

    # Test points shared across symbols so each step can be one batched call.
    n = min(len(df) for df in data.values())
    starts = list(range(args.lookback, n - args.horizon, args.stride))
    print(f"\n{len(starts)} test points/symbol x {len(args.symbols)} symbols "
          f"= {len(starts) * len(args.symbols)} samples "
          f"(lookback={args.lookback}, horizon={args.horizon})")

    records = []
    t_start = time.time()
    for step, t in enumerate(starts, 1):
        df_list, xt_list, yt_list, syms = [], [], [], []
        for sym, df in data.items():
            df_list.append(df.iloc[t - args.lookback:t][OHLCV].reset_index(drop=True))
            xt_list.append(df.iloc[t - args.lookback:t]["timestamps"].reset_index(drop=True))
            yt_list.append(df.iloc[t:t + args.horizon]["timestamps"].reset_index(drop=True))
            syms.append(sym)

        preds = predictor.predict_batch(
            df_list=df_list, x_timestamp_list=xt_list, y_timestamp_list=yt_list,
            pred_len=args.horizon, T=args.temperature, top_p=args.top_p,
            sample_count=args.sample_count, verbose=False
        )

        for sym, x_df, pred in zip(syms, df_list, preds):
            last_close = x_df["close"].iloc[-1]
            pred_close = pred["close"].iloc[-1]
            pred_move_pct = (pred_close - last_close) / last_close * 100.0
            outcome, pnl = simulate_long(
                data[sym], t - 1, args.horizon,
                args.take_profit_pct, args.stop_loss_pct
            )
            records.append({
                "symbol": sym, "t": t,
                "kronos_up": bool(pred_move_pct > 0),
                "kronos_move_pct": pred_move_pct,
                "outcome": outcome, "pnl_pct": pnl,
            })
        if step % 5 == 0 or step == len(starts):
            el = time.time() - t_start
            print(f"  step {step}/{len(starts)}  ({el:.0f}s elapsed, "
                  f"{el / step:.1f}s/step)")

    return records


def report(records, min_conviction):
    def stats(rows, label):
        if not rows:
            print(f"{label:<34} (no samples)")
            return None
        wins = sum(1 for r in rows if r["outcome"] == "win")
        total_pnl = sum(r["pnl_pct"] for r in rows)
        wr = wins / len(rows) * 100.0
        avg = total_pnl / len(rows)
        print(f"{label:<34} n={len(rows):<5} win={wr:5.1f}%  "
              f"avg={avg:+.4f}%  total={total_pnl:+.2f}%")
        return {"n": len(rows), "win_rate": wr, "avg_pnl_pct": avg,
                "total_pnl_pct": total_pnl}

    print("\n" + "=" * 78)
    print("RESULT — every row is a simulated LONG with the live TP/SL rule")
    print("=" * 78)
    base = stats(records, "ALL longs (current strategy)")
    approved = stats([r for r in records if r["kronos_up"]],
                     "Kronos says UP (filter ON)")
    rejected = stats([r for r in records if not r["kronos_up"]],
                     "Kronos says DOWN (filter skips)")
    conv = stats([r for r in records
                  if r["kronos_up"] and r["kronos_move_pct"] >= min_conviction],
                 f"Kronos UP & >= {min_conviction}% conviction")

    print("\nDirectional accuracy (did price end up where Kronos said?)")
    correct = sum(1 for r in records
                  if r["kronos_up"] == (r["pnl_pct"] > 0))
    print(f"  {correct}/{len(records)} = {correct / len(records) * 100:.1f}% "
          f"(50% = coin flip)")

    print("\nVERDICT")
    if base and approved:
        d_wr = approved["win_rate"] - base["win_rate"]
        d_avg = approved["avg_pnl_pct"] - base["avg_pnl_pct"]
        print(f"  win-rate change:  {d_wr:+.1f} pp")
        print(f"  avg-PnL change:   {d_avg:+.4f} pp per trade")
        if d_avg > 0 and d_wr > 0:
            print("  -> filter helps on this sample. Proceed to shadow mode.")
        else:
            print("  -> filter does NOT help on this sample. Do not wire in.")
    return {"all": base, "kronos_up": approved, "kronos_down": rejected,
            "high_conviction": conv}


def main():
    p = argparse.ArgumentParser(description="Kronos filter validation (offline)")
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--timeframe", default="1m")
    p.add_argument("--count", type=int, default=300)
    p.add_argument("--lookback", type=int, default=180)
    p.add_argument("--horizon", type=int, default=15)
    p.add_argument("--stride", type=int, default=3)
    p.add_argument("--take-profit-pct", type=float, default=0.5)
    p.add_argument("--stop-loss-pct", type=float, default=0.25)
    p.add_argument("--min-conviction", type=float, default=0.1)
    p.add_argument("--model", default="NeoQuasar/Kronos-small")
    p.add_argument("--tokenizer", default="NeoQuasar/Kronos-Tokenizer-base")
    p.add_argument("--device", default="cpu")
    p.add_argument("--max-context", type=int, default=512)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--top-p", type=float, default=0.9)
    p.add_argument("--sample-count", type=int, default=1)
    p.add_argument("--out", default=None)
    args = p.parse_args()

    records = run(args)
    summary = report(records, args.min_conviction)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "records": records}, f, indent=1)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
