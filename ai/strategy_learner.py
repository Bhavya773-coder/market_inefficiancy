import json
from collections import defaultdict

DATA_FILE = "strategy_dataset.jsonl"

total = 0
executables = 0
by_symbol = defaultdict(int)
by_signal = defaultdict(int)

latencies = []

with open(DATA_FILE, "r") as f:
    for line in f:
        data = json.loads(line)
        total += 1

        symbol = data["symbol"]
        signal = data["signal"]
        status = data["execution_status"]
        latency = data["total_latency"]

        by_symbol[symbol] += 1
        by_signal[signal] += 1
        latencies.append(latency)

        if status == "EXECUTABLE":
            executables += 1

print("=== STRATEGY LEARNING REPORT v1 ===")
print(f"Total samples: {total}")
print(f"Executable opportunities: {executables}")
print(f"Execution rate: {round((executables/total)*100, 2) if total else 0}%")

print("\n--- Signal Distribution ---")
for k, v in by_signal.items():
    print(k, ":", v)

print("\n--- Symbol Distribution ---")
for k, v in by_symbol.items():
    print(k, ":", v)

if latencies:
    print("\n--- Latency Stats ---")
    print("Avg latency:", round(sum(latencies)/len(latencies), 3))
    print("Max latency:", round(max(latencies), 3))
    print("Min latency:", round(min(latencies), 3))
