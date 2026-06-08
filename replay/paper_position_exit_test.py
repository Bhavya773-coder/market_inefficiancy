from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
from ai.paper_trade_simulator import PaperTradeSimulator
import pprint

def main():
    # 1. Setup simulator and pipeline
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

    # 3. Force buy
    print("Pre-buy account positions:", simulator.account.positions)
    buy_result = simulator.force_buy_for_test(candidate, quantity=10, price=100.0)
    print("Buy result:", buy_result)
    print("Post-buy account positions:", simulator.account.positions)
    print("-" * 50)

    # Test 1: Evaluate current_price = 100.20
    # Expected: HOLD (0.20% profit is less than 0.50% target and greater than -0.25% stop)
    res_1 = simulator.evaluate_position_exit("HDFCNIFTY", current_price=100.20)
    print("Test 1 — Current Price: 100.20 (Expected: HOLD)")
    pprint.pprint(res_1)
    print("-" * 50)

    # Test 2: Evaluate current_price = 100.60
    # Expected: TAKE_PROFIT (0.60% profit >= 0.50% target)
    res_2 = simulator.evaluate_position_exit("HDFCNIFTY", current_price=100.60)
    print("Test 2 — Current Price: 100.60 (Expected: TAKE_PROFIT)")
    pprint.pprint(res_2)
    print("-" * 50)

    # Test 3: Evaluate current_price = 99.70
    # Expected: STOP_LOSS (-0.30% loss <= -0.25% stop)
    res_3 = simulator.evaluate_position_exit("HDFCNIFTY", current_price=99.70)
    print("Test 3 — Current Price: 99.70 (Expected: STOP_LOSS)")
    pprint.pprint(res_3)
    print("-" * 50)

if __name__ == "__main__":
    main()
