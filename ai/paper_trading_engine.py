from ai.paper_trade_simulator import PaperTradeSimulator
from ai.paper_entry_decision import PaperEntryDecision

class PaperTradingEngine:
    """
    Reusable wrapper around PaperTradeSimulator to handle candidate processing,
    price updates, and account state reporting for paper trading.
    """

    def __init__(self, simulator=None):
        self.simulator = simulator if simulator is not None else PaperTradeSimulator()

    def process_candidate(self, candidate, quantity=1, price=None):
        """
        Process a paper trade candidate by creating and executing an entry decision.

        Legacy path: gates entry with the flat-percentage
        RoundTripFeasibilityChecker. The live runner uses
        process_gated_candidate instead, where the OpportunityRankingEngine
        verdict decides.
        """
        decision = self.simulator.create_entry_decision(
            candidate,
            quantity=quantity,
            price=price
        )
        execution = self.simulator.execute_entry_decision(decision)
        return {
            "stage": "entry",
            "decision": decision.to_dict() if decision else None,
            "execution": execution,
            "account": self.simulator.account.to_dict()
        }

    def process_gated_candidate(self, candidate, gate_result, price):
        """
        Process a candidate whose entry verdict was already decided by
        LiveOpportunityGate (i.e. by the OpportunityRankingEngine). No
        second feasibility opinion is taken here — the gate's verdict IS
        the decision; this method only converts it into a paper entry.
        """
        if candidate is None or gate_result is None:
            return {
                "stage": "entry",
                "decision": None,
                "execution": {"status": "rejected", "reason": "candidate_or_gate_missing"},
                "account": self.simulator.account.to_dict()
            }

        try:
            candidate_dict = candidate.to_dict()
        except AttributeError:
            candidate_dict = candidate if isinstance(candidate, dict) else {}

        evaluation = gate_result.get("evaluation") or {}
        allowed = gate_result.get("allowed") is True

        if allowed:
            action = "BUY_ALLOWED"
            reason = "ranking_engine_approved"
        else:
            action = "REJECTED"
            reasons = gate_result.get("rejection_reasons") or ["ranking_engine_rejected"]
            reason = "ranking_engine_rejected:" + ",".join(reasons)

        cost_result = evaluation.get("cost_result") or {}
        gross_buy_value = cost_result.get("gross_buy_value") or 0.0
        total_cost = cost_result.get("total_round_trip_cost") or 0.0
        total_cost_pct = (total_cost / gross_buy_value * 100.0) if gross_buy_value else 0.0

        decision = PaperEntryDecision(
            asset=candidate_dict.get("asset"),
            action=action,
            reason=reason,
            score=evaluation.get("rank_score", 0.0),
            confidence=candidate_dict.get("confidence", 0.0),
            gross_edge_pct=evaluation.get("net_profit_pct", 0.0),
            total_cost_pct=total_cost_pct,
            net_edge_pct=evaluation.get("net_profit_pct", 0.0),
            quantity=gate_result.get("quantity", 0),
            price=price,
            metadata={
                "gate": "opportunity_ranking_engine",
                "rejection_reasons": gate_result.get("rejection_reasons", []),
                "annualized_return_pct": evaluation.get("annualized_return_pct"),
                "liquidity_score": evaluation.get("liquidity_score"),
                "capital_required": evaluation.get("capital_required")
            }
        )
        execution = self.simulator.execute_entry_decision(decision)
        return {
            "stage": "entry",
            "decision": decision.to_dict(),
            "execution": execution,
            "account": self.simulator.account.to_dict()
        }

    def process_price_update(self, symbol, current_price, target_profit_pct=0.50, stop_loss_pct=0.25):
        """
        Process a price update for a symbol, checking if any active position should exit.
        """
        decision = self.simulator.create_exit_decision(
            symbol,
            current_price=current_price,
            target_profit_pct=target_profit_pct,
            stop_loss_pct=stop_loss_pct
        )
        execution = self.simulator.close_position_from_decision(decision)
        return {
            "stage": "exit",
            "decision": decision.to_dict() if decision else None,
            "execution": execution,
            "account": self.simulator.account.to_dict()
        }

    def account_state(self):
        """
        Return the current state of the paper trading account.
        """
        return self.simulator.account.to_dict()
