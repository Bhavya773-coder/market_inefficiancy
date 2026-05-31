import time
import random

from ai.event_bus import EventBus

bus = EventBus()

symbols = {
    "RELIANCE": {"base": 2800, "vol": 18},
    "TCS": {"base": 3900, "vol": 12},
    "INFY": {"base": 1500, "vol": 10},
    "HDFCBANK": {"base": 1650, "vol": 8},
    "ICICIBANK": {"base": 1100, "vol": 9},
    "SBIN": {"base": 800, "vol": 12},
    "LT": {"base": 3600, "vol": 16},
    "TATAMOTORS": {"base": 950, "vol": 15},
    "AXISBANK": {"base": 1150, "vol": 9},
    "MARUTI": {"base": 12500, "vol": 35}
}

prices = {
    symbol: data["base"]
    for symbol, data in symbols.items()
}

print("=== LIVE TICK PRODUCER RUNNING ===")

while True:

    symbol = random.choice(list(symbols.keys()))
    profile = symbols[symbol]

    drift = random.uniform(-0.2, 0.2)
    shock = random.gauss(0, profile["vol"])

    prices[symbol] = max(
        1,
        prices[symbol] + drift + shock
    )

    event = {
        "symbol": symbol,
        "price": str(round(prices[symbol], 2)),
        "timestamp": str(time.time())
    }

    bus.publish("market_stream", event)

    print("PUBLISHED:", event)

    time.sleep(1)
