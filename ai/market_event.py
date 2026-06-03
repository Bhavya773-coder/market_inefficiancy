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
