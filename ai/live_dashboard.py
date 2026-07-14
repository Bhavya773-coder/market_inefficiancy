import redis
import json
import time
import os

r = redis.Redis(host="localhost", port=6379, decode_responses=True)


def clear():
    os.system("clear")


def clamp(v):
    return max(-1.0, min(1.0, v))


while True:
    clear()

    print("=== ADAPTIVE TRADING BRAIN DASHBOARD ===")
    print("")

    try:
        equity_raw = r.get("portfolio:equity")

        if equity_raw:
            equity = json.loads(equity_raw)

            print("=== PORTFOLIO EQUITY ===")
            print("Current Equity:", round(equity.get("current_equity", 0), 2))
            print("Peak Equity:", round(equity.get("peak_equity", 0), 2))
            print("Return %:", equity.get("return_pct", 0))
            print("Max Drawdown %:", equity.get("max_drawdown_pct", 0))
            print("Equity Updates:", equity.get("updates", 0))
            print("-" * 40)
            print("")

        regime_raw = r.get("cross_metal:state")
        if regime_raw:
            regime_data = json.loads(regime_raw)
            print("=== CROSS-METAL REGIME ===")
            print("Current Regime:", regime_data.get("regime", "UNKNOWN"))
            print("Observed At:", regime_data.get("observed_at", "UNKNOWN"))
            print("Is Synchronized:", regime_data.get("is_synchronized", False))
            print("Timestamp Gap:", regime_data.get("timestamp_gap_seconds", 0.0), "s")
            print("Gold Context:", regime_data.get("gold_context", "UNKNOWN"), f"({regime_data.get('gold_support_score')})")
            print("Steel Context:", regime_data.get("steel_context", "UNKNOWN"), f"({regime_data.get('steel_support_score')})")
            print("-" * 40)
            print("")

        keys = sorted(r.keys("memory:*"))

        for key in keys:
            data = json.loads(r.get(key))
            name = key.replace("memory:", "")

            wins = data.get("wins", 0)
            losses = data.get("losses", 0)
            pnl = data.get("total_pnl", 0)
            trades = wins + losses

            if trades == 0:
                continue

            win_rate = wins / trades * 100
            raw_bias = pnl / trades
            safe_bias = clamp(raw_bias)

            print(name)
            print("Trades:", trades)
            print("Win Rate:", round(win_rate, 2), "%")
            print("Total PnL:", round(pnl, 4))
            print("Safe Bias:", round(safe_bias, 4))
            print("-" * 40)

    except redis.exceptions.ConnectionError:
        print("WARNING: Redis connection failed. Ensure Redis is running on localhost:6379.")
        print("-" * 40)

    print("")
    print("Lifecycle active: OPEN → HOLD → CLOSE")
    print("Refresh: 2 sec")

    time.sleep(2)

