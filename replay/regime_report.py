import redis
import json

r = redis.Redis(
    host="localhost",
    port=6379,
    decode_responses=True
)

rows = []

for key in r.keys("memory:*:*:*"):

    data = json.loads(
        r.get(key)
    )

    parts = key.split(":")

    symbol = parts[1]
    strategy = parts[2]
    regime = parts[3]

    wins = data["wins"]
    losses = data["losses"]
    pnl = data["total_pnl"]

    trades = wins + losses

    if trades == 0:
        continue

    rows.append({

        "symbol": symbol,
        "strategy": strategy,
        "regime": regime,

        "trades": trades,

        "win_rate":
        wins / trades * 100,

        "total_pnl":
        pnl,

        "avg_pnl":
        pnl / trades
    })

rows.sort(
    key=lambda x: x["avg_pnl"],
    reverse=True
)

print(
    "=== REGIME PERFORMANCE REPORT ==="
)

for r in rows:

    print("")
    print(
        f"{r['symbol']} | "
        f"{r['strategy']} | "
        f"{r['regime']}"
    )

    print(
        "Trades:",
        r["trades"]
    )

    print(
        "Win Rate:",
        round(
            r["win_rate"],
            2
        ),
        "%"
    )

    print(
        "Total PnL:",
        round(
            r["total_pnl"],
            4
        )
    )

    print(
        "Avg PnL:",
        round(
            r["avg_pnl"],
            4
        )
    )
