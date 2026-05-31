import random


class MockSteelConnector:

    def get_quote(self):

        india_price = random.randint(48000, 52000)

        futures_price = (
            india_price
            + random.randint(-1500, 2500)
        )

        return {
            "asset": "STEEL_HRC",
            "market_a": "India Physical",
            "market_b": "MCX Futures",
            "price_a": india_price,
            "price_b": futures_price
        }
