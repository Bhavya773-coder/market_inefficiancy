from ai.round_trip_feasibility_checker import RoundTripFeasibilityChecker
from ai.candidate_feasibility_adapter import CandidateFeasibilityAdapter
from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
import pprint

def main():
    checker = RoundTripFeasibilityChecker()
    adapter = CandidateFeasibilityAdapter()

    # Test 1: gross_edge_pct = 0.37
    print("=== TEST 1: gross_edge_pct = 0.37 ===")
    res_1 = checker.check(0.37)
    pprint.pprint(res_1)
    print("-" * 50)

    # Test 2: gross_edge_pct = 0.05
    print("=== TEST 2: gross_edge_pct = 0.05 ===")
    res_2 = checker.check(0.05)
    pprint.pprint(res_2)
    print("-" * 50)

    # Test 3: Full pipeline
    print("=== TEST 3: Full pipeline ===")
    opp_adapter = OpportunityAdapter()
    validator = OpportunityValidator()
    factory = PaperTradeCandidateFactory()

    lag_result = {
        "reference_symbol": "NIFTYBEES",
        "target_symbol": "HDFCNIFTY",
        "reference_change": 0.40,
        "target_change": 0.03,
        "reaction_gap": 0.37,
        "same_direction": True,
        "is_lagging": True,
        "timestamp": "06/06/2026 19:33:13"
    }

    opp = opp_adapter.from_lag_result(lag_result)
    val = validator.validate(opp)
    candidate = factory.from_validated_opportunity(val)

    feasibility = adapter.from_candidate(candidate, checker)
    pprint.pprint(feasibility)
    print("-" * 50)

if __name__ == "__main__":
    main()
