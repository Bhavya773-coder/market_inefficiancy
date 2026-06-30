import copy
from typing import Dict, Any
import ai.cross_metal_regime as rgm

class CrossMetalContextAdjuster:
    """
    Applies contextual rules based on cross-metal regimes to adjust or suppress 
    individual commodity inefficiency detections.
    """
    def adjust(self, commodity: str, detection: Dict[str, Any], regime_result: Dict[str, Any]) -> Dict[str, Any]:
        if commodity not in ("GOLD", "STEEL"):
            raise ValueError(f"Invalid commodity: {commodity}")
            
        if not isinstance(detection, dict):
            raise TypeError("detection must be a dictionary")
            
        if not isinstance(regime_result, dict):
            raise TypeError("regime_result must be a dictionary")

        # Defensive copy of the input detection to ensure it is not mutated
        orig_detection = copy.deepcopy(detection)

        # Standardize recommended direction
        base_action = orig_detection.get("recommended_direction")
        if base_action == "NO_TRADE":
            base_action = "NO_ACTION"
            
        if base_action not in ("LONG_TARGET", "SHORT_TARGET", "NO_ACTION"):
            raise ValueError(f"Invalid base action: {base_action}")

        # Extract regime details
        regime = regime_result.get("regime", rgm.MIXED_OR_UNCERTAIN)
        
        # Dynamically determine context based on the passed detection's recommended direction
        if regime == rgm.MIXED_OR_UNCERTAIN:
            context = "UNCERTAIN"
            support_score = 0.0
        else:
            if commodity == "GOLD":
                if base_action == "LONG_TARGET":
                    if regime in (rgm.BOTH_STRONG, rgm.GOLD_STRONG_STEEL_WEAK):
                        context = "SUPPORTIVE"
                        support_score = 1.0
                    else:
                        context = "CONTRADICTORY"
                        support_score = -1.0
                elif base_action == "SHORT_TARGET":
                    if regime in (rgm.BOTH_WEAK, rgm.STEEL_STRONG_GOLD_WEAK):
                        context = "SUPPORTIVE"
                        support_score = 1.0
                    else:
                        context = "CONTRADICTORY"
                        support_score = -1.0
                else:
                    context = "NEUTRAL"
                    support_score = 0.0
            else:
                # STEEL
                if base_action == "LONG_TARGET":
                    if regime in (rgm.BOTH_STRONG, rgm.STEEL_STRONG_GOLD_WEAK):
                        context = "SUPPORTIVE"
                        support_score = 1.0
                    else:
                        context = "CONTRADICTORY"
                        support_score = -1.0
                elif base_action == "SHORT_TARGET":
                    if regime in (rgm.BOTH_WEAK, rgm.GOLD_STRONG_STEEL_WEAK):
                        context = "SUPPORTIVE"
                        support_score = 1.0
                    else:
                        context = "CONTRADICTORY"
                        support_score = -1.0
                else:
                    context = "NEUTRAL"
                    support_score = 0.0

        # Determine adjusted action
        action_changed = False
        if base_action == "NO_ACTION":
            contextual_action = "NO_ACTION"
        else:
            # base_action is LONG_TARGET or SHORT_TARGET
            if context == "SUPPORTIVE":
                contextual_action = "KEEP_SIGNAL"
            elif context == "CONTRADICTORY":
                # Contradictory context can either REDUCE_PRIORITY or REJECT_CONTEXTUALLY
                # We use a threshold on inefficiency_score to decide between full rejection vs priority reduction
                ineff_score = orig_detection.get("inefficiency_score")
                if ineff_score is not None and ineff_score < 2.0:
                    contextual_action = "REJECT_CONTEXTUALLY"
                else:
                    contextual_action = "REDUCE_PRIORITY"
                action_changed = True
            elif context == "UNCERTAIN":
                contextual_action = "UNCERTAIN"
                action_changed = True
            else:
                # NEUTRAL context
                contextual_action = "KEEP_SIGNAL"

        # Build explanation
        target = orig_detection.get("target", "UNKNOWN")
        explanation = (
            f"Adjusted {commodity} target {target} signal. Base action was {base_action}, "
            f"contextual action is {contextual_action} based on regime {regime} (context: {context})."
        )

        return {
            "commodity": commodity,
            "original_detection": orig_detection,
            "cross_metal_regime": regime,
            "context": context,
            "support_score": float(support_score),
            "base_action": base_action,
            "contextual_action": contextual_action,
            "action_changed": action_changed,
            "is_historically_calibrated": False,
            "explanation": explanation
        }
