from ai.opportunity import Opportunity
from inefficiency.inefficiency_engine import InefficiencyEngine


class InefficiencyOpportunityAdapter:

    def __init__(self):
        self.engine = InefficiencyEngine()

    def from_market_pair(
        self,
        asset,
        market_a,
        market_b,
        market_a_price,
        market_b_price,
        fx_rate=1.0,
        fees=0.0,
        freight=0.0,
        funding_cost=0.0
    ):

        result = self.engine.calculate_spread(
            market_a_price=market_a_price,
            market_b_price=market_b_price,
            fx_rate=fx_rate,
            fees=fees,
            freight=freight,
            funding_cost=funding_cost
        )

        score = result["profit_pct"]

        confidence = max(
            -1.0,
            min(
                1.0,
                result["profit_pct"] / 5.0
            )
        )

        metadata = {
            "market_a": market_a,
            "market_b": market_b,
            "market_a_price": market_a_price,
            "market_b_price": market_b_price,
            "fx_rate": fx_rate,
            "fees": fees,
            "freight": freight,
            "funding_cost": funding_cost,
            "converted_a": result["converted_a"],
            "gross_spread": result["gross_spread"],
            "total_cost": result["total_cost"],
            "net_spread": result["net_spread"],
            "profit_pct": result["profit_pct"],
            "is_profitable": result["is_profitable"]
        }

        return Opportunity(
            asset=asset,
            source="inefficiency_engine",
            opportunity_type="cross_market_spread",
            score=score,
            confidence=confidence,
            metadata=metadata
        )
