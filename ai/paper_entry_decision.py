class PaperEntryDecision:
    """
    Represents a structured decision about whether a paper candidate should be allowed to enter.
    """

    def __init__(
        self,
        asset,
        action,
        reason,
        score,
        confidence,
        gross_edge_pct,
        total_cost_pct,
        net_edge_pct,
        quantity=1,
        price=None,
        status="entry_decision",
        metadata=None
    ):
        self.asset = asset
        self.action = action
        self.reason = reason
        self.score = score
        self.confidence = confidence
        self.gross_edge_pct = gross_edge_pct
        self.total_cost_pct = total_cost_pct
        self.net_edge_pct = net_edge_pct
        self.quantity = quantity
        self.price = price
        self.status = status
        self.metadata = metadata or {}

    def to_dict(self):
        """
        Returns a dictionary representation of the entry decision.
        """
        return {
            "asset": self.asset,
            "action": self.action,
            "reason": self.reason,
            "score": self.score,
            "confidence": self.confidence,
            "gross_edge_pct": self.gross_edge_pct,
            "total_cost_pct": self.total_cost_pct,
            "net_edge_pct": self.net_edge_pct,
            "quantity": self.quantity,
            "price": self.price,
            "status": self.status,
            "metadata": self.metadata
        }

    @classmethod
    def from_feasibility(cls, feasibility_result, quantity=1, price=None):
        """
        Creates a PaperEntryDecision object from a feasibility result dictionary.
        """
        if feasibility_result is None:
            return cls(
                asset=None,
                action="REJECTED",
                reason="feasibility_missing",
                score=0.0,
                confidence=0.0,
                gross_edge_pct=0.0,
                total_cost_pct=0.0,
                net_edge_pct=0.0,
                quantity=quantity,
                price=price
            )

        is_feasible = feasibility_result.get("is_feasible", False)
        if is_feasible is True:
            action = "BUY_ALLOWED"
            reason = "net_edge_positive"
        else:
            action = "REJECTED"
            reason = feasibility_result.get("reason", "net_edge_not_positive")

        asset = feasibility_result.get("asset")
        score = feasibility_result.get("gross_edge_pct", 0.0)
        confidence = feasibility_result.get("candidate", {}).get("confidence", 0.0)
        gross_edge_pct = feasibility_result.get("gross_edge_pct", 0.0)
        total_cost_pct = feasibility_result.get("total_cost_pct", 0.0)
        net_edge_pct = feasibility_result.get("net_edge_pct", 0.0)
        metadata = feasibility_result

        return cls(
            asset=asset,
            action=action,
            reason=reason,
            score=score,
            confidence=confidence,
            gross_edge_pct=gross_edge_pct,
            total_cost_pct=total_cost_pct,
            net_edge_pct=net_edge_pct,
            quantity=quantity,
            price=price,
            status="entry_decision",
            metadata=metadata
        )
