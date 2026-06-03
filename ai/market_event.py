class MarketEvent:

    def __init__(
        self,
        symbol,
        source,
        event_type,
        price,
        volume,
        timestamp,
        metadata=None
    ):
        self.symbol = symbol
        self.source = source
        self.event_type = event_type
        self.price = price
        self.volume = volume
        self.timestamp = timestamp
        self.metadata = metadata or {}

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "source": self.source,
            "event_type": self.event_type,
            "price": self.price,
            "volume": self.volume,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }

    @classmethod
    def from_quote(cls, quote):
        symbol = quote["symbol"]
        source = "market_quote"
        event_type = "live_quote"
        price = quote["last_price"]
        volume = quote.get("volume", 0)
        timestamp = quote.get("last_trade_time") or quote.get("timestamp")
        metadata = quote

        return cls(
            symbol=symbol,
            source=source,
            event_type=event_type,
            price=price,
            volume=volume,
            timestamp=timestamp,
            metadata=metadata
        )

