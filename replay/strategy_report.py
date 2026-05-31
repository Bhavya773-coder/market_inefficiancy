import redis
import json

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

rows = []

for key in r.keys("memory:*:*"):
    data = json.loads(r.get(key))

    parts = key.split(":")

    if len(parts) < 3:
        continue

    symbol = parts[1]
    strategy = parts[2]

    if len(parts) >= 4:
        regime = parts[3]
    else:
        regime = "all"

    wins = data.get("wins", 0)
    losses = data.get("losses", 0)
    pnl = data.get("total_pnl", 0.0)
    trades = wins + losses

    if trades == 0:
        continue

    rows.append(
        {
            "symbol": symbol,
            "strategy": strategy,
            "regime": regime,
            "trades": trades,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / trades * 100,
            "total_pnl": pnl,
            "avg_pnl": pnl / trades,
        }
    )

rows.sort(key=lambda x: x["avg_pnl"], reverse=True)

print("=== STRATEGY PERFORMANCE RANKING ===")

for r in rows:
    print("")
    print(f"{r['symbol']} | {r['strategy']} | {r['regime']}")
    print("Trades:", r["trades"])
    print("Win Rate:", round(r["win_rate"], 2), "%")
    print("Total PnL:", round(r["total_pnl"], 4))
    print("Avg PnL:", round(r["avg_pnl"], 4))
