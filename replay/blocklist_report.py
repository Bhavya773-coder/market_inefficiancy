import redis
import json

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

print("=== STRATEGY BLOCKLIST REPORT ===")

for key in sorted(r.keys("memory:*:*")):
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

    wins = data["wins"]
    losses = data["losses"]
    pnl = data["total_pnl"]
    trades = wins + losses

    if trades == 0:
        continue

    avg_pnl = pnl / trades

    if trades >= 5 and avg_pnl < 0:
        print("")
        print(f"BLOCK CANDIDATE: {symbol} | {strategy} | {regime}")
        print("Trades:", trades)
        print("Avg PnL:", round(avg_pnl, 4))
        print("Total PnL:", round(pnl, 4))
