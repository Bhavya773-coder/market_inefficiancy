import json
from collections import defaultdict

class TradeMemory:
    def __init__(self):
        self.stats = defaultdict(lambda: {
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0
        })

    def record(self, symbol, pnl):
        s = self.stats[symbol]

        s["total_pnl"] += pnl

        if pnl > 0:
            s["wins"] += 1
        else:
            s["losses"] += 1

    def score_bias(self, symbol):
        s = self.stats[symbol]
        total = s["wins"] + s["losses"]

        if total == 0:
            return 0

        return s["total_pnl"] / total

    def dump(self):
        return dict(self.stats)
