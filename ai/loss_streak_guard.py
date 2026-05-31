import redis
import json
import time


class LossStreakGuard:

    def __init__(self):
        self.r = redis.Redis(
            host="localhost",
            port=6379,
            decode_responses=True
        )

        self.max_loss_streak = 3
        self.cooldown_seconds = 60

    def _key(self, symbol, strategy, regime):
        return f"loss_streak:{symbol}:{strategy}:{regime}"

    def record_result(self, symbol, strategy, regime, pnl):
        key = self._key(symbol, strategy, regime)

        existing = self.r.get(key)

        if existing:
            data = json.loads(existing)
        else:
            data = {
                "loss_streak": 0,
                "blocked_until": 0
            }

        data.setdefault("loss_streak", 0)
        data.setdefault("blocked_until", 0)

        if pnl < 0:
            data["loss_streak"] += 1
        else:
            data["loss_streak"] = 0
            data["blocked_until"] = 0

        if data["loss_streak"] >= self.max_loss_streak:
            data["blocked_until"] = time.time() + self.cooldown_seconds

        self.r.set(key, json.dumps(data))

    def is_blocked(self, symbol, strategy, regime):
        key = self._key(symbol, strategy, regime)

        existing = self.r.get(key)

        if not existing:
            return False

        data = json.loads(existing)

        data.setdefault("loss_streak", 0)
        data.setdefault("blocked_until", 0)

        now = time.time()

        if data["blocked_until"] > now:
            return True

        if data["blocked_until"] > 0 and data["blocked_until"] <= now:
            data["loss_streak"] = 0
            data["blocked_until"] = 0
            self.r.set(key, json.dumps(data))
            return False

        return False

    def get_streak(self, symbol, strategy, regime):
        key = self._key(symbol, strategy, regime)

        existing = self.r.get(key)

        if not existing:
            return 0

        data = json.loads(existing)
        return data.get("loss_streak", 0)
