import math
import copy
from typing import Dict, Any, List, Optional
from ai.gold_signal_graph import GoldSignalGraph
from ai.gold_commodity_instrument_registry import GoldCommodityInstrumentRegistry

class GoldPressureCalculator:
    """
    Calculates expected directional pressure score and expected change for a Gold target instrument
    based on a dictionary of driver percentage changes.
    """
    def __init__(self, signal_graph: Optional[GoldSignalGraph] = None, minimum_coverage_ratio: float = 0.5):
        self.graph = signal_graph if signal_graph is not None else GoldSignalGraph()
        if type(minimum_coverage_ratio) is bool or not isinstance(minimum_coverage_ratio, (int, float)):
            raise TypeError("minimum_coverage_ratio must be a float or int and not bool")
        self.minimum_coverage_ratio = float(minimum_coverage_ratio)

    def calculate(self, target: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates pressure score metrics for the target based on changes.
        """
        registry = GoldCommodityInstrumentRegistry()
        if not registry.contains(target):
            raise ValueError(f"Target '{target}' is not registered in the Gold registry")
            
        target_definition = registry.get(target)
        if target_definition["role"] != "TARGET":
            raise ValueError(f"Instrument '{target}' is registered but is not a target role")

        if not isinstance(changes, dict):
            raise TypeError("changes must be a dictionary")

        # Validate changes dictionary
        for k, v in changes.items():
            if isinstance(v, bool):
                raise TypeError(f"Change value for '{k}' cannot be a boolean")
            if not isinstance(v, (int, float)):
                raise TypeError(f"Change value for '{k}' must be a float or int, got {type(v).__name__}")
            if math.isnan(v) or math.isinf(v):
                raise ValueError(f"Change value for '{k}' must be finite")

        relationships = self.graph.relationships_for_target(target)
        
        total_possible_weight = 0.0
        observed_weight = 0.0
        raw_pressure_score = 0.0
        
        contributors = []
        missing_sources = []
        
        for rel in relationships:
            source = rel["source"]
            weight = rel["weight"]
            direction = rel["direction"]
            is_regime = rel.get("is_regime_dependent", False)
            
            # Sum up absolute possible weights
            total_possible_weight += abs(weight)
            
            if source in changes:
                change = changes[source]
                direction_multiplier = 1.0 if direction == "positive" else -1.0 if direction == "negative" else 0.0
                contribution = change * weight * direction_multiplier
                
                observed_weight += abs(weight)
                raw_pressure_score += contribution
                
                contributors.append({
                    "source": source,
                    "change": change,
                    "weight": weight,
                    "relationship_direction": direction,
                    "direction_multiplier": direction_multiplier,
                    "contribution": contribution,
                    "is_regime_dependent": is_regime
                })
            else:
                missing_sources.append(source)

        # Expected change
        expected_change = raw_pressure_score / observed_weight if observed_weight > 0.0 else 0.0
        
        # Coverage ratio
        coverage_ratio = observed_weight / total_possible_weight if total_possible_weight > 0.0 else 0.0
        coverage_ratio_rounded = round(coverage_ratio, 6)
        is_sufficient_coverage = coverage_ratio_rounded >= self.minimum_coverage_ratio

        # Sort contributors descending by absolute contribution
        contributors_sorted = sorted(
            contributors,
            key=lambda x: abs(x["contribution"]),
            reverse=True
        )

        missing_sources.sort()

        def rnd(val: Optional[float]) -> Optional[float]:
            if val is None:
                return None
            return round(float(val), 6)

        # Round values in contributors
        rounded_contributors = []
        for c in contributors_sorted:
            rounded_contributors.append({
                "source": c["source"],
                "change": rnd(c["change"]),
                "weight": rnd(c["weight"]),
                "relationship_direction": c["relationship_direction"],
                "direction_multiplier": rnd(c["direction_multiplier"]),
                "contribution": rnd(c["contribution"]),
                "is_regime_dependent": c["is_regime_dependent"]
            })

        return {
            "target": target,
            "raw_pressure_score": rnd(raw_pressure_score),
            "expected_change": rnd(expected_change),
            "observed_weight": rnd(observed_weight),
            "total_possible_weight": rnd(total_possible_weight),
            "coverage_ratio": rnd(coverage_ratio),
            "contributors": rounded_contributors,
            "missing_sources": missing_sources,
            "is_sufficient_coverage": is_sufficient_coverage,
            "expected_change_basis": "weighted_average_directional_driver_change_proxy",
            "is_historically_calibrated": False
        }
