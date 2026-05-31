import redis
import json
import time


class EquityMemory:

    def __init__(self):
        self.r = redis.Redis(
            host="localhost",
            port=6379,
            decode_responses=True
        )

        self.key = "portfolio:equity"

    def record(self, equity, return_pct):
        existing = self.r.get(self.key)

        if existing:
            data = json.loads(existing)
        else:
            data = {
                "starting_equity": equity,
                "peak_equity": equity,
                "current_equity": equity,
                "return_pct": return_pct,
                "max_drawdown_pct": 0.0,
                "updates": 0,
                "last_updated": time.time()
            }

        peak = max(
            data.get("peak_equity", equity),
            equity
        )

        drawdown_pct = 0.0

        if peak > 0:
            drawdown_pct = ((peak - equity) / peak) * 100

        max_drawdown_pct = max(
            data.get("max_drawdown_pct", 0.0),
            drawdown_pct
        )

        data["peak_equity"] = peak
        data["current_equity"] = equity
        data["return_pct"] = return_pct
        data["max_drawdown_pct"] = round(max_drawdown_pct, 4)
        data["updates"] = data.get("updates", 0) + 1
        data["last_updated"] = time.time()

        self.r.set(
            self.key,
            json.dumps(data)
        )

    def get(self):
        existing = self.r.get(self.key)

        if not existing:
            return None

        return json.loads(existing)
