import pprint
from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
from ai.paper_trading_engine import PaperTradingEngine

def make_candidate(reaction_gap):
    """
    Helper to generate a PaperTradeCandidate object from a mock lag_result.
    """
    lag_result = {
        "reference_symbol": "SETFNIF50",
        "target_symbol": "HDFCNIFTY",
        "reference_change": 0.40,
        "target_change": 0.03,
        "reaction_gap": reaction_gap,
        "same_direction": True,
        "is_lagging": True,
        "timestamp": "08/06/2026 13:03:27",
        "target_price": 100.0,
        "mock": False,
        "data_source": "offline_test"
    }

    adapter = OpportunityAdapter()
    validator = OpportunityValidator()
    factory = PaperTradeCandidateFactory()

    opp = adapter.from_lag_result(lag_result)
    val = validator.validate(opp)
    candidate = factory.from_validated_opportunity(val)
    return candidate

def run_test_1():
    print("\n" + "="*50)
    print("TEST 1 - ACCEPTED ENTRY THEN TAKE PROFIT")
    print("="*50)

    candidate = make_candidate(0.37)
    engine = PaperTradingEngine()
    
    # Process Candidate Entry
    entry_report = engine.process_candidate(candidate, quantity=10, price=100.0)
    print("\nEntry Report:")
    pprint.pprint(entry_report)

    assert entry_report["execution"]["status"] == "filled"
    assert entry_report["execution"]["side"] == "BUY"
    assert entry_report["decision"]["action"] == "BUY_ALLOWED"

    # Process Price Update for Exit
    exit_report = engine.process_price_update("HDFCNIFTY", current_price=100.60)
    print("\nExit Report:")
    pprint.pprint(exit_report)

    assert exit_report["decision"]["action"] == "TAKE_PROFIT"
    assert exit_report["execution"]["status"] == "filled"
    assert exit_report["execution"]["side"] == "SELL"
    assert exit_report["account"]["cash"] == 100006
    assert len(exit_report["account"]["positions"]) == 0

def run_test_2():
    print("\n" + "="*50)
    print("TEST 2 - REJECTED ENTRY")
    print("="*50)

    candidate = make_candidate(0.05)
    engine = PaperTradingEngine()
    
    entry_report = engine.process_candidate(candidate, quantity=10, price=100.0)
    print("\nEntry Report:")
    pprint.pprint(entry_report)

    assert entry_report["decision"]["action"] == "REJECTED"
    assert entry_report["execution"]["status"] == "rejected"
    assert len(entry_report["account"]["positions"]) == 0
    assert entry_report["account"]["cash"] == 100000

def run_test_3():
    print("\n" + "="*50)
    print("TEST 3 - NO POSITION EXIT SAFETY")
    print("="*50)

    engine = PaperTradingEngine()
    
    exit_report = engine.process_price_update("HDFCNIFTY", current_price=101.00)
    print("\nExit Report:")
    pprint.pprint(exit_report)

    assert exit_report["execution"]["status"] == "rejected"
    assert exit_report["account"]["cash"] == 100000
    assert len(exit_report["account"]["positions"]) == 0

def main():
    run_test_1()
    run_test_2()
    run_test_3()

    # Safety Prints
    print("\n" + "="*50)
    print("REAL ORDER APIs USED: NO")
    print("DHAN USED: NO")
    print("PAPER ONLY: YES")
    print("="*50)

if __name__ == "__main__":
    main()
