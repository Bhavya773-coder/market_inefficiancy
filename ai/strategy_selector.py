import json
from collections import defaultdict

DATA_FILE = "strategy_dataset.jsonl"

symbol_scores = defaultdict(list)

def compute_score(event):
    change = abs(event["change"])
    volatility = event["volatility"]
    latency = event["total_latency"]
    duration = event["signal_duration"]

    movement_score = change * 0.6
    volatility_score = volatility * 0.4
    persistence_bonus = duration * 20
    latency_penalty = latency * 50

    return movement_score + volatility_score + persistence_bonus - latency_penalty


with open(DATA_FILE, "r") as f:
    for line in f:
        event = json.loads(line)
        score = compute_score(event)
        symbol_scores[event["symbol"]].append(score)

# compute averages
avg_scores = {}

for symbol, scores in symbol_scores.items():
    avg_scores[symbol] = sum(scores) / len(scores)

# rank symbols
ranked = sorted(avg_scores.items(), key=lambda x: x[1], reverse=True)

print("=== STRATEGY SELECTION ENGINE v3 ===\n")

print("Symbol Rankings (Edge Strength):")
for sym, score in ranked:
    print(sym, "=>", round(score, 2))

print("\n--- DECISION ---")

best_symbol, best_score = ranked[0]

THRESHOLD = 80  # minimum edge required to trade

if best_score >= THRESHOLD:
    decision = "TRADE"
else:
    decision = "NO_TRADE"

print("Best Symbol:", best_symbol)
print("Best Score:", round(best_score, 2))
print("Decision:", decision)
