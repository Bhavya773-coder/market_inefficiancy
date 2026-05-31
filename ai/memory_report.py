import redis
import json

r = redis.Redis(
    host="localhost",
    port=6379,
    decode_responses=True
)

keys = r.keys("memory:*")

print("=== LEARNING MEMORY REPORT ===")

for key in keys:

    data = json.loads(r.get(key))

    symbol = key.replace(
        "memory:",
        ""
    )

    wins = data["wins"]
    losses = data["losses"]
    total_pnl = data["total_pnl"]

    trades = wins + losses

    win_rate = (
        (wins / trades) * 100
        if trades
        else 0
    )

    avg_pnl = (
        total_pnl / trades
        if trades
        else 0
    )

    print("")
    print(symbol)
    print("Trades:", trades)
    print("Wins:", wins)
    print("Losses:", losses)
    print(
        "Win Rate:",
        round(win_rate, 2),
        "%"
    )

    print(
        "Total PnL:",
        round(total_pnl, 4)
    )

    print(
        "Avg PnL:",
        round(avg_pnl, 4)
    )
