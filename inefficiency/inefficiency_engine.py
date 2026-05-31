class InefficiencyEngine:

    def calculate_spread(
        self,
        market_a_price,
        market_b_price,
        fx_rate=1.0,
        fees=0.0,
        freight=0.0,
        funding_cost=0.0
    ):
        converted_a = market_a_price * fx_rate

        gross_spread = market_b_price - converted_a

        total_cost = fees + freight + funding_cost

        net_spread = gross_spread - total_cost

        if converted_a == 0:
            profit_pct = 0.0
        else:
            profit_pct = (net_spread / converted_a) * 100

        return {
            "converted_a": converted_a,
            "market_b_price": market_b_price,
            "gross_spread": gross_spread,
            "total_cost": total_cost,
            "net_spread": net_spread,
            "profit_pct": profit_pct,
            "is_profitable": net_spread > 0
        }
