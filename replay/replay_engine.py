import json
import time

LOG_FILE = "trade_log.jsonl"

print("=== REPLAY ENGINE ===")

with open(LOG_FILE, "r") as f:

    for line in f:

        trade = json.loads(line)

        print("REPLAY:", trade)

        time.sleep(0.2)
