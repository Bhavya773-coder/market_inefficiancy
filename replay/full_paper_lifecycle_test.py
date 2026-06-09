import pprint
from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
from ai.paper_trade_simulator import PaperTradeSimulator

def run_scenario_1():
    print("\n" + "="*50)
    print("SCENARIO 1 - PROFITABLE LIFECYCLE")
    print("="*50)

    # 1. Create lag_result
    lag_result = {
        "reference_symbol": "SETFNIF50",
        "target_symbol": "HDFCNIFTY",
        "reference_change": 0.40,
        "target_change": 0.03,
        "reaction_gap": 0.37,
        "same_direction": True,
        "is_lagging": True,
        "timestamp": "08/06/2026 13:03:27",
        "target_price": 100.0,
        "mock": False,
        "data_source": "offline_test"
    }

    # 2. Pass through
    adapter = OpportunityAdapter()
    validator = OpportunityValidator()
    candidate_factory = PaperTradeCandidateFactory()
    simulator = PaperTradeSimulator()

    opportunity = adapter.from_lag_result(lag_result)
    validation_result = validator.validate(opportunity)
    candidate = candidate_factory.from_validated_opportunity(validation_result)
    entry_decision = simulator.create_entry_decision(candidate, quantity=10, price=100.0)

    # 3. Execute entry decision
    entry_result = simulator.execute_entry_decision(entry_decision)

    import copy
    account_after_entry = copy.deepcopy(simulator.account.to_dict())

    # 4. Create exit decision
    exit_decision = simulator.create_exit_decision("HDFCNIFTY", current_price=100.60)

    # 5. Close position
    close_result = simulator.close_position_from_decision(exit_decision)

    final_account_state = simulator.account.to_dict()

    # Print results clearly
    print("\nopportunity:")
    pprint.pprint(opportunity.to_dict() if opportunity else None)

    print("\nvalidation_result:")
    pprint.pprint(validation_result)

    print("\ncandidate:")
    pprint.pprint(candidate.to_dict() if candidate else None)

    print("\nentry_decision:")
    pprint.pprint(entry_decision.to_dict() if entry_decision else None)

    print("\nentry_result:")
    pprint.pprint(entry_result)

    print("\naccount_after_entry:")
    pprint.pprint(account_after_entry)

    print("\nexit_decision:")
    pprint.pprint(exit_decision.to_dict() if exit_decision else None)

    print("\nclose_result:")
    pprint.pprint(close_result)

    print("\nfinal_account_state:")
    pprint.pprint(final_account_state)

    # Assertions to ensure logic is correct
    assert entry_result.get("status") == "filled"
    assert entry_result.get("side") == "BUY"
    assert account_after_entry.get("cash") == 99000
    assert "HDFCNIFTY" in account_after_entry.get("positions", {})
    assert exit_decision.action == "TAKE_PROFIT"
    assert close_result.get("status") == "filled"
    assert close_result.get("side") == "SELL"
    assert final_account_state.get("cash") == 100006
    assert "HDFCNIFTY" not in final_account_state.get("positions", {})


def run_scenario_2():
    print("\n" + "="*50)
    print("SCENARIO 2 - REJECTED LIFECYCLE")
    print("="*50)

    # 1. Create lag_result with small gap
    lag_result = {
        "reference_symbol": "SETFNIF50",
        "target_symbol": "HDFCNIFTY",
        "reference_change": 0.40,
        "target_change": 0.03,
        "reaction_gap": 0.05,
        "same_direction": True,
        "is_lagging": True,
        "timestamp": "08/06/2026 13:03:27",
        "target_price": 100.0,
        "mock": False,
        "data_source": "offline_test"
    }

    # 2. Pass through
    adapter = OpportunityAdapter()
    validator = OpportunityValidator()
    candidate_factory = PaperTradeCandidateFactory()
    simulator = PaperTradeSimulator()

    opportunity = adapter.from_lag_result(lag_result)
    validation_result = validator.validate(opportunity)
    candidate = candidate_factory.from_validated_opportunity(validation_result)
    entry_decision = simulator.create_entry_decision(candidate, quantity=10, price=100.0)

    # 3. Execute entry decision
    execute_result = simulator.execute_entry_decision(entry_decision)

    final_account_state = simulator.account.to_dict()

    # Print results clearly
    print("\nentry_decision:")
    pprint.pprint(entry_decision.to_dict() if entry_decision else None)

    print("\nexecute_entry_decision result:")
    pprint.pprint(execute_result)

    print("\nfinal_account_state:")
    pprint.pprint(final_account_state)

    # Assertions
    assert entry_decision.action == "REJECTED"
    assert execute_result.get("status") == "rejected"
    assert execute_result.get("reason") == "entry_not_allowed"
    assert len(final_account_state.get("positions", {})) == 0
    assert final_account_state.get("cash") == 100000


def main():
    run_scenario_1()
    run_scenario_2()

    # Safety prints
    print("\n" + "="*50)
    print("REAL ORDER APIs USED: NO")
    print("DHAN USED: NO")
    print("PAPER ONLY: YES")
    print("="*50)

if __name__ == "__main__":
    main()
