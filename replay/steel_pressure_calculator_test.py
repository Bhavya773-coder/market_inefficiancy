import json
from ai.steel_pressure_calculator import SteelPressureCalculator

def main():
    print("Instantiating SteelPressureCalculator...")
    calculator = SteelPressureCalculator()
    
    market_changes = {
        "IRON_ORE": 5.0,
        "COKING_COAL": 3.0,
        "SCRAP_STEEL": 1.0,
        "BALTIC_DRY": 2.0,
        "CRUDE_OIL": 1.5,
        "USDINR": 0.5,
        "NIFTY_METAL": 2.0,
        "TATASTEEL": 1.0,
        "JSWSTEEL": 1.0,
        "GOLD": -1.0
    }
    
    print("\nCalculating pressure scores...")
    result = calculator.calculate(market_changes)
    
    # 1. Print Full result
    print("\n--- Full Result ---")
    print(json.dumps(result, indent=2))
    
    # 2. Print STEEL_FUTURE result
    print("\n--- STEEL_FUTURE Result ---")
    future_res = result["targets"].get("STEEL_FUTURE")
    print(json.dumps(future_res, indent=2))
    
    # 3. Print STEEL_PHYSICAL_PLATE result
    print("\n--- STEEL_PHYSICAL_PLATE Result ---")
    plate_res = result["targets"].get("STEEL_PHYSICAL_PLATE")
    print(json.dumps(plate_res, indent=2))
    
    # Assertions
    print("\nRunning assertions...")
    
    assert "STEEL_FUTURE" in result["targets"], "Assertion failed: STEEL_FUTURE target is missing"
    assert "STEEL_PHYSICAL_PLATE" in result["targets"], "Assertion failed: STEEL_PHYSICAL_PLATE target is missing"
    
    assert future_res["pressure_score"] > 0, f"Assertion failed: STEEL_FUTURE pressure_score is {future_res['pressure_score']} (expected > 0)"
    assert plate_res["pressure_score"] > 0, f"Assertion failed: STEEL_PHYSICAL_PLATE pressure_score is {plate_res['pressure_score']} (expected > 0)"
    
    # Check new target-level fields
    assert future_res["applied_weight"] == 0.65, f"Expected applied_weight 0.65, got {future_res['applied_weight']}"
    assert future_res["skipped_mixed_weight"] == 0.05, f"Expected skipped_mixed_weight 0.05, got {future_res['skipped_mixed_weight']}"
    assert "GOLD" in future_res["skipped_sources"], "Expected GOLD in skipped_sources"
    
    assert len(future_res["contributors"]) > 0, "Assertion failed: STEEL_FUTURE contributors list is empty"
    assert len(plate_res["contributors"]) > 0, "Assertion failed: STEEL_PHYSICAL_PLATE contributors list is empty"
    
    # Check contributor fields
    for contrib in future_res["contributors"]:
        assert "relationship_direction" in contrib, "Missing relationship_direction in contributor"
        assert "direction_multiplier" in contrib, "Missing direction_multiplier in contributor"
        assert contrib["relationship_direction"] in ("positive", "negative"), "Invalid relationship direction"
        
    # Check that sorting is descending by absolute contribution
    contribs_future = future_res["contributors"]
    for i in range(len(contribs_future) - 1):
        c1 = abs(contribs_future[i]["contribution"])
        c2 = abs(contribs_future[i+1]["contribution"])
        assert c1 >= c2, f"Assertion failed: Contributors not sorted by absolute contribution. {c1} < {c2}"
        
    print("All assertions passed successfully!")

if __name__ == "__main__":
    main()
