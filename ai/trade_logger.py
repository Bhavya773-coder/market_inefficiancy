import json
import time
import redis

r = redis.Redis(
    host="localhost",
    port=6379,
    decode_responses=True
)

LOG_FILE = "trade_log.jsonl"

print("=== TRADE LOGGER RUNNING ===")

last_id = "0-0"

while True:

    data = r.xread(
        {"execution_stream": last_id},
        block=1000,
        count=10
    )

    if data:

        for stream, messages in data:

            for message_id, msg in messages:

                last_id = message_id

                msg["logged_at"] = time.time()

                with open(
                    LOG_FILE,
                    "a"
                ) as f:

                    f.write(
                        json.dumps(msg)
                        + "\n"
                    )

                print(
                    "LOGGED:",
                    msg
                )
