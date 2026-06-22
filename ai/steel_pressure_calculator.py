from ai.steel_signal_graph import SteelSignalGraph

class SteelPressureCalculator:
    def __init__(self):
        self.graph = SteelSignalGraph()

    def calculate(self, market_changes):
        relationships = self.graph.all()
        
        # Determine all unique target instruments from the graph
        targets_data = {}
        for rel in relationships:
            target = rel["target"]
            if target not in targets_data:
                targets_data[target] = {
                    "pressure_score": 0.0,
                    "contributors": []
                }
        
        # Calculate contributions
        for rel in relationships:
            source = rel["source"]
            target = rel["target"]
            weight = rel["weight"]
            
            if source in market_changes:
                change = market_changes[source]
                contribution = change * weight
                
                targets_data[target]["pressure_score"] += contribution
                targets_data[target]["contributors"].append({
                    "source": source,
                    "change": change,
                    "weight": weight,
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
                "classification": classification,
                "contributors": sorted_contributors
            }
            
        return result
