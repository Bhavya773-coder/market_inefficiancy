import math
from typing import Dict, Any, List, Optional
from ai.gold_pressure_calculator import GoldPressureCalculator
from ai.gold_commodity_instrument_registry import GoldCommodityInstrumentRegistry

class GoldInefficiencyDetector:
    """
    Detects and classifies gold target inefficiencies relative to macro drivers.
    """
    def __init__(
        self,
        pressure_calculator: Optional[GoldPressureCalculator] = None,
        minimum_pressure_threshold: float = 0.50,
        minimum_coverage_ratio: float = 0.50,
        efficient_gap_threshold: float = 0.75,
        overreaction_multiplier: float = 1.5
    ):
        self.calculator = pressure_calculator if pressure_calculator is not None else GoldPressureCalculator(
            minimum_coverage_ratio=minimum_coverage_ratio
        )
        
        if type(minimum_pressure_threshold) is bool or not isinstance(minimum_pressure_threshold, (int, float)):
            raise TypeError("minimum_pressure_threshold must be a float or int and not bool")
        self.minimum_pressure_threshold = float(minimum_pressure_threshold)
        
        if type(minimum_coverage_ratio) is bool or not isinstance(minimum_coverage_ratio, (int, float)):
            raise TypeError("minimum_coverage_ratio must be a float or int and not bool")
        self.minimum_coverage_ratio = float(minimum_coverage_ratio)
        
        if type(efficient_gap_threshold) is bool or not isinstance(efficient_gap_threshold, (int, float)):
            raise TypeError("efficient_gap_threshold must be a float or int and not bool")
        self.efficient_gap_threshold = float(efficient_gap_threshold)
        
        if type(overreaction_multiplier) is bool or not isinstance(overreaction_multiplier, (int, float)):
            raise TypeError("overreaction_multiplier must be a float or int and not bool")
        self.overreaction_multiplier = float(overreaction_multiplier)
        
        self.non_reaction_threshold = 0.20

    def _classify(self, expected_change: float, actual_change: float, absolute_gap: float, coverage_ratio: float) -> str:
        if actual_change is None:
            return "INSUFFICIENT_DATA"
        if coverage_ratio < self.minimum_coverage_ratio:
            return "LOW_COVERAGE"
        if abs(expected_change) < self.minimum_pressure_threshold:
            return "LOW_PRESSURE"
        if absolute_gap < self.efficient_gap_threshold:
            return "EFFICIENT"
            
        # Check signs for divergence
        if (expected_change > 0 and actual_change < 0) or (expected_change < 0 and actual_change > 0):
            return "DIVERGENCE"
            
        if abs(actual_change) <= self.non_reaction_threshold:
            return "NON_REACTION"
            
        if abs(actual_change) < abs(expected_change):
            return "UNDERREACTION"
            
        return "OVERREACTION"

    def detect(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs detection on all configured Gold target instruments.
        """
        if not isinstance(changes, dict):
            raise TypeError("changes must be a dictionary")
            
        for k, v in changes.items():
            if isinstance(v, bool):
                raise TypeError(f"Change value for '{k}' cannot be a boolean")
            if not isinstance(v, (int, float)):
                raise TypeError(f"Change value for '{k}' must be a float or int, got {type(v).__name__}")
            if math.isnan(v) or math.isinf(v):
                raise ValueError(f"Change value for '{k}' must be finite")

        registry = GoldCommodityInstrumentRegistry()
        targets = [t["symbol"] for t in registry.targets()]
        
        result_targets = {}
        inefficiencies_found = 0
        insufficient_data_targets = 0

        for target in targets:
            calc_res = self.calculator.calculate(target, changes)
            
            expected_change = calc_res["expected_change"]
            coverage_ratio = calc_res["coverage_ratio"]
            raw_pressure_score = calc_res["raw_pressure_score"]
            observed_weight = calc_res["observed_weight"]
            total_possible_weight = calc_res["total_possible_weight"]
            contributors = calc_res["contributors"]
            missing_sources = calc_res["missing_sources"]
            
            actual_change = changes.get(target)
            
            residual_gap = None
            absolute_gap = None
            inefficiency_score = None
            recommended_direction = "NO_ACTION"
            
            if actual_change is not None:
                residual_gap = expected_change - actual_change
                absolute_gap = abs(residual_gap)
                inefficiency_score = absolute_gap * coverage_ratio

            status = self._classify(expected_change, actual_change, absolute_gap, coverage_ratio)
            
            is_inefficient = status in ("DIVERGENCE", "NON_REACTION", "UNDERREACTION", "OVERREACTION")
            
            if is_inefficient:
                inefficiencies_found += 1
                if residual_gap > 0:
                    recommended_direction = "LONG_TARGET"
                elif residual_gap < 0:
                    recommended_direction = "SHORT_TARGET"
                else:
                    recommended_direction = "NO_ACTION"
            else:
                recommended_direction = "NO_ACTION"

            if status == "INSUFFICIENT_DATA":
                insufficient_data_targets += 1

            # Dynamic explanation
            explanations = {
                "DIVERGENCE": "Gold moved in the opposite direction to the movement implied by its drivers.",
                "OVERREACTION": "Gold moved materially beyond the movement implied by its drivers.",
                "EFFICIENT": "Actual gold movement was sufficiently close to the expected movement.",
                "LOW_COVERAGE": "Too few registered drivers were available to evaluate the target reliably.",
                "LOW_PRESSURE": "Expected driver pressure was too small to classify as an inefficiency.",
                "INSUFFICIENT_DATA": "Actual target movement was not provided."
            }

            if status == "UNDERREACTION":
                if expected_change > 0:
                    explanation = "Expected positive movement was materially larger than the actual positive movement."
                else:
                    explanation = "Expected negative movement was materially larger in magnitude than the actual negative movement."
            elif status == "NON_REACTION":
                if expected_change > 0:
                    explanation = "Gold showed little or no upward reaction despite meaningful positive driver pressure."
                else:
                    explanation = "Gold showed little or no downward reaction despite meaningful negative driver pressure."
            else:
                explanation = explanations[status]

            def rnd(val: Optional[float]) -> Optional[float]:
                if val is None:
                    return None
                return round(float(val), 6)

            result_targets[target] = {
                "target": target,
                "status": status,
                "recommended_direction": recommended_direction,
                "is_inefficient": is_inefficient,
                "expected_change": rnd(expected_change),
                "actual_change": rnd(actual_change),
                "residual_gap": rnd(residual_gap),
                "absolute_gap": rnd(absolute_gap),
                "inefficiency_score": rnd(inefficiency_score),
                "coverage_ratio": rnd(coverage_ratio),
                "raw_pressure_score": rnd(raw_pressure_score),
                "observed_weight": rnd(observed_weight),
                "total_possible_weight": rnd(total_possible_weight),
                "contributors": contributors,
                "missing_sources": missing_sources,
                "expected_change_basis": "weighted_average_directional_driver_change_proxy",
                "is_historically_calibrated": False,
                "explanation": explanation
            }

        summary = {
            "targets_evaluated": len(targets),
            "inefficiencies_found": inefficiencies_found,
            "insufficient_data_targets": insufficient_data_targets
        }

        return {
            "targets": result_targets,
            "summary": summary
        }
