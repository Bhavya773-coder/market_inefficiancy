from ai.paper_trading_account import PaperTradingAccount

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
