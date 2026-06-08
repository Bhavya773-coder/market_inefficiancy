from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
from ai.paper_trade_simulator import PaperTradeSimulator
import pprint

def setup_simulation():
    # Helper to setup a simulator with HDFCNIFTY position (10 @ 100)
    simulator = PaperTradeSimulator()
    adapter = OpportunityAdapter()
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
        "timestamp": "06/06/2026 19:33:13",
        "target_price": 100.0
    }

    opp = adapter.from_lag_result(lag_result)
    val = validator.validate(opp)
    candidate = factory.from_validated_opportunity(val)

    simulator.force_buy_for_test(candidate, quantity=10, price=100.0)
    return simulator

def main():
    # Test 1 — HOLD
    print("=== TEST 1: HOLD ===")
    simulator = setup_simulation()
    
    decision_1 = simulator.create_exit_decision("HDFCNIFTY", current_price=100.20)
    print("Decision:")
    pprint.pprint(decision_1.to_dict())
    
    close_res_1 = simulator.close_position_from_decision(decision_1)
    print("Close Result:")
    pprint.pprint(close_res_1)
    
    print("Account State:")
    pprint.pprint(simulator.account.to_dict())
    print("-" * 50)

    # Test 2 — TAKE_PROFIT
    print("=== TEST 2: TAKE PROFIT ===")
    simulator = setup_simulation() # Reset simulator
    
    decision_2 = simulator.create_exit_decision("HDFCNIFTY", current_price=100.60)
    print("Decision:")
    pprint.pprint(decision_2.to_dict())
    
    close_res_2 = simulator.close_position_from_decision(decision_2)
    print("Close Result:")
    pprint.pprint(close_res_2)
    
    print("Account State:")
    pprint.pprint(simulator.account.to_dict())
    print("-" * 50)

    # Test 3 — STOP_LOSS
    print("=== TEST 3: STOP LOSS ===")
    simulator = setup_simulation() # Reset simulator
    
    decision_3 = simulator.create_exit_decision("HDFCNIFTY", current_price=99.70)
    print("Decision:")
    pprint.pprint(decision_3.to_dict())
    
    close_res_3 = simulator.close_position_from_decision(decision_3)
    print("Close Result:")
    pprint.pprint(close_res_3)
    
    print("Account State:")
    pprint.pprint(simulator.account.to_dict())
    print("-" * 50)

if __name__ == "__main__":
    main()
