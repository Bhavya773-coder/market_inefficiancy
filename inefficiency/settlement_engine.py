class SettlementEngine:
    """
    Models settlement timing for a two-leg (buy leg + sell leg) opportunity.

    Answers, deterministically and with no hidden state:
    - How long is capital locked before sale proceeds are usable?
    - What does that lock-up cost in financing terms?
    - Does the settlement mismatch between the two legs create a funding gap?

    All inputs are explicit. Output is a plain dict.
    """

    def calculate(
        self,
        buy_settlement_days,
        sell_settlement_days,
        capital_required,
        holding_period_days=0.0,
        annual_financing_rate_pct=0.0,
        max_acceptable_lockup_days=None
    ):
        if buy_settlement_days < 0:
            raise ValueError("buy_settlement_days must be >= 0")
        if sell_settlement_days < 0:
            raise ValueError("sell_settlement_days must be >= 0")
        if capital_required < 0:
            raise ValueError("capital_required must be >= 0")
        if holding_period_days < 0:
            raise ValueError("holding_period_days must be >= 0")
        if annual_financing_rate_pct < 0:
            raise ValueError("annual_financing_rate_pct must be >= 0")

        # Capital leaves on buy settlement and returns after the position is
        # held and the sell leg settles.
        capital_lockup_days = (
            holding_period_days + sell_settlement_days
        )

        # A funding gap exists when the buy leg must be paid before the sell
        # leg pays out (the normal case; the gap is the lock-up itself), and
        # is negative only in the unusual case sale proceeds arrive first.
        settlement_mismatch_days = sell_settlement_days - buy_settlement_days

        daily_financing_rate = (annual_financing_rate_pct / 100.0) / 365.0
        financing_cost = capital_required * daily_financing_rate * capital_lockup_days

        if max_acceptable_lockup_days is None:
            within_lockup_limit = True
        else:
            within_lockup_limit = capital_lockup_days <= max_acceptable_lockup_days

        return {
            "buy_settlement_days": buy_settlement_days,
            "sell_settlement_days": sell_settlement_days,
            "holding_period_days": holding_period_days,
            "capital_lockup_days": capital_lockup_days,
            "settlement_mismatch_days": settlement_mismatch_days,
            "annual_financing_rate_pct": annual_financing_rate_pct,
            "financing_cost": financing_cost,
            "within_lockup_limit": within_lockup_limit,
            "is_settlement_viable": within_lockup_limit
        }
