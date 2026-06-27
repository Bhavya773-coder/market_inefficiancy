import json
import math
import copy
from ai.steel_pressure_calculator import SteelPressureCalculator
from ai.steel_inefficiency_detector import SteelInefficiencyDetector

def main():
    print("Starting exact regression tests...")
    
    # Base positive drivers (excluding targets)
    base_positive_drivers = {
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

    # Base negative drivers (excluding targets)
    base_negative_drivers = {
        "IRON_ORE": -5.0,
        "COKING_COAL": -3.0,
        "SCRAP_STEEL": -1.0,
        "BALTIC_DRY": -2.0,
        "CRUDE_OIL": -1.5,
        "USDINR": -0.5,
        "NIFTY_METAL": -2.0,
        "TATASTEEL": -1.0,
        "JSWSTEEL": -1.0,
        "GOLD": 1.0
    }

    detector = SteelInefficiencyDetector()

    # -------------------------------------------------------------------------
    # SCENARIO 1 — Exact NON_REACTION boundary
    # -------------------------------------------------------------------------
    print("\nScenario 1: Exact NON_REACTION boundary")
    changes_s1 = dict(base_positive_drivers)
    changes_s1["STEEL_FUTURE"] = 0.20
    changes_s1["STEEL_PHYSICAL_PLATE"] = 0.10
    
    res_s1 = detector.detect(changes_s1)
    future_s1 = res_s1["targets"]["STEEL_FUTURE"]
    print(f"STEEL_FUTURE expected: {future_s1['expected_change']}, actual: {future_s1['actual_change']}, status: {future_s1['status']}")
    
    assert future_s1["status"] == "NON_REACTION", f"Expected NON_REACTION, got {future_s1['status']}"
    assert future_s1["is_inefficient"] is True
    assert future_s1["recommended_direction"] == "LONG_TARGET"

    # -------------------------------------------------------------------------
    # SCENARIO 2 — Bullish UNDERREACTION
    # -------------------------------------------------------------------------
    print("\nScenario 2: Bullish UNDERREACTION")
    changes_s2 = dict(base_positive_drivers)
    changes_s2["STEEL_FUTURE"] = 0.50
    changes_s2["STEEL_PHYSICAL_PLATE"] = 0.10
    
    res_s2 = detector.detect(changes_s2)
    future_s2 = res_s2["targets"]["STEEL_FUTURE"]
    print(f"STEEL_FUTURE expected: {future_s2['expected_change']}, actual: {future_s2['actual_change']}, status: {future_s2['status']}")
    
    assert future_s2["status"] == "UNDERREACTION", f"Expected UNDERREACTION, got {future_s2['status']}"
    assert future_s2["is_inefficient"] is True
    assert future_s2["recommended_direction"] == "LONG_TARGET"

    # -------------------------------------------------------------------------
    # SCENARIO 3 — Bearish NON_REACTION
    # -------------------------------------------------------------------------
    print("\nScenario 3: Bearish NON_REACTION")
    changes_s3 = dict(base_negative_drivers)
    changes_s3["STEEL_FUTURE"] = -0.20
    changes_s3["STEEL_PHYSICAL_PLATE"] = -0.10
    
    res_s3 = detector.detect(changes_s3)
    future_s3 = res_s3["targets"]["STEEL_FUTURE"]
    print(f"STEEL_FUTURE expected: {future_s3['expected_change']}, actual: {future_s3['actual_change']}, status: {future_s3['status']}")
    
    assert future_s3["status"] == "NON_REACTION", f"Expected NON_REACTION, got {future_s3['status']}"
    assert future_s3["is_inefficient"] is True
    assert future_s3["recommended_direction"] == "SHORT_TARGET"
    assert "downward reaction" in future_s3["explanation"]

    # -------------------------------------------------------------------------
    # SCENARIO 4 — Bearish UNDERREACTION
    # -------------------------------------------------------------------------
    print("\nScenario 4: Bearish UNDERREACTION")
    changes_s4 = dict(base_negative_drivers)
    changes_s4["STEEL_FUTURE"] = -0.50
    changes_s4["STEEL_PHYSICAL_PLATE"] = -0.10
    
    res_s4 = detector.detect(changes_s4)
    future_s4 = res_s4["targets"]["STEEL_FUTURE"]
    print(f"STEEL_FUTURE expected: {future_s4['expected_change']}, actual: {future_s4['actual_change']}, status: {future_s4['status']}")
    
    assert future_s4["status"] == "UNDERREACTION", f"Expected UNDERREACTION, got {future_s4['status']}"
    assert future_s4["is_inefficient"] is True
    assert future_s4["recommended_direction"] == "SHORT_TARGET"
    assert "Expected negative movement" in future_s4["explanation"], f"Wrong explanation: {future_s4['explanation']}"
    assert "magnitude" in future_s4["explanation"]

    # -------------------------------------------------------------------------
    # SCENARIO 5 — Efficient reaction
    # -------------------------------------------------------------------------
    print("\nScenario 5: Efficient reaction")
    # Determine the expected changes from a preliminary run
    res_pref = detector.detect(base_positive_drivers)
    expected_future = res_pref["targets"]["STEEL_FUTURE"]["expected_change"]
    expected_plate = res_pref["targets"]["STEEL_PHYSICAL_PLATE"]["expected_change"]
    
    changes_s5 = dict(base_positive_drivers)
    changes_s5["STEEL_FUTURE"] = expected_future
    changes_s5["STEEL_PHYSICAL_PLATE"] = expected_plate
    
    res_s5 = detector.detect(changes_s5)
    future_s5 = res_s5["targets"]["STEEL_FUTURE"]
    plate_s5 = res_s5["targets"]["STEEL_PHYSICAL_PLATE"]
    print(f"STEEL_FUTURE expected: {future_s5['expected_change']}, actual: {future_s5['actual_change']}, status: {future_s5['status']}")
    print(f"STEEL_PHYSICAL_PLATE expected: {plate_s5['expected_change']}, actual: {plate_s5['actual_change']}, status: {plate_s5['status']}")
    
    assert future_s5["status"] == "EFFICIENT", f"Expected EFFICIENT, got {future_s5['status']}"
    assert future_s5["is_inefficient"] is False
    assert abs(future_s5["absolute_gap"]) < 1e-5
    
    assert plate_s5["status"] == "EFFICIENT", f"Expected EFFICIENT, got {plate_s5['status']}"
    assert plate_s5["is_inefficient"] is False
    assert abs(plate_s5["absolute_gap"]) < 1e-5

    # -------------------------------------------------------------------------
    # SCENARIO 6 — Divergence
    # -------------------------------------------------------------------------
    print("\nScenario 6: Divergence")
    changes_s6 = dict(base_positive_drivers)
    changes_s6["STEEL_FUTURE"] = -1.0
    changes_s6["STEEL_PHYSICAL_PLATE"] = 0.10
    
    res_s6 = detector.detect(changes_s6)
    future_s6 = res_s6["targets"]["STEEL_FUTURE"]
    print(f"STEEL_FUTURE expected: {future_s6['expected_change']}, actual: {future_s6['actual_change']}, status: {future_s6['status']}")
    
    assert future_s6["status"] == "DIVERGENCE", f"Expected DIVERGENCE, got {future_s6['status']}"
    assert future_s6["is_inefficient"] is True
    assert future_s6["recommended_direction"] == "LONG_TARGET"

    # -------------------------------------------------------------------------
    # SCENARIO 7 — Positive overreaction
    # -------------------------------------------------------------------------
    print("\nScenario 7: Positive overreaction")
    changes_s7 = dict(base_positive_drivers)
    changes_s7["STEEL_FUTURE"] = expected_future + 2.0
    changes_s7["STEEL_PHYSICAL_PLATE"] = expected_plate
    
    res_s7 = detector.detect(changes_s7)
    future_s7 = res_s7["targets"]["STEEL_FUTURE"]
    print(f"STEEL_FUTURE expected: {future_s7['expected_change']}, actual: {future_s7['actual_change']}, status: {future_s7['status']}")
    
    assert future_s7["status"] == "OVERREACTION", f"Expected OVERREACTION, got {future_s7['status']}"
    assert future_s7["is_inefficient"] is True
    assert future_s7["recommended_direction"] == "SHORT_TARGET"

    # -------------------------------------------------------------------------
    # SCENARIO 8 — Negative overreaction
    # -------------------------------------------------------------------------
    print("\nScenario 8: Negative overreaction")
    res_pref_neg = detector.detect(base_negative_drivers)
    expected_future_neg = res_pref_neg["targets"]["STEEL_FUTURE"]["expected_change"]
    
    changes_s8 = dict(base_negative_drivers)
    changes_s8["STEEL_FUTURE"] = expected_future_neg - 2.0
    changes_s8["STEEL_PHYSICAL_PLATE"] = -1.0
    
    res_s8 = detector.detect(changes_s8)
    future_s8 = res_s8["targets"]["STEEL_FUTURE"]
    print(f"STEEL_FUTURE expected: {future_s8['expected_change']}, actual: {future_s8['actual_change']}, status: {future_s8['status']}")
    
    assert future_s8["status"] == "OVERREACTION", f"Expected OVERREACTION, got {future_s8['status']}"
    assert future_s8["is_inefficient"] is True
    assert future_s8["recommended_direction"] == "LONG_TARGET"

    # -------------------------------------------------------------------------
    # SCENARIO 9 — Low coverage
    # -------------------------------------------------------------------------
    print("\nScenario 9: Low coverage")
    custom_detector = SteelInefficiencyDetector(min_coverage_ratio=0.80)
    changes_s9 = {
        "IRON_ORE": 5.0,
        "STEEL_FUTURE": 0.20
    }
    
    res_s9 = custom_detector.detect(changes_s9)
    future_s9 = res_s9["targets"]["STEEL_FUTURE"]
    print(f"STEEL_FUTURE coverage_ratio: {future_s9['coverage_ratio']}, status: {future_s9['status']}")
    
    assert future_s9["status"] == "LOW_COVERAGE"
    assert future_s9["is_inefficient"] is False
    assert future_s9["recommended_direction"] == "NO_TRADE"

    # -------------------------------------------------------------------------
    # SCENARIO 10 — Missing target
    # -------------------------------------------------------------------------
    print("\nScenario 10: Missing target")
    changes_s10 = dict(base_positive_drivers)
    # STEEL_FUTURE is not set
    res_s10 = detector.detect(changes_s10)
    future_s10 = res_s10["targets"]["STEEL_FUTURE"]
    print(f"STEEL_FUTURE status: {future_s10['status']}")
    
    assert future_s10["status"] == "INSUFFICIENT_DATA"
    assert future_s10["is_inefficient"] is False
    assert future_s10["recommended_direction"] == "NO_TRADE"

    # -------------------------------------------------------------------------
    # SCENARIO 11 — Mixed relationship handling
    # -------------------------------------------------------------------------
    print("\nScenario 11: Mixed relationship handling")
    # Instantiate calculator and test target fields
    calculator = SteelPressureCalculator()
    calc_res = calculator.calculate(base_positive_drivers)
    calc_target = calc_res["targets"]["STEEL_FUTURE"]
    
    # GOLD (mixed) must not be in applied contributors
    applied_sources = [c["source"] for c in calc_target["contributors"]]
    assert "GOLD" not in applied_sources, "GOLD should not be in applied contributors"
    
    # GOLD must be in skipped_sources
    assert "GOLD" in calc_target["skipped_sources"], "GOLD must be in skipped_sources"
    
    # skipped_mixed_weight should be > 0 (GOLD weight is 0.05)
    assert calc_target["skipped_mixed_weight"] > 0, "skipped_mixed_weight should be > 0"
    
    # Check coverage calculation excluding GOLD
    det_res = detector.detect(base_positive_drivers)
    det_target = det_res["targets"]["STEEL_FUTURE"]
    # Total possible weight of non-mixed drivers for STEEL_FUTURE is 0.65
    assert abs(det_target["total_possible_weight"] - 0.65) < 1e-5, f"Expected 0.65, got {det_target['total_possible_weight']}"
    
    # Changing only GOLD must not change STEEL_FUTURE pressure_score
    drivers_gold_1 = dict(base_positive_drivers)
    drivers_gold_1["GOLD"] = 10.0
    drivers_gold_2 = dict(base_positive_drivers)
    drivers_gold_2["GOLD"] = -10.0
    
    score_1 = calculator.calculate(drivers_gold_1)["targets"]["STEEL_FUTURE"]["pressure_score"]
    score_2 = calculator.calculate(drivers_gold_2)["targets"]["STEEL_FUTURE"]["pressure_score"]
    assert score_1 == score_2, f"GOLD changes altered pressure score: {score_1} vs {score_2}"
    print("GOLD mixed relationship skipped successfully from pressure and coverage calculations.")

    # -------------------------------------------------------------------------
    # SCENARIO 12 — Input immutability
    # -------------------------------------------------------------------------
    print("\nScenario 12: Input immutability")
    input_orig = copy.deepcopy(base_positive_drivers)
    
    _ = calculator.calculate(base_positive_drivers)
    assert base_positive_drivers == input_orig, "calculate() mutated input market_changes dictionary"
    
    _ = detector.detect(base_positive_drivers)
    assert base_positive_drivers == input_orig, "detect() mutated input market_changes dictionary"
    print("Verified input immutability.")

    # -------------------------------------------------------------------------
    # SCENARIO 13 — Input validation
    # -------------------------------------------------------------------------
    print("\nScenario 13: Input validation")
    # None
    try:
        detector.detect(None)
        assert False, "None was not rejected"
    except TypeError:
        pass

    # string value
    try:
        detector.detect({"IRON_ORE": "1.0"})
        assert False, "string value was not rejected"
    except TypeError:
        pass

    # bool value
    try:
        detector.detect({"IRON_ORE": True})
        assert False, "bool value was not rejected"
    except TypeError:
        pass

    # NaN
    try:
        detector.detect({"IRON_ORE": float("nan")})
        assert False, "NaN was not rejected"
    except ValueError:
        pass

    # positive infinity
    try:
        detector.detect({"IRON_ORE": float("inf")})
        assert False, "+inf was not rejected"
    except ValueError:
        pass

    # negative infinity
    try:
        detector.detect({"IRON_ORE": float("-inf")})
        assert False, "-inf was not rejected"
    except ValueError:
        pass
    print("All input validations successfully rejected bad data.")

    # -------------------------------------------------------------------------
    # SCENARIO 14 — Output metadata
    # -------------------------------------------------------------------------
    print("\nScenario 14: Output metadata")
    res_s14 = detector.detect(base_positive_drivers)
    target_s14 = res_s14["targets"]["STEEL_FUTURE"]
    
    assert target_s14["expected_change_basis"] == "weighted_average_directional_driver_change_proxy", f"Got basis: {target_s14['expected_change_basis']}"
    assert target_s14["is_historically_calibrated"] is False, "is_historically_calibrated should be False"
    print("Metadata fields successfully verified.")

    print("\nAll hardened steel pressure and inefficiency regression assertions passed.")

if __name__ == "__main__":
    main()
