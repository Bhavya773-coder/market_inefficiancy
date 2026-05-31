class Opportunity:

    def __init__(
        self,
        asset,
        source,
        opportunity_type,
        score,
        confidence=0.0,
        metadata=None
    ):

        self.asset = asset

        self.source = source

        self.opportunity_type = opportunity_type

        self.score = score

        self.confidence = confidence

        self.metadata = metadata or {}

    def to_dict(self):

        return {
            "asset": self.asset,
            "source": self.source,
            "opportunity_type": self.opportunity_type,
            "score": self.score,
            "confidence": self.confidence,
            "metadata": self.metadata
        }
