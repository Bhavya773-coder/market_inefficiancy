from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
from ai.paper_trade_simulator import PaperTradeSimulator
import pprint

def main():
    # Setup simulator and pipeline
    simulator = PaperTradeSimulator()
    adapter = OpportunityAdapter()
    validator = OpportunityValidator()
    factory = PaperTradeCandidateFactory()

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

    # Pipeline
    opp = adapter.from_lag_result(lag_result)
    val = validator.validate(opp)
    candidate = factory.from_validated_opportunity(val)

    # Force buy
    print("Pre-buy positions:", simulator.account.positions)
    buy_result = simulator.force_buy_for_test(candidate, quantity=10, price=100.0)
    print("Buy result:", buy_result)
    print("Post-buy positions:", simulator.account.positions)
    print("-" * 50)

    # Test 1: current_price = 100.20
    dec_1 = simulator.create_exit_decision("HDFCNIFTY", current_price=100.20)
    print("Test 1 — Current Price: 100.20 (Expected action: HOLD)")
    if dec_1:
        pprint.pprint(dec_1.to_dict())
    else:
        print("Decision is None")
    print("-" * 50)

    # Test 2: current_price = 100.60
    dec_2 = simulator.create_exit_decision("HDFCNIFTY", current_price=100.60)
    print("Test 2 — Current Price: 100.60 (Expected action: TAKE_PROFIT)")
    if dec_2:
        pprint.pprint(dec_2.to_dict())
    else:
        print("Decision is None")
    print("-" * 50)

    # Test 3: current_price = 99.70
    dec_3 = simulator.create_exit_decision("HDFCNIFTY", current_price=99.70)
    print("Test 3 — Current Price: 99.70 (Expected action: STOP_LOSS)")
    if dec_3:
        pprint.pprint(dec_3.to_dict())
    else:
        print("Decision is None")
    print("-" * 50)

if __name__ == "__main__":
    main()
