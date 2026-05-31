import time

from ai.event_bus import EventBus

bus = EventBus()

bus.create_group(
    "market_stream",
    "feature_group"
)

print("=== FEATURE ENGINE RUNNING ===")

last_price = {}

while True:

    data = bus.read(
        "market_stream",
        "feature_group",
        "feature_1"
    )

    if data:

        for _, messages in data:

            for _, msg in messages:

                symbol = msg["symbol"]

                price = float(msg["price"])

                previous = last_price.get(
                    symbol,
                    price
                )

                change = price - previous

                volatility = abs(change)

                signal = (
                    "TRADE"
                    if volatility > 100
                    else "NO_TRADE"
                )

                features = {
                    "symbol": symbol,
                    "price": price,
                    "change": change,
                    "volatility": volatility,
                    "signal": signal,
                    "timestamp": time.time()
                }

                bus.publish(
                    "feature_stream",
                    features
                )

                print(
                    "FEATURES:",
                    features
                )

                last_price[symbol] = price
