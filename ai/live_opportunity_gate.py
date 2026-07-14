from inefficiency.opportunity_ranking_engine import OpportunityRankingEngine


DEFAULT_GATE_CONFIG = {
    # Trade sizing
    "desired_quantity": 10,
    # NSE equity T+1 both legs; intraday convergence assumption
    "buy_settlement_days": 1,
    "sell_settlement_days": 1,
    "holding_period_days": 0.0,
    "annual_financing_rate_pct": 6.0,
    "max_acceptable_lockup_days": 30,
    # Percentage-based costs, converted to absolute against gross buy value.
    # Split of the flat 0.13% used by the legacy RoundTripFeasibilityChecker,
    # minus spread/slippage which the liquidity engine now prices explicitly.
    "buy_brokerage_pct": 0.015,
    "sell_brokerage_pct": 0.015,
    "buy_tax_pct": 0.01,
    "sell_tax_pct": 0.01,
    "latency_buffer_pct": 0.02,
    # Liquidity assumptions when the quote carries no usable depth/volume
    "default_available_quantity": 100000.0,
    "default_spread_pct": 0.03,
    "max_participation_rate": 0.25,
    "slippage_pct_at_full_participation": 0.5,
    "min_fill_ratio": 0.5,
    # Capital hurdle
    "min_annualized_return_pct": 5.0
}


class LiveOpportunityGate:
    """
    The single entry gate for live paper trading.

    Adapts a detector target result + live quote into a full
    OpportunityRankingEngine candidate and lets THAT engine — cost,
    settlement, capital and liquidity together — decide whether a paper
    entry is allowed. Replaces the legacy flat-percentage
    RoundTripFeasibilityChecker gating.

    Detected inefficiencies here are convergence signals, not two-venue
    price locks, so candidates are typed "relative_value" (honest per the
    north-star priority order) and modeled as a round trip on one
    instrument: buy at the live price, exit at the price implied by the
    unpriced gap.
    """

    def __init__(self, ranking_engine=None, config=None):
        self.ranking_engine = ranking_engine if ranking_engine is not None else OpportunityRankingEngine()
        merged = dict(DEFAULT_GATE_CONFIG)
        if config:
            unknown = set(config) - set(DEFAULT_GATE_CONFIG)
            if unknown:
                raise ValueError(f"unknown gate config keys: {sorted(unknown)}")
            merged.update(config)
        self.config = merged

    @staticmethod
    def _expected_edge_pct(target_result, contextual_action):
        """
        The unpriced move the detector claims remains, in percent.
        residual_gap is preferred (gap net of what already happened);
        absolute_gap is the fallback. REDUCE_PRIORITY halves the edge we
        are willing to believe.
        """
        gap = target_result.get("residual_gap")
        if gap is None:
            gap = target_result.get("absolute_gap")
        if gap is None or not isinstance(gap, (int, float)):
            return None
        edge = abs(float(gap))
        if contextual_action == "REDUCE_PRIORITY":
            edge *= 0.5
        return edge

    def build_candidate(self, target_name, target_result, contextual_action, quote):
        """
        Builds an OpportunityRankingEngine candidate dict from live inputs.
        Returns (candidate, None) or (None, reason).
        """
        if not isinstance(quote, dict):
            return None, "missing_quote"

        price = quote.get("last_price")
        if not isinstance(price, (int, float)) or price <= 0:
            return None, "invalid_quote_price"

        edge_pct = self._expected_edge_pct(target_result, contextual_action)
        if edge_pct is None:
            return None, "no_measurable_edge"
        if edge_pct == 0.0:
            return None, "zero_edge"

        cfg = self.config
        volume = quote.get("volume")
        if isinstance(volume, (int, float)) and volume > 0:
            available_qty = float(volume)
        else:
            available_qty = cfg["default_available_quantity"]

        quantity = cfg["desired_quantity"]
        gross_buy_value = price * quantity

        def pct_cost(pct):
            return gross_buy_value * (pct / 100.0)

        candidate = {
            "opportunity_id": f"{target_name}@{quote.get('timestamp', 'unknown')}",
            "opportunity_type": "relative_value",
            "asset": target_name,
            "buy_market": quote.get("exchange", "UNKNOWN"),
            "sell_market": quote.get("exchange", "UNKNOWN"),
            "buy_price": float(price),
            "sell_price": float(price) * (1.0 + edge_pct / 100.0),
            "quantity": quantity,
            "buy_settlement_days": cfg["buy_settlement_days"],
            "sell_settlement_days": cfg["sell_settlement_days"],
            "holding_period_days": cfg["holding_period_days"],
            "annual_financing_rate_pct": cfg["annual_financing_rate_pct"],
            "max_acceptable_lockup_days": cfg["max_acceptable_lockup_days"],
            "buy_side_available_quantity": available_qty,
            "sell_side_available_quantity": available_qty,
            "buy_spread_pct": cfg["default_spread_pct"],
            "sell_spread_pct": cfg["default_spread_pct"],
            "max_participation_rate": cfg["max_participation_rate"],
            "slippage_pct_at_full_participation": cfg["slippage_pct_at_full_participation"],
            "min_fill_ratio": cfg["min_fill_ratio"],
            "min_annualized_return_pct": cfg["min_annualized_return_pct"],
            "buy_brokerage": pct_cost(cfg["buy_brokerage_pct"]),
            "sell_brokerage": pct_cost(cfg["sell_brokerage_pct"]),
            "buy_tax": pct_cost(cfg["buy_tax_pct"]),
            "sell_tax": pct_cost(cfg["sell_tax_pct"]),
            "handling_cost": pct_cost(cfg["latency_buffer_pct"])
        }
        return candidate, None

    def evaluate_target(
        self,
        target_name,
        target_result,
        contextual_action,
        quote,
        available_capital=None
    ):
        """
        Full gate decision. Returns:
        {
            "allowed": bool,
            "quantity": int (0 when blocked),
            "rejection_reasons": [str, ...],
            "candidate": dict or None,
            "evaluation": full ranking-engine evaluation or None
        }
        """
        candidate, build_error = self.build_candidate(
            target_name, target_result, contextual_action, quote
        )
        if candidate is None:
            return {
                "allowed": False,
                "quantity": 0,
                "rejection_reasons": [build_error],
                "candidate": None,
                "evaluation": None
            }

        evaluation = self.ranking_engine.evaluate(
            candidate, available_capital=available_capital
        )

        quantity = int(evaluation["executable_quantity"])
        allowed = bool(evaluation["is_executable"]) and quantity >= 1

        rejection_reasons = list(evaluation["rejection_reasons"])
        if evaluation["is_executable"] and quantity < 1:
            rejection_reasons.append("executable_quantity_below_one")

        return {
            "allowed": allowed,
            "quantity": quantity if allowed else 0,
            "rejection_reasons": rejection_reasons,
            "candidate": candidate,
            "evaluation": evaluation
        }
