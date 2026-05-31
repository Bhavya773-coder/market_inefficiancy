import json
import random
from collections import defaultdict

DATA_FILE = "strategy_dataset.jsonl"
FEEDBACK_FILE = "trade_feedback.jsonl"

# adaptive weights (this is the "learning brain")
weights = {
    "change": 0.6,
    "volatility": 0.4,
    "duration": 20,
    "latency": -50
}

def compute_score(event):
    return (
        abs(event["change"]) * weights["change"]
        + event["volatility"] * weights["volatility"]
        + event["signal_duration"] * weights["duration"]
        + event["total_latency"] * weights["latency"]
    )

def adjust_weights(pnl):
    # simple reinforcement logic
    if pnl > 0:
        weights["change"] += 0.01
        weights["duration"] += 0.5
        weights["latency"] -= 0.5
    else:
        weights["change"] -= 0.01
        weights["duration"] -= 0.5
        weights["latency"] += 0.5

    # clamp stability
    weights["change"] = max(0.1, weights["change"])
    weights["duration"] = max(1, weights["duration"])
    weights["latency"] = min(-1, weights["latency"])


def simulate_trade(symbol, score):
    # execution model
    slippage = random.uniform(0.1, 2.5)
    success_prob = max(0.2, 1 - slippage / 3)

    filled = random.random() < success_prob

    if filled:
        pnl = random.uniform(-2, 3) * score / 100
    else:
        pnl = 0

    return pnl


def load_data():
    data = defaultdict(list)

    with open(DATA_FILE, "r") as f:
        for line in f:
            e = json.loads(line)
            data[e["symbol"]].append(e)

    return data


def run_cycle():
    data = load_data()

    best_symbol = None
    best_score = -999

    # evaluate all symbols
    for symbol, events in data.items():
        scores = [compute_score(e) for e in events]
        avg_score = sum(scores) / len(scores)

        if avg_score > best_score:
            best_score = avg_score
            best_symbol = symbol

    print("\n=== ADAPTIVE ENGINE v5 ===")
    print("Weights:", weights)
    print("Best Symbol:", best_symbol)
    print("Score:", round(best_score, 2))

    # execute trade
    pnl = simulate_trade(best_symbol, best_score)

    print("PnL:", round(pnl, 3))

    # learn from outcome
    adjust_weights(pnl)

    print("Updated Weights:", weights)


if __name__ == "__main__":
    run_cycle()
