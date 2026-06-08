from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
from ai.paper_trade_simulator import PaperTradeSimulator
import pprint

def run_pipeline(lag_result, quantity=10, price=100.0):
    adapter = OpportunityAdapter()
    validator = OpportunityValidator()
    factory = PaperTradeCandidateFactory()
    simulator = PaperTradeSimulator()

    opp = adapter.from_lag_result(lag_result)
    val = validator.validate(opp)
    candidate = factory.from_validated_opportunity(val)

    decision = simulator.create_entry_decision(candidate, quantity, price)
    return decision

def main():
    # Test 1 — feasible candidate
    print("=== TEST 1: FEASIBLE CANDIDATE ===")
    lag_result_feasible = {
        "reference_symbol": "NIFTYBEES",
        "target_symbol": "HDFCNIFTY",
        "reference_change": 0.40,
        "target_change": 0.03,
        "reaction_gap": 0.37,
        "same_direction": True,
        "is_lagging": True,
        "timestamp": "06/06/2026 19:33:13",
        "target_price": 100.0
    }
    dec_feasible = run_pipeline(lag_result_feasible, quantity=10, price=100.0)
    print("Decision:")
    if dec_feasible:
        pprint.pprint(dec_feasible.to_dict())
    else:
        print("Decision is None")
    print("-" * 50)

    # Test 2 — non-feasible candidate (reaction_gap = 0.05)
    print("=== TEST 2: NON-FEASIBLE CANDIDATE ===")
    lag_result_non_feasible = {
        "reference_symbol": "NIFTYBEES",
        "target_symbol": "HDFCNIFTY",
        "reference_change": 0.40,
        "target_change": 0.03,
        "reaction_gap": 0.05,
        "same_direction": True,
        "is_lagging": True,
        "timestamp": "06/06/2026 19:33:13",
        "target_price": 100.0
    }
    dec_non_feasible = run_pipeline(lag_result_non_feasible, quantity=10, price=100.0)
    print("Decision:")
    if dec_non_feasible:
        pprint.pprint(dec_non_feasible.to_dict())
    else:
        print("Decision is None")
    print("-" * 50)

if __name__ == "__main__":
    main()
