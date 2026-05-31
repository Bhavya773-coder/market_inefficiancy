import json
from collections import defaultdict

DATA_FILE = "strategy_dataset.jsonl"

symbol_scores = defaultdict(list)

def compute_score(event):
    # base components
    change = abs(event["change"])
    volatility = event["volatility"]
    latency = event["total_latency"]
    duration = event["signal_duration"]

    # core idea: reward movement + persistence, penalize latency
    movement_score = change * 0.6
    volatility_score = volatility * 0.4
    latency_penalty = latency * 50

    persistence_bonus = duration * 20

    score = movement_score + volatility_score + persistence_bonus - latency_penalty

    return round(score, 2)

with open(DATA_FILE, "r") as f:
    for line in f:
        event = json.loads(line)

        score = compute_score(event)

        symbol_scores[event["symbol"]].append(score)

print("=== STRATEGY SCORING ENGINE v2 ===")

for symbol, scores in symbol_scores.items():
    avg_score = sum(scores) / len(scores)

    print(symbol)
    print("  samples:", len(scores))
    print("  avg_edge_score:", round(avg_score, 2))
    print("  max_score:", round(max(scores), 2))
    print("  min_score:", round(min(scores), 2))
    print("")
