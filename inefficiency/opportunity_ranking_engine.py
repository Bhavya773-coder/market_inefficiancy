from inefficiency.round_trip_cost_engine import RoundTripCostEngine
from inefficiency.settlement_engine import SettlementEngine
from inefficiency.capital_engine import CapitalEngine
from inefficiency.liquidity_engine import LiquidityEngine


# North-star priority order. Lower tier ranks first.
OPPORTUNITY_TYPE_PRIORITY = {
    "arbitrage": 0,
    "relative_value": 1,
    "delivery_fallback": 2,
    "inventory_optimization": 3
}


class OpportunityRankingEngine:
    """
    Runs every candidate opportunity through the full Phase 2 stack —
    round-trip cost, settlement, capital, liquidity — and returns one
    ranked, fully-explained list.

    Ranking rules:
    1. Non-viable candidates are excluded from the ranking and returned
       separately with explicit rejection reasons.
    2. Viable candidates rank first by opportunity-type priority
       (arbitrage > relative_value > delivery_fallback >
       inventory_optimization), then by liquidity-adjusted annualized
       return on capital, descending.

    Each candidate is a plain dict; see rank() for required keys. Output is
    a plain dict. No hidden state.
    """

    def __init__(self):
        self.cost_engine = RoundTripCostEngine()
        self.settlement_engine = SettlementEngine()
        self.capital_engine = CapitalEngine()
        self.liquidity_engine = LiquidityEngine()

    def evaluate(self, candidate, available_capital=None):
        """
        Evaluates a single candidate through all four engines.

        Required candidate keys:
            opportunity_id, opportunity_type, asset,
            buy_market, sell_market, buy_price, sell_price, quantity,
            buy_settlement_days, sell_settlement_days,
            buy_side_available_quantity, sell_side_available_quantity

        Optional keys (defaults are zero / permissive):
            every RoundTripCostEngine cost field, holding_period_days,
            annual_financing_rate_pct, max_acceptable_lockup_days,
            buy_spread_pct, sell_spread_pct, max_participation_rate,
            slippage_pct_at_full_participation, min_fill_ratio,
            min_annualized_return_pct
        """
        required = [
            "opportunity_id", "opportunity_type", "asset",
            "buy_market", "sell_market", "buy_price", "sell_price",
            "quantity", "buy_settlement_days", "sell_settlement_days",
            "buy_side_available_quantity", "sell_side_available_quantity"
        ]
        missing = [k for k in required if k not in candidate]
        if missing:
            raise ValueError(f"candidate missing required keys: {missing}")

        opportunity_type = candidate["opportunity_type"]
        if opportunity_type not in OPPORTUNITY_TYPE_PRIORITY:
            raise ValueError(
                f"unknown opportunity_type: {opportunity_type!r}; "
                f"expected one of {sorted(OPPORTUNITY_TYPE_PRIORITY)}"
            )

        rejection_reasons = []

        # 1. Liquidity first: it determines the quantity everything else
        #    is costed at.
        liquidity = self.liquidity_engine.calculate(
            desired_quantity=candidate["quantity"],
            buy_side_available_quantity=candidate["buy_side_available_quantity"],
            sell_side_available_quantity=candidate["sell_side_available_quantity"],
            buy_spread_pct=candidate.get("buy_spread_pct", 0.0),
            sell_spread_pct=candidate.get("sell_spread_pct", 0.0),
            max_participation_rate=candidate.get("max_participation_rate", 0.25),
            slippage_pct_at_full_participation=candidate.get(
                "slippage_pct_at_full_participation", 0.5
            ),
            min_fill_ratio=candidate.get("min_fill_ratio", 1.0)
        )
        executable_quantity = liquidity["executable_quantity"]
        if not liquidity["is_liquidity_viable"]:
            rejection_reasons.append("liquidity_not_viable")

        # 2. Settlement: lock-up window and financing cost of that window.
        capital_required = candidate["buy_price"] * executable_quantity
        settlement = self.settlement_engine.calculate(
            buy_settlement_days=candidate["buy_settlement_days"],
            sell_settlement_days=candidate["sell_settlement_days"],
            capital_required=capital_required,
            holding_period_days=candidate.get("holding_period_days", 0.0),
            annual_financing_rate_pct=candidate.get("annual_financing_rate_pct", 0.0),
            max_acceptable_lockup_days=candidate.get("max_acceptable_lockup_days")
        )
        if not settlement["is_settlement_viable"]:
            rejection_reasons.append("settlement_not_viable")

        # 3. Round-trip cost at executable size, including liquidity-implied
        #    slippage and settlement-implied financing.
        gross_buy_value = candidate["buy_price"] * executable_quantity
        slippage_cost = gross_buy_value * (
            liquidity["total_liquidity_cost_pct"] / 100.0
        )
        cost = self.cost_engine.calculate(
            buy_price=candidate["buy_price"],
            sell_price=candidate["sell_price"],
            quantity=executable_quantity,
            buy_brokerage=candidate.get("buy_brokerage", 0.0),
            sell_brokerage=candidate.get("sell_brokerage", 0.0),
            exchange_charges=candidate.get("exchange_charges", 0.0),
            clearing_charges=candidate.get("clearing_charges", 0.0),
            buy_tax=candidate.get("buy_tax", 0.0),
            sell_tax=candidate.get("sell_tax", 0.0),
            gst_or_vat=candidate.get("gst_or_vat", 0.0),
            stamp_duty=candidate.get("stamp_duty", 0.0),
            fx_spread=candidate.get("fx_spread", 0.0),
            slippage=slippage_cost,
            funding_cost=settlement["financing_cost"],
            freight=candidate.get("freight", 0.0),
            warehouse_cost=candidate.get("warehouse_cost", 0.0),
            handling_cost=candidate.get("handling_cost", 0.0),
            hedging_cost=candidate.get("hedging_cost", 0.0)
        )
        if not cost["is_profitable_after_round_trip"]:
            rejection_reasons.append("not_profitable_after_round_trip_costs")

        # 4. Capital: can we fund it, and what does it earn per day of
        #    lock-up?
        capital = self.capital_engine.calculate(
            capital_required=capital_required,
            net_profit=cost["net_profit"],
            capital_lockup_days=settlement["capital_lockup_days"],
            available_capital=available_capital,
            min_annualized_return_pct=candidate.get("min_annualized_return_pct", 0.0)
        )
        if not capital["can_fund"]:
            rejection_reasons.append("insufficient_capital")
        if not capital["meets_return_threshold"]:
            rejection_reasons.append("below_min_annualized_return")

        is_executable = len(rejection_reasons) == 0

        # Liquidity-adjusted annualized return is the ranking score within a
        # priority tier: a thin market discounts the headline return.
        rank_score = capital["annualized_return_pct"] * liquidity["liquidity_score"]

        return {
            "opportunity_id": candidate["opportunity_id"],
            "opportunity_type": opportunity_type,
            "priority_tier": OPPORTUNITY_TYPE_PRIORITY[opportunity_type],
            "asset": candidate["asset"],
            "buy_market": candidate["buy_market"],
            "sell_market": candidate["sell_market"],
            "executable_quantity": executable_quantity,
            "capital_required": capital_required,
            "net_profit": cost["net_profit"],
            "net_profit_pct": cost["net_profit_pct"],
            "annualized_return_pct": capital["annualized_return_pct"],
            "liquidity_score": liquidity["liquidity_score"],
            "rank_score": rank_score,
            "is_executable": is_executable,
            "rejection_reasons": rejection_reasons,
            "cost_result": cost,
            "settlement_result": settlement,
            "capital_result": capital,
            "liquidity_result": liquidity
        }

    def rank(self, candidates, available_capital=None):
        """
        Evaluates every candidate and returns:
        {
            "ranked": [evaluations ordered best-first],
            "rejected": [evaluations with rejection_reasons],
            "evaluated_count": int
        }
        """
        evaluations = [
            self.evaluate(candidate, available_capital=available_capital)
            for candidate in candidates
        ]

        ranked = [e for e in evaluations if e["is_executable"]]
        rejected = [e for e in evaluations if not e["is_executable"]]

        ranked.sort(key=lambda e: (e["priority_tier"], -e["rank_score"]))

        return {
            "ranked": ranked,
            "rejected": rejected,
            "evaluated_count": len(evaluations)
        }
