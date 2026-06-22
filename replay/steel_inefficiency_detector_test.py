import json
import math
from ai.steel_inefficiency_detector import SteelInefficiencyDetector

def main():
    print("Instantiating SteelInefficiencyDetector...")
    detector = SteelInefficiencyDetector()

    # Define standard market changes (excluding targets)
    base_drivers = {
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

    # -------------------------------------------------------------------------
    # SCENARIO 1 — Bullish underreaction
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("SCENARIO 1 — Bullish underreaction")
    print("==================================================")
    changes_s1 = dict(base_drivers)
    changes_s1["STEEL_FUTURE"] = 0.20
    changes_s1["STEEL_PHYSICAL_PLATE"] = 0.10

    res_s1 = detector.detect(changes_s1)
    print("Bullish underreaction result:")
    print(json.dumps(res_s1, indent=2))

    # Assertions
    future_s1 = res_s1["targets"]["STEEL_FUTURE"]
    assert future_s1 is not None, "STEEL_FUTURE missing in result"
    assert future_s1["coverage_ratio"] == 1.0, f"Expected coverage_ratio 1.0, got {future_s1['coverage_ratio']}"
    assert future_s1["expected_change"] > future_s1["actual_change"], "Expected expected_change > actual_change"
    assert future_s1["status"] in ["UNDERREACTION", "NON_REACTION"], f"Expected status UNDERREACTION/NON_REACTION, got {future_s1['status']}"
    assert future_s1["is_inefficient"] is True, "Expected is_inefficient to be True"
    assert future_s1["recommended_direction"] == "LONG_TARGET", f"Expected recommended_direction LONG_TARGET, got {future_s1['recommended_direction']}"
    assert len(future_s1["contributors"]) > 0, "Contributors should not be empty"


    # -------------------------------------------------------------------------
    # SCENARIO 2 — Efficient reaction
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("SCENARIO 2 — Efficient reaction")
    print("==================================================")
    
    # Dynamically extract expected change for STEEL_FUTURE from Scenario 1
    expected_future_s1 = future_s1["expected_change"]
    
    changes_s2 = dict(base_drivers)
    changes_s2["STEEL_FUTURE"] = expected_future_s1
    changes_s2["STEEL_PHYSICAL_PLATE"] = 0.40  # Just set some valid plate actual value

    res_s2 = detector.detect(changes_s2)
    print("Efficient reaction result:")
    print(json.dumps(res_s2, indent=2))

    # Assertions
    future_s2 = res_s2["targets"]["STEEL_FUTURE"]
    assert future_s2["status"] == "EFFICIENT", f"Expected status EFFICIENT, got {future_s2['status']}"
    assert future_s2["is_inefficient"] is False, "Expected is_inefficient to be False"
    assert future_s2["recommended_direction"] == "NO_TRADE", f"Expected recommended_direction NO_TRADE, got {future_s2['recommended_direction']}"
    assert abs(future_s2["absolute_gap"]) < 1e-5, f"Expected absolute_gap ~0, got {future_s2['absolute_gap']}"


    # -------------------------------------------------------------------------
    # SCENARIO 3 — Bearish underreaction
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("SCENARIO 3 — Bearish underreaction")
    print("==================================================")
    changes_s3 = {
        "IRON_ORE": -5.0,
        "COKING_COAL": -3.0,
        "SCRAP_STEEL": -1.0,
        "BALTIC_DRY": -2.0,
        "CRUDE_OIL": -1.5,
        "USDINR": -0.5,
        "NIFTY_METAL": -2.0,
        "TATASTEEL": -1.0,
        "JSWSTEEL": -1.0,
        "GOLD": 1.0,
        "STEEL_FUTURE": -0.10,
        "STEEL_PHYSICAL_PLATE": -0.10
    }

    res_s3 = detector.detect(changes_s3)
    print("Bearish underreaction result:")
    print(json.dumps(res_s3, indent=2))

    # Assertions
    future_s3 = res_s3["targets"]["STEEL_FUTURE"]
    assert future_s3["expected_change"] < 0, f"Expected expected_change < 0, got {future_s3['expected_change']}"
    assert future_s3["residual_gap"] < 0, f"Expected residual_gap < 0, got {future_s3['residual_gap']}"
    assert future_s3["is_inefficient"] is True, "Expected is_inefficient to be True"
    assert future_s3["recommended_direction"] == "SHORT_TARGET", f"Expected recommended_direction SHORT_TARGET, got {future_s3['recommended_direction']}"
    assert future_s3["status"] in ["UNDERREACTION", "NON_REACTION"], f"Expected status UNDERREACTION/NON_REACTION, got {future_s3['status']}"


    # -------------------------------------------------------------------------
    # SCENARIO 4 — Divergence
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("SCENARIO 4 — Divergence")
    print("==================================================")
    changes_s4 = dict(base_drivers)
    changes_s4["STEEL_FUTURE"] = -1.0
    changes_s4["STEEL_PHYSICAL_PLATE"] = 0.10

    res_s4 = detector.detect(changes_s4)
    print("Divergence result:")
    print(json.dumps(res_s4, indent=2))

    # Assertions
    future_s4 = res_s4["targets"]["STEEL_FUTURE"]
    assert future_s4["status"] == "DIVERGENCE", f"Expected status DIVERGENCE, got {future_s4['status']}"
    assert future_s4["is_inefficient"] is True, "Expected is_inefficient to be True"
    assert future_s4["recommended_direction"] == "LONG_TARGET", f"Expected recommended_direction LONG_TARGET, got {future_s4['recommended_direction']}"


    # -------------------------------------------------------------------------
    # SCENARIO 5 — Overreaction
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("SCENARIO 5 — Overreaction")
    print("==================================================")
    changes_s5 = dict(base_drivers)
    # expected_change for STEEL_FUTURE is ~2.571428.
    # Set actual to expected_change + 2.0
    changes_s5["STEEL_FUTURE"] = expected_future_s1 + 2.0
    changes_s5["STEEL_PHYSICAL_PLATE"] = 0.10

    res_s5 = detector.detect(changes_s5)
    print("Overreaction result:")
    print(json.dumps(res_s5, indent=2))

    # Assertions
    future_s5 = res_s5["targets"]["STEEL_FUTURE"]
    assert future_s5["status"] == "OVERREACTION", f"Expected status OVERREACTION, got {future_s5['status']}"
    assert future_s5["is_inefficient"] is True, "Expected is_inefficient to be True"
    assert future_s5["recommended_direction"] == "SHORT_TARGET", f"Expected recommended_direction SHORT_TARGET, got {future_s5['recommended_direction']}"


    # -------------------------------------------------------------------------
    # SCENARIO 6 — Low driver coverage
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("SCENARIO 6 — Low driver coverage")
    print("==================================================")
    custom_detector = SteelInefficiencyDetector(min_coverage_ratio=0.80)
    changes_s6 = {
        "IRON_ORE": 5.0,
        "STEEL_FUTURE": 0.20
    }

    res_s6 = custom_detector.detect(changes_s6)
    print("Low-coverage result:")
    print(json.dumps(res_s6, indent=2))

    # Assertions
    future_s6 = res_s6["targets"]["STEEL_FUTURE"]
    assert future_s6["status"] == "LOW_COVERAGE", f"Expected status LOW_COVERAGE, got {future_s6['status']}"
    assert future_s6["is_inefficient"] is False, "Expected is_inefficient to be False"
    assert future_s6["recommended_direction"] == "NO_TRADE", f"Expected recommended_direction NO_TRADE, got {future_s6['recommended_direction']}"


    # -------------------------------------------------------------------------
    # SCENARIO 7 — Missing target movement
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("SCENARIO 7 — Missing target movement")
    print("==================================================")
    changes_s7 = dict(base_drivers)
    # STEEL_FUTURE is omitted!

    res_s7 = detector.detect(changes_s7)
    print("Missing-target result:")
    print(json.dumps(res_s7, indent=2))

    # Assertions
    future_s7 = res_s7["targets"]["STEEL_FUTURE"]
    assert future_s7["status"] == "INSUFFICIENT_DATA", f"Expected status INSUFFICIENT_DATA, got {future_s7['status']}"
    assert future_s7["is_inefficient"] is False, "Expected is_inefficient to be False"
    assert future_s7["recommended_direction"] == "NO_TRADE", f"Expected recommended_direction NO_TRADE, got {future_s7['recommended_direction']}"


    # -------------------------------------------------------------------------
    # SCENARIO 8 — Input validation
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("SCENARIO 8 — Input validation")
    print("==================================================")
    
    # 8.1 detect(None)
    try:
        detector.detect(None)
        assert False, "Expected TypeError for None input"
    except TypeError as e:
        print(f"Passed: detect(None) raised TypeError: {e}")

    # 8.2 String market-change value
    try:
        detector.detect({"IRON_ORE": "5.0"})
        assert False, "Expected TypeError for string value"
    except TypeError as e:
        print(f"Passed: detect(string) raised TypeError: {e}")

    # 8.3 Bool market-change value
    try:
        detector.detect({"IRON_ORE": True})
        assert False, "Expected TypeError for bool value"
    except TypeError as e:
        print(f"Passed: detect(bool) raised TypeError: {e}")

    # 8.4 NaN
    try:
        detector.detect({"IRON_ORE": float("nan")})
        assert False, "Expected ValueError for NaN value"
    except ValueError as e:
        print(f"Passed: detect(NaN) raised ValueError: {e}")

    # 8.5 Infinite
    try:
        detector.detect({"IRON_ORE": float("inf")})
        assert False, "Expected ValueError for Inf value"
    except ValueError as e:
        print(f"Passed: detect(Inf) raised ValueError: {e}")

    print("\nAll SteelInefficiencyDetector assertions passed.")

if __name__ == "__main__":
    main()
