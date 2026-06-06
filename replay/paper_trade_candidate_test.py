from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory

def main():
    adapter = OpportunityAdapter()
    validator = OpportunityValidator()
    factory = PaperTradeCandidateFactory()

    # Test 1: Valid lag opportunity candidate creation
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
    val_1 = validator.validate(opp_1)
    candidate_1 = factory.from_validated_opportunity(val_1)
    
    print("Test 1 - Valid Lag Result:")
    if candidate_1:
        print("Candidate created successfully:")
        import pprint
        pprint.pprint(candidate_1.to_dict())
    else:
        print("Candidate is None.")
    print("-" * 50)

    # Test 2: Mock lag result with mock=True candidate creation
    lag_result_2 = {
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
    
    opp_2 = adapter.from_lag_result(lag_result_2)
    val_2 = validator.validate(opp_2)
    candidate_2 = factory.from_validated_opportunity(val_2)
    
    print("Test 2 - Mock Lag Result:")
    if candidate_2:
        print("Candidate created (Expected: None):")
        import pprint
        pprint.pprint(candidate_2.to_dict())
    else:
        print("Candidate is None.")
    print("-" * 50)

if __name__ == "__main__":
    main()
