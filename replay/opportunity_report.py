import redis
import json

from ai.opportunity_adapter import OpportunityAdapter

r = redis.Redis(host="localhost", port=6379, decode_responses=True)
adapter = OpportunityAdapter()

print("=== OPPORTUNITY FORMAT TEST ===")
print("")

keys = sorted(r.keys("memory:*:*"))

for key in keys[:10]:

    parts = key.split(":")

    if len(parts) < 3:
        continue

    data = json.loads(r.get(key))

    wins = data.get("wins", 0)
    losses = data.get("losses", 0)
    pnl = data.get("total_pnl", 0.0)
    trades = wins + losses

    if trades == 0:
        continue

    symbol = parts[1]
    strategy = parts[2]
    regime = parts[3] if len(parts) > 3 else "all"

    avg_pnl = pnl / trades

    ranked = {
        "symbol": symbol,
        "strategy": strategy,
        "regime": regime,
        "score": avg_pnl,
        "symbol_bias": 0.0,
        "strategy_bias": max(-1.0, min(1.0, avg_pnl / 200.0)),
        "regime_multiplier": 1.0,
        "change": 0.0,
        "volatility": 0.0,
        "timestamp": 0.0
    }

    opportunity = adapter.from_ranked_signal(ranked)

    print(opportunity.to_dict())
    print("-" * 40)
