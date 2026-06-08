class RoundTripFeasibilityChecker:
    """
    Calculates whether a trading opportunity has enough edge to survive round-trip trading costs.
    """

    def check(
        self,
        gross_edge_pct,
        brokerage_pct=0.03,
        taxes_pct=0.02,
        spread_pct=0.03,
        slippage_pct=0.03,
        latency_buffer_pct=0.02
    ):
        """
        Calculates total cost, net edge, and returns whether the opportunity is feasible.
        """
        total_cost_pct = (
            brokerage_pct
            + taxes_pct
            + spread_pct
            + slippage_pct
            + latency_buffer_pct
        )

        net_edge_pct = gross_edge_pct - total_cost_pct
        is_feasible = net_edge_pct > 0

        return {
            "gross_edge_pct": gross_edge_pct,
            "brokerage_pct": brokerage_pct,
            "taxes_pct": taxes_pct,
            "spread_pct": spread_pct,
            "slippage_pct": slippage_pct,
            "latency_buffer_pct": latency_buffer_pct,
            "total_cost_pct": total_cost_pct,
            "net_edge_pct": net_edge_pct,
            "is_feasible": is_feasible
        }
