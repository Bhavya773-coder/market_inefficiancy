import time
from collections import defaultdict
from ai.event_bus import EventBus

bus = EventBus()

bus.create_group("detector_group")

history = defaultdict(list)

WINDOW = 20


def compute_baseline(symbol):
    values = history[symbol]
    if len(values) < 5:
        return 0
    return sum(values) / len(values)


def score_inefficiency(change, baseline):
    return abs(change - baseline)


print("=== INEFFICIENCY DETECTOR RUNNING ===")

while True:
    data = bus.read_ticks("detector_group", "detector_1")

    if data:
        for stream, messages in data:
            for msg_id, msg in messages:

                symbol = msg["symbol"]
                change = float(msg.get("change", 0))

                history[symbol].append(change)
                history[symbol] = history[symbol][-WINDOW:]

                baseline = compute_baseline(symbol)
                score = score_inefficiency(change, baseline)

                if score > 5:
                    signal = "TRADE_OPPORTUNITY"
                else:
                    signal = "NO_TRADE"

                event = {
                    "symbol": symbol,
                    "change": change,
                    "baseline": baseline,
                    "score": score,
                    "signal": signal,
                    "timestamp": time.time()
                }

                # publish to next stage
                bus.r.xadd("signal_stream", event)

                print(event)
