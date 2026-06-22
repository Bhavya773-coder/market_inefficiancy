import math
from ai.steel_pressure_calculator import SteelPressureCalculator
from ai.steel_signal_graph import SteelSignalGraph

class SteelInefficiencyDetector:
    def __init__(
        self,
        gap_threshold=0.75,
        min_expected_move=0.50,
        min_coverage_ratio=0.60,
        non_reaction_threshold=0.20
    ):
        self.gap_threshold = gap_threshold
        self.min_expected_move = min_expected_move
        self.min_coverage_ratio = min_coverage_ratio
        self.non_reaction_threshold = non_reaction_threshold
        
        self.calculator = SteelPressureCalculator()
        self.graph = SteelSignalGraph()

    def detect(self, market_changes):
        # Input Validation
        if not isinstance(market_changes, dict):
            raise TypeError("market_changes must be a dictionary")

        for k, v in market_changes.items():
            # Reject bool (bool is a subclass of int, so check it first)
            if isinstance(v, bool):
                raise TypeError(f"Value for key '{k}' cannot be a boolean")
            if not isinstance(v, (int, float)):
                raise TypeError(f"Value for key '{k}' must be an int or float, got {type(v).__name__}")
            if math.isnan(v) or math.isinf(v):
                raise ValueError(f"Value for key '{k}' must be finite and not NaN/Inf")

        # Calculate pressure
        pressure_res = self.calculator.calculate(market_changes)
        
        result_targets = {}
        inefficiencies_found = 0
        insufficient_data_targets = 0
        
        for target, target_data in pressure_res["targets"].items():
            # 1. Find all registered drivers
            drivers = self.graph.drivers_for(target)
            total_possible_weight = sum(abs(d["weight"]) for d in drivers)
            
            # 2. Calculate observed weight
            contributors = target_data["contributors"]
            observed_weight = sum(abs(c["weight"]) for c in contributors)
            
            # 3. Calculate coverage ratio
            coverage_ratio = observed_weight / total_possible_weight if total_possible_weight > 0 else 0.0
            
            # 4. Get raw pressure score
            raw_pressure_score = target_data["pressure_score"]
            
            # 5. Expected change
            expected_change = raw_pressure_score / observed_weight if observed_weight > 0 else 0.0
            
            # 6. Actual change
            actual_change = market_changes.get(target)
            
            # 7. Residual gap, absolute gap, inefficiency score, recommended direction
            residual_gap = None
            absolute_gap = None
            inefficiency_score = None
            recommended_direction = "NO_TRADE"
            status = None
            is_inefficient = False
            
            if actual_change is not None:
                residual_gap = expected_change - actual_change
                absolute_gap = abs(residual_gap)
                inefficiency_score = absolute_gap * coverage_ratio
                
                if residual_gap > 0:
                    recommended_direction = "LONG_TARGET"
                elif residual_gap < 0:
                    recommended_direction = "SHORT_TARGET"
                else:
                    recommended_direction = "NO_TRADE"
            
            # 8. Detection status rules in exact order
            if actual_change is None:
                status = "INSUFFICIENT_DATA"
                is_inefficient = False
                recommended_direction = "NO_TRADE"
                insufficient_data_targets += 1
            elif coverage_ratio < self.min_coverage_ratio:
                status = "LOW_COVERAGE"
                is_inefficient = False
                recommended_direction = "NO_TRADE"
            elif abs(expected_change) < self.min_expected_move:
                status = "LOW_PRESSURE"
                is_inefficient = False
                recommended_direction = "NO_TRADE"
            elif absolute_gap < self.gap_threshold:
                status = "EFFICIENT"
                is_inefficient = False
                recommended_direction = "NO_TRADE"
            elif (expected_change > 0 and actual_change < 0) or (expected_change < 0 and actual_change > 0):
                status = "DIVERGENCE"
                is_inefficient = True
            elif abs(actual_change) <= self.non_reaction_threshold:
                status = "NON_REACTION"
                is_inefficient = True
            elif abs(actual_change) < abs(expected_change):
                status = "UNDERREACTION"
                is_inefficient = True
            else:
                status = "OVERREACTION"
                is_inefficient = True
                
            if is_inefficient:
                inefficiencies_found += 1
                
            # Rounding
            def rnd(val):
                return round(float(val), 6) if val is not None else None
            
            # Format contributors copy with rounded values
            contributors_formatted = []
            for c in contributors:
                contributors_formatted.append({
                    "source": c["source"],
                    "change": rnd(c["change"]),
                    "weight": rnd(c["weight"]),
                    "contribution": rnd(c["contribution"])
                })
                
            explanations = {
                "UNDERREACTION": "Expected positive movement was materially larger than the actual positive movement.",
                "NON_REACTION": "Steel showed little or no reaction despite meaningful expected pressure.",
                "DIVERGENCE": "Steel moved in the opposite direction to the movement implied by its drivers.",
                "OVERREACTION": "Steel moved materially beyond the movement implied by its drivers.",
                "EFFICIENT": "Actual steel movement was sufficiently close to the expected movement.",
                "LOW_COVERAGE": "Too few registered drivers were available to evaluate the target reliably.",
                "LOW_PRESSURE": "Expected driver pressure was too small to classify as an inefficiency.",
                "INSUFFICIENT_DATA": "Actual target movement was not provided."
            }
            
            result_targets[target] = {
                "target": target,
                "raw_pressure_score": rnd(raw_pressure_score),
                "expected_change": rnd(expected_change),
                "actual_change": rnd(actual_change),
                "residual_gap": rnd(residual_gap),
                "absolute_gap": rnd(absolute_gap),
                "total_possible_weight": rnd(total_possible_weight),
                "observed_weight": rnd(observed_weight),
                "coverage_ratio": rnd(coverage_ratio),
                "inefficiency_score": rnd(inefficiency_score),
                "status": status,
                "is_inefficient": is_inefficient,
                "recommended_direction": recommended_direction,
                "contributors": contributors_formatted,
                "explanation": explanations[status]
            }
            
        summary = {
            "targets_evaluated": len(pressure_res["targets"]),
            "inefficiencies_found": inefficiencies_found,
            "insufficient_data_targets": insufficient_data_targets
        }
        
        return {
            "targets": result_targets,
            "summary": summary
        }
