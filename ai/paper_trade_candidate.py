class PaperTradeCandidate:
    """
    Represents a candidate for paper trading generated from a validated opportunity.
    """

    def __init__(
        self,
        asset,
        source,
        opportunity_type,
        entry_reason,
        suggested_direction="WATCH",
        score=0.0,
        confidence=0.0,
        timestamp=None,
        status="candidate",
        metadata=None
    ):
        self.asset = asset
        self.source = source
        self.opportunity_type = opportunity_type
        self.entry_reason = entry_reason
        self.suggested_direction = suggested_direction
        self.score = score
        self.confidence = confidence
        self.timestamp = timestamp
        self.status = status
        self.metadata = metadata or {}

    def to_dict(self):
        return {
            "asset": self.asset,
            "source": self.source,
            "opportunity_type": self.opportunity_type,
            "entry_reason": self.entry_reason,
            "suggested_direction": self.suggested_direction,
            "score": self.score,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "status": self.status,
            "metadata": self.metadata
        }
