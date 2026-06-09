# Paper-only simulator.
# This module must never call real broker order APIs.
from ai.paper_trading_account import PaperTradingAccount
from ai.paper_position_exit_evaluator import PaperPositionExitEvaluator
from ai.paper_exit_decision import PaperExitDecision
from ai.candidate_feasibility_adapter import CandidateFeasibilityAdapter
from ai.paper_entry_decision import PaperEntryDecision




class PaperTradeSimulator:
    """
    Converts PaperTradeCandidate into simulated paper-trade decisions.
    """

    def __init__(self, account=None):
        self.account = account if account is not None else PaperTradingAccount()

    def simulate_candidate(self, candidate, quantity=1, price=None):
        """
        Simulates evaluation of a candidate.
        Currently watch-only for safety.
        """
        if candidate is None:
            return {
                "status": "rejected",
                "reason": "candidate_missing"
            }

        try:
            candidate_dict = candidate.to_dict()
        except AttributeError:
            if isinstance(candidate, dict):
                candidate_dict = candidate
            else:
                return {
                    "status": "rejected",
                    "reason": "candidate_missing"
                }

        if candidate_dict.get("status") != "candidate":
            return {
                "status": "rejected",
                "reason": "invalid_candidate_status",
                "candidate": candidate_dict
            }

        if price is None:
            metadata = candidate_dict.get("metadata") or {}
            price = metadata.get("target_price")
            if price is None:
                return {
                    "status": "rejected",
                    "reason": "price_missing",
                    "candidate": candidate_dict
                }

        if candidate_dict.get("suggested_direction") == "WATCH":
            return {
                "status": "watch_only",
                "reason": "candidate_is_watch_only",
                "candidate": candidate_dict
            }

        # Safety-first watch-only default
        return {
            "status": "watch_only",
            "reason": "candidate_is_watch_only",
            "candidate": candidate_dict
        }

    def force_buy_for_test(self, candidate, quantity, price):
        """
        Force buying for testing purposes.
        """
        if candidate is None:
            return {
                "status": "rejected",
                "reason": "candidate_missing"
            }

        try:
            candidate_dict = candidate.to_dict()
        except AttributeError:
            if isinstance(candidate, dict):
                candidate_dict = candidate
            else:
                return {
                    "status": "rejected",
                    "reason": "candidate_missing"
                }

        asset = candidate_dict.get("asset")
        return self.account.buy(asset, quantity, price, metadata=candidate_dict)

    def evaluate_position_exit(self, symbol, current_price, target_profit_pct=0.50, stop_loss_pct=0.25):
        """
        Evaluates whether an active paper position should be exited or held.
        """
        evaluator = PaperPositionExitEvaluator()
        position = self.account.positions.get(symbol)
        return evaluator.evaluate(symbol, position, current_price, target_profit_pct, stop_loss_pct)

    def create_exit_decision(self, symbol, current_price, target_profit_pct=0.50, stop_loss_pct=0.25):
        """
        Creates a structured PaperExitDecision for an active paper position.
        """
        evaluation = self.evaluate_position_exit(symbol, current_price, target_profit_pct, stop_loss_pct)
        return PaperExitDecision.from_evaluation(evaluation)

    def create_entry_decision(self, candidate, quantity=1, price=None):
        """
        Creates a structured PaperEntryDecision about entering a paper candidate.
        """
        adapter = CandidateFeasibilityAdapter()
        feasibility_result = adapter.from_candidate(candidate)
        return PaperEntryDecision.from_feasibility(feasibility_result, quantity, price)

    def execute_entry_decision(self, decision):
        """
        Executes an entry decision if allowed.
        """
        if decision is None:
            return {
                "status": "rejected",
                "reason": "decision_missing"
            }

        try:
            decision_dict = decision.to_dict()
        except AttributeError:
            if isinstance(decision, dict):
                decision_dict = decision
            else:
                return {
                    "status": "rejected",
                    "reason": "decision_missing"
                }

        if decision_dict.get("action") != "BUY_ALLOWED":
            return {
                "status": "rejected",
                "reason": "entry_not_allowed",
                "decision": decision_dict
            }

        if decision_dict.get("price") is None:
            return {
                "status": "rejected",
                "reason": "price_missing",
                "decision": decision_dict
            }

        if decision_dict.get("asset") is None:
            return {
                "status": "rejected",
                "reason": "asset_missing",
                "decision": decision_dict
            }

        symbol = decision_dict["asset"]
        quantity = decision_dict["quantity"]
        price = decision_dict["price"]
        return self.account.buy(symbol, quantity, price, metadata=decision_dict)

    def close_position_from_decision(self, decision):
        """
        Closes a position automatically based on a PaperExitDecision.
        """
        if decision is None:
            return {
                "status": "rejected",
                "reason": "decision_missing"
            }

        try:
            decision_dict = decision.to_dict()
        except AttributeError:
            if isinstance(decision, dict):
                decision_dict = decision
            else:
                return {
                    "status": "rejected",
                    "reason": "decision_missing"
                }

        action = decision_dict.get("action")
        if action == "HOLD":
            return {
                "status": "hold",
                "reason": "exit_not_required",
                "decision": decision_dict
            }

        if action == "NO_POSITION":
            return {
                "status": "rejected",
                "reason": "position_missing",
                "decision": decision_dict
            }

        if action in ("TAKE_PROFIT", "STOP_LOSS"):
            symbol = decision_dict.get("symbol")
            quantity = decision_dict.get("quantity")
            price = decision_dict.get("current_price")
            return self.account.sell(symbol, quantity, price, metadata=decision_dict)

        return {
            "status": "rejected",
            "reason": "unknown_exit_action",
            "decision": decision_dict
        }



