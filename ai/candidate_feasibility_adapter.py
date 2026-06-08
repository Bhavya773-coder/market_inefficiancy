from ai.round_trip_feasibility_checker import RoundTripFeasibilityChecker

class CandidateFeasibilityAdapter:
    """
    Adapts a PaperTradeCandidate to evaluate its feasibility based on round-trip costs.
    """

    def from_candidate(self, candidate, checker=None):
        """
        Calculates feasibility parameters from a PaperTradeCandidate object or dict.
        """
        if candidate is None:
            return {
                "is_feasible": False,
                "reason": "candidate_missing"
            }

        try:
            candidate_dict = candidate.to_dict()
        except AttributeError:
            if isinstance(candidate, dict):
                candidate_dict = candidate
            else:
                return {
                    "is_feasible": False,
                    "reason": "candidate_missing"
                }

        gross_edge_pct = candidate_dict.get("score", 0.0)

        if checker is None:
            checker = RoundTripFeasibilityChecker()

        res = checker.check(gross_edge_pct)
        res.update({
            "asset": candidate_dict.get("asset"),
            "source": candidate_dict.get("source"),
            "opportunity_type": candidate_dict.get("opportunity_type"),
            "candidate": candidate_dict,
            "reason": "feasible" if res["is_feasible"] else "net_edge_not_positive"
        })
        
        return res
