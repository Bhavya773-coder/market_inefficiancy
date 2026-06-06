from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator

def main():
    adapter = OpportunityAdapter()
    validator = OpportunityValidator()

    # Test 1: Valid lag opportunity
    lag_result_1 = {
        "reference_symbol": "NIFTYBEES",
        "target_symbol": "HDFCNIFTY",
        "reference_change": 0.40,
        "target_change": 0.03,
        "reaction_gap": 0.37,
        "same_direction": True,
        "is_lagging": True,
        "timestamp": "06/06/2026 19:33:13"
    }
    opp_1 = adapter.from_lag_result(lag_result_1)
    res_1 = validator.validate(opp_1)
    print("Test 1 - Valid Opportunity:")
    print(f"is_valid: {res_1['is_valid']}")
    print(f"reason: {res_1.get('reason')}")
    print(f"opportunity: {res_1['opportunity']}")
    print("-" * 50)

    # Test 2: Non-lag lag_result (is_lagging=False)
    lag_result_2 = {
        "reference_symbol": "NIFTYBEES",
        "target_symbol": "HDFCNIFTY",
        "reference_change": 0.40,
        "target_change": 0.03,
        "reaction_gap": 0.37,
        "same_direction": True,
        "is_lagging": False,
        "timestamp": "06/06/2026 19:33:13"
    }
    opp_2 = adapter.from_lag_result(lag_result_2)
    res_2 = validator.validate(opp_2)
    print("Test 2 - Non-lag Opportunity:")
    print(f"is_valid: {res_2['is_valid']}")
    print(f"reason: {res_2.get('reason')}")
    print(f"opportunity: {res_2['opportunity']}")
    print("-" * 50)

    # Test 3: Valid-looking but mock: True
    lag_result_3 = {
        "reference_symbol": "NIFTYBEES",
        "target_symbol": "HDFCNIFTY",
        "reference_change": 0.40,
        "target_change": 0.03,
        "reaction_gap": 0.37,
        "same_direction": True,
        "is_lagging": True,
        "timestamp": "06/06/2026 19:33:13",
        "mock": True
    }
    opp_3 = adapter.from_lag_result(lag_result_3)
    res_3 = validator.validate(opp_3)
    print("Test 3 - Mock Opportunity:")
    print(f"is_valid: {res_3['is_valid']}")
    print(f"reason: {res_3.get('reason')}")
    print(f"opportunity: {res_3['opportunity']}")
    print("-" * 50)

if __name__ == "__main__":
    main()
