from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
from ai.paper_trade_simulator import PaperTradeSimulator
import pprint

def main():
    adapter = OpportunityAdapter()
    validator = OpportunityValidator()
    factory = PaperTradeCandidateFactory()
    simulator = PaperTradeSimulator()

    # Valid lag result
    lag_result = {
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

    # Flow
    opp = adapter.from_lag_result(lag_result)
    val = validator.validate(opp)
    candidate = factory.from_validated_opportunity(val)

    # Test 1: simulate_candidate
    sim_res_1 = simulator.simulate_candidate(candidate)
    print("Test 1 - Simulate Candidate:")
    pprint.pprint(sim_res_1)
    print("-" * 50)

    # Test 2: force_buy_for_test
    print("Test 2 - Force Buy for Test (10 @ 100):")
    buy_res_2 = simulator.force_buy_for_test(candidate, quantity=10, price=100)
    pprint.pprint(buy_res_2)
    print("Account State:")
    pprint.pprint(simulator.account.to_dict())
    print("-" * 50)

    # Test 3: Insufficient Cash Buy
    print("Test 3 - Force Buy for Test (2000 @ 100) (insufficient cash):")
    buy_res_3 = simulator.force_buy_for_test(candidate, quantity=2000, price=100)
    pprint.pprint(buy_res_3)
    print("Account State:")
    pprint.pprint(simulator.account.to_dict())
    print("-" * 50)

if __name__ == "__main__":
    main()
