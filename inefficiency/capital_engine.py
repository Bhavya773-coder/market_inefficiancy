class CapitalEngine:
    """
    Measures what an opportunity earns per unit of capital per unit of time,
    and whether available capital can fund it at all.

    This is the layer that makes a 0.4% spread settling tomorrow comparable
    with a 3% spread that locks capital for a month.

    All inputs are explicit. Output is a plain dict. No hidden state.
    """

    def calculate(
        self,
        capital_required,
        net_profit,
        capital_lockup_days,
        available_capital=None,
        min_annualized_return_pct=0.0
    ):
        if capital_required < 0:
            raise ValueError("capital_required must be >= 0")
        if capital_lockup_days < 0:
            raise ValueError("capital_lockup_days must be >= 0")
        if available_capital is not None and available_capital < 0:
            raise ValueError("available_capital must be >= 0")

        if capital_required == 0:
            return_on_capital_pct = 0.0
        else:
            return_on_capital_pct = (net_profit / capital_required) * 100.0

        # A same-day round trip is treated as a one-day capital commitment so
        # annualization never divides by zero and never rewards an
        # unrealistic instantaneous turnover.
        effective_lockup_days = max(capital_lockup_days, 1.0)
        annualized_return_pct = return_on_capital_pct * (365.0 / effective_lockup_days)

        if available_capital is None:
            can_fund = True
            capital_utilization_pct = 0.0
        else:
            can_fund = available_capital >= capital_required
            if available_capital == 0:
                capital_utilization_pct = 0.0 if capital_required == 0 else 100.0
            else:
                capital_utilization_pct = (capital_required / available_capital) * 100.0

        meets_return_threshold = annualized_return_pct >= min_annualized_return_pct

        return {
            "capital_required": capital_required,
            "net_profit": net_profit,
            "capital_lockup_days": capital_lockup_days,
            "effective_lockup_days": effective_lockup_days,
            "return_on_capital_pct": return_on_capital_pct,
            "annualized_return_pct": annualized_return_pct,
            "can_fund": can_fund,
            "capital_utilization_pct": capital_utilization_pct,
            "meets_return_threshold": meets_return_threshold,
            "is_capital_viable": can_fund and meets_return_threshold
        }
