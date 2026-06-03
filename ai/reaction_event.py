class ReactionEvent:

    def __init__(
        self,
        symbol,
        source,
        reaction_type,
        direction,
        absolute_change,
        percent_change,
        current_price,
        previous_price,
        timestamp,
        metadata=None
    ):
        self.symbol = symbol
        self.source = source
        self.reaction_type = reaction_type
        self.direction = direction
        self.absolute_change = absolute_change
        self.percent_change = percent_change
        self.current_price = current_price
        self.previous_price = previous_price
        self.timestamp = timestamp
        self.metadata = metadata or {}

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "source": self.source,
            "reaction_type": self.reaction_type,
            "direction": self.direction,
            "absolute_change": self.absolute_change,
            "percent_change": self.percent_change,
            "current_price": self.current_price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }

    @classmethod
    def from_price_change(cls, change):
        symbol = change["symbol"]
        source = "price_change_detector"
        reaction_type = "price_reaction"
        direction = change["direction"]
        absolute_change = change["absolute_change"]
        percent_change = change["percent_change"]
        current_price = change["current_price"]
        previous_price = change["previous_price"]
        timestamp = change["timestamp"]
        metadata = change

        return cls(
            symbol=symbol,
            source=source,
            reaction_type=reaction_type,
            direction=direction,
            absolute_change=absolute_change,
            percent_change=percent_change,
            current_price=current_price,
            previous_price=previous_price,
            timestamp=timestamp,
            metadata=metadata
        )
