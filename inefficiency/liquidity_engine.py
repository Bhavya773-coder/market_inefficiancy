class LiquidityEngine:
    """
    Answers whether an opportunity's size can actually be executed on both
    legs, and at what slippage, given each leg's observable liquidity.

    Sizing model (deterministic, explicit):
    - Executable quantity is capped by a maximum participation share of each
      leg's available quantity (market depth or tradable volume).
    - Slippage is estimated linearly against participation: consuming the
      full allowed participation costs `slippage_pct_at_full_participation`
      of price on that leg. This is a deliberately simple, conservative
      proxy — not a fitted market-impact model.

    All inputs are explicit. Output is a plain dict. No hidden state.
    """

    def calculate(
        self,
        desired_quantity,
        buy_side_available_quantity,
        sell_side_available_quantity,
        buy_spread_pct=0.0,
        sell_spread_pct=0.0,
        max_participation_rate=0.25,
        slippage_pct_at_full_participation=0.5,
        min_fill_ratio=1.0
    ):
        if desired_quantity <= 0:
            raise ValueError("desired_quantity must be > 0")
        if buy_side_available_quantity < 0:
            raise ValueError("buy_side_available_quantity must be >= 0")
        if sell_side_available_quantity < 0:
            raise ValueError("sell_side_available_quantity must be >= 0")
        if not (0.0 < max_participation_rate <= 1.0):
            raise ValueError("max_participation_rate must be in (0, 1]")
        if slippage_pct_at_full_participation < 0:
            raise ValueError("slippage_pct_at_full_participation must be >= 0")
        if not (0.0 <= min_fill_ratio <= 1.0):
            raise ValueError("min_fill_ratio must be in [0, 1]")
        if buy_spread_pct < 0 or sell_spread_pct < 0:
            raise ValueError("spread percentages must be >= 0")

        max_buy_quantity = buy_side_available_quantity * max_participation_rate
        max_sell_quantity = sell_side_available_quantity * max_participation_rate

        executable_quantity = min(desired_quantity, max_buy_quantity, max_sell_quantity)
        fill_ratio = executable_quantity / desired_quantity

        # Participation actually used on each leg by the executable quantity.
        if buy_side_available_quantity == 0:
            buy_participation = 0.0
        else:
            buy_participation = executable_quantity / buy_side_available_quantity
        if sell_side_available_quantity == 0:
            sell_participation = 0.0
        else:
            sell_participation = executable_quantity / sell_side_available_quantity

        # Linear impact proxy: full allowed participation costs the full
        # configured slippage on that leg.
        buy_slippage_pct = (
            (buy_participation / max_participation_rate)
            * slippage_pct_at_full_participation
        )
        sell_slippage_pct = (
            (sell_participation / max_participation_rate)
            * slippage_pct_at_full_participation
        )

        # Round-trip liquidity cost: crossing each leg's spread once plus
        # impact on both legs.
        total_liquidity_cost_pct = (
            buy_spread_pct + sell_spread_pct + buy_slippage_pct + sell_slippage_pct
        )

        # Bounded 0..1 score: 1.0 when the desired size fills entirely with
        # zero liquidity cost, decaying with unfilled size and with cost.
        # 1% of round-trip liquidity cost halves the cost component.
        cost_component = 1.0 / (1.0 + total_liquidity_cost_pct)
        liquidity_score = fill_ratio * cost_component

        meets_fill_requirement = fill_ratio >= min_fill_ratio

        return {
            "desired_quantity": desired_quantity,
            "executable_quantity": executable_quantity,
            "fill_ratio": fill_ratio,
            "buy_participation": buy_participation,
            "sell_participation": sell_participation,
            "buy_slippage_pct": buy_slippage_pct,
            "sell_slippage_pct": sell_slippage_pct,
            "buy_spread_pct": buy_spread_pct,
            "sell_spread_pct": sell_spread_pct,
            "total_liquidity_cost_pct": total_liquidity_cost_pct,
            "liquidity_score": liquidity_score,
            "meets_fill_requirement": meets_fill_requirement,
            "is_liquidity_viable": meets_fill_requirement and executable_quantity > 0
        }
