import math
from ai.steel_signal_graph import SteelSignalGraph

class SteelPressureCalculator:
    def __init__(self):
        self.graph = SteelSignalGraph()

    def calculate(self, market_changes):
        # Input Validation
        if not isinstance(market_changes, dict):
            raise TypeError("market_changes must be a dictionary")

        for k, v in market_changes.items():
            if isinstance(v, bool):
                raise TypeError(f"Value for key '{k}' cannot be a boolean")
            if not isinstance(v, (int, float)):
                raise TypeError(f"Value for key '{k}' must be an int or float, got {type(v).__name__}")
            if math.isnan(v) or math.isinf(v):
                raise ValueError(f"Value for key '{k}' must be finite and not NaN/Inf")

        relationships = self.graph.all()
        
        # Determine all unique target instruments from the graph
        targets_data = {}
        for rel in relationships:
            target = rel["target"]
            if target not in targets_data:
                targets_data[target] = {
                    "pressure_score": 0.0,
                    "applied_weight": 0.0,
                    "skipped_mixed_weight": 0.0,
                    "skipped_sources": [],
                    "contributors": []
                }
        
        # Process relationships
        for rel in relationships:
            source = rel["source"]
            target = rel["target"]
            weight = rel["weight"]
            direction = rel.get("direction", "positive")
            
            if direction == "mixed":
                targets_data[target]["skipped_mixed_weight"] += weight
                if source not in targets_data[target]["skipped_sources"]:
                    targets_data[target]["skipped_sources"].append(source)
                continue
                
            direction_multiplier = 1.0 if direction == "positive" else -1.0
            
            if source in market_changes:
                change = market_changes[source]
                contribution = change * weight * direction_multiplier
                
                targets_data[target]["pressure_score"] += contribution
                targets_data[target]["applied_weight"] += weight
                targets_data[target]["contributors"].append({
                    "source": source,
                    "change": change,
                    "weight": weight,
                    "relationship_direction": direction,
                    "direction_multiplier": direction_multiplier,
                    "contribution": contribution
                })
        
        # Classify and sort contributors
        result = {"targets": {}}
        for target, data in targets_data.items():
            score = data["pressure_score"]
            
            # Classification logic
            if score >= 2.0:
                classification = "VERY_BULLISH"
            elif score >= 1.0:
                classification = "BULLISH"
            elif score <= -2.0:
                classification = "VERY_BEARISH"
            elif score <= -1.0:
                classification = "BEARISH"
            else:
                classification = "NEUTRAL"
            
            # Sort contributors descending by absolute contribution
            sorted_contributors = sorted(
                data["contributors"],
                key=lambda x: abs(x["contribution"]),
                reverse=True
            )
            
            result["targets"][target] = {
                "pressure_score": score,
                "applied_weight": data["applied_weight"],
                "skipped_mixed_weight": data["skipped_mixed_weight"],
                "skipped_sources": data["skipped_sources"],
                "classification": classification,
                "contributors": sorted_contributors
            }
            
        return result
