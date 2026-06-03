from ai.opportunity import Opportunity


class OpportunityAdapter:

    def from_ranked_signal(self, ranked):

        asset = ranked.get("symbol", "unknown")

        opportunity_type = ranked.get(
            "strategy",
            "unknown"
        )

        score = float(
            ranked.get("score", 0)
        )

        confidence = float(
            ranked.get("strategy_bias", 0)
        )

        metadata = {
            "regime": ranked.get("regime"),
            "symbol_bias": ranked.get("symbol_bias"),
            "strategy_bias": ranked.get("strategy_bias"),
            "regime_multiplier": ranked.get("regime_multiplier"),
            "change": ranked.get("change"),
            "volatility": ranked.get("volatility"),
            "timestamp": ranked.get("timestamp")
        }

        return Opportunity(
            asset=asset,
            source="signal_ranker",
            opportunity_type=opportunity_type,
            score=score,
            confidence=confidence,
            metadata=metadata
        )

    def from_market_quote(self, asset, quote):

        return Opportunity(
            asset=asset,
            source="market_quote",
            opportunity_type="live_market_quote",
            score=0.0,
            confidence=1.0,
            metadata=quote
        )

