from ai.paper_trade_candidate import PaperTradeCandidate

class PaperTradeCandidateFactory:
    """
    Factory for creating PaperTradeCandidate objects from validated opportunities.
    """

    def from_validated_opportunity(self, validation_result):
        """
        Creates a PaperTradeCandidate from a validation result dict.
        Returns None if validation_result is invalid.
        """
        if validation_result is None:
            return None

        if validation_result.get("is_valid") is not True:
            return None

        opp = validation_result.get("opportunity")
        if opp is None:
            return None

        metadata = opp.get("metadata") or {}
        timestamp = metadata.get("timestamp") if isinstance(metadata, dict) else None

        return PaperTradeCandidate(
            asset=opp.get("asset"),
            source=opp.get("source"),
            opportunity_type=opp.get("opportunity_type"),
            entry_reason=validation_result.get("reason"),
            suggested_direction="WATCH",
            score=opp.get("score", 0.0),
            confidence=opp.get("confidence", 0.0),
            timestamp=timestamp,
            metadata=metadata
        )
