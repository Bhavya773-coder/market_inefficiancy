class PaperExitDecision:
    """
    Represents a structured exit decision for an active paper position.
    """

    def __init__(
        self,
        symbol,
        action,
        reason,
        entry_price,
        current_price,
        quantity,
        unrealized_pnl,
        unrealized_pct,
        status="decision",
        metadata=None
    ):
        self.symbol = symbol
        self.action = action
        self.reason = reason
        self.entry_price = entry_price
        self.current_price = current_price
        self.quantity = quantity
        self.unrealized_pnl = unrealized_pnl
        self.unrealized_pct = unrealized_pct
        self.status = status
        self.metadata = metadata or {}

    def to_dict(self):
        """
        Returns a dictionary representation of the exit decision.
        """
        return {
            "symbol": self.symbol,
            "action": self.action,
            "reason": self.reason,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "quantity": self.quantity,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pct": self.unrealized_pct,
            "status": self.status,
            "metadata": self.metadata
        }

    @classmethod
    def from_evaluation(cls, evaluation):
        """
        Constructs a PaperExitDecision object from an evaluation result dictionary.
        """
        if evaluation is None:
            return None

        return cls(
            symbol=evaluation.get("symbol"),
            action=evaluation.get("action"),
            reason=evaluation.get("reason"),
            entry_price=evaluation.get("entry_price"),
            current_price=evaluation.get("current_price"),
            quantity=evaluation.get("quantity"),
            unrealized_pnl=evaluation.get("unrealized_pnl"),
            unrealized_pct=evaluation.get("unrealized_pct"),
            status="decision",
            metadata=evaluation
        )
