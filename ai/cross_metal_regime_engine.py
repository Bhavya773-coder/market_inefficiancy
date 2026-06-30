import math
from typing import Dict, Any, List
from ai.commodity_detection_snapshot import CommodityDetectionSnapshot
from ai.cross_metal_snapshot import CrossMetalSnapshot
import ai.cross_metal_regime as rgm

class CrossMetalRegimeEngine:
    """
    Deterministic engine that classifies combined monetary-industrial environments 
    from Gold and Steel detector snapshots.
    """
    def __init__(
        self,
        synchronization_limit_seconds: float = 300.0,
        minimum_coverage_ratio: float = 0.5,
        minimum_inefficiency_score: float = 0.0
    ):
        if isinstance(synchronization_limit_seconds, bool) or not isinstance(synchronization_limit_seconds, (int, float)):
            raise TypeError("synchronization_limit_seconds must be float or int")
        if synchronization_limit_seconds <= 0:
            raise ValueError("synchronization_limit_seconds must be positive")
            
        if isinstance(minimum_coverage_ratio, bool) or not isinstance(minimum_coverage_ratio, (int, float)):
            raise TypeError("minimum_coverage_ratio must be float or int")
        if minimum_coverage_ratio < 0.0 or minimum_coverage_ratio > 1.0:
            raise ValueError("minimum_coverage_ratio must be between 0 and 1")
            
        if isinstance(minimum_inefficiency_score, bool) or not isinstance(minimum_inefficiency_score, (int, float)):
            raise TypeError("minimum_inefficiency_score must be float or int")
        if minimum_inefficiency_score < 0.0:
            raise ValueError("minimum_inefficiency_score must be non-negative")

        self.synchronization_limit_seconds = float(synchronization_limit_seconds)
        self.minimum_coverage_ratio = float(minimum_coverage_ratio)
        self.minimum_inefficiency_score = float(minimum_inefficiency_score)

    def classify(self, gold_snapshot: CommodityDetectionSnapshot, steel_snapshot: CommodityDetectionSnapshot) -> Dict[str, Any]:
        if not isinstance(gold_snapshot, CommodityDetectionSnapshot):
            raise TypeError("gold_snapshot must be a CommodityDetectionSnapshot")
        if gold_snapshot.commodity != "GOLD":
            raise ValueError(f"gold_snapshot commodity must be 'GOLD', got {gold_snapshot.commodity}")
            
        if not isinstance(steel_snapshot, CommodityDetectionSnapshot):
            raise TypeError("steel_snapshot must be a CommodityDetectionSnapshot")
        if steel_snapshot.commodity != "STEEL":
            raise ValueError(f"steel_snapshot commodity must be 'STEEL', got {steel_snapshot.commodity}")

        # Create paired CrossMetalSnapshot
        cross_snap = CrossMetalSnapshot.from_snapshots(
            gold_snapshot,
            steel_snapshot,
            synchronization_limit_seconds=self.synchronization_limit_seconds
        )

        uncertainty_reasons = []
        if not cross_snap.is_synchronized:
            uncertainty_reasons.append("UNSYNCHRONIZED_TIMESTAMPS")
        if not gold_snapshot.data_is_fresh:
            uncertainty_reasons.append("GOLD_DATA_STALE")
        if not steel_snapshot.data_is_fresh:
            uncertainty_reasons.append("STEEL_DATA_STALE")
            
        # Check coverage ratio bounds relative to engine minimums
        if gold_snapshot.coverage_ratio < self.minimum_coverage_ratio:
            uncertainty_reasons.append("GOLD_LOW_COVERAGE")
        if steel_snapshot.coverage_ratio < self.minimum_coverage_ratio:
            uncertainty_reasons.append("STEEL_LOW_COVERAGE")
            
        # Check inefficiency scores if available
        if gold_snapshot.inefficiency_score is not None and gold_snapshot.inefficiency_score < self.minimum_inefficiency_score:
            uncertainty_reasons.append("GOLD_LOW_INEFFICIENCY_SCORE")
        if steel_snapshot.inefficiency_score is not None and steel_snapshot.inefficiency_score < self.minimum_inefficiency_score:
            uncertainty_reasons.append("STEEL_LOW_INEFFICIENCY_SCORE")

        # Check standard uncertain and neutral statuses
        if gold_snapshot.is_uncertain:
            uncertainty_reasons.append(f"GOLD_DETECTION_STATUS_{gold_snapshot.status}")
        if steel_snapshot.is_uncertain:
            uncertainty_reasons.append(f"STEEL_DETECTION_STATUS_{steel_snapshot.status}")
            
        if gold_snapshot.is_neutral:
            uncertainty_reasons.append("GOLD_DETECTION_NEUTRAL")
        if steel_snapshot.is_neutral:
            uncertainty_reasons.append("STEEL_DETECTION_NEUTRAL")

        # Determine regime
        is_mixed_or_uncertain = (
            len(uncertainty_reasons) > 0 
            or not gold_snapshot.is_actionable 
            or not steel_snapshot.is_actionable
        )

        if is_mixed_or_uncertain:
            regime = rgm.MIXED_OR_UNCERTAIN
            gold_context = "UNCERTAIN"
            steel_context = "UNCERTAIN"
            gold_support_score = 0.0
            steel_support_score = 0.0
        else:
            # Both are actionable and synchronized
            gold_bullish = gold_snapshot.is_bullish
            steel_bullish = steel_snapshot.is_bullish
            gold_bearish = gold_snapshot.is_bearish
            steel_bearish = steel_snapshot.is_bearish

            if gold_bullish and steel_bearish:
                regime = rgm.GOLD_STRONG_STEEL_WEAK
            elif steel_bullish and gold_bearish:
                regime = rgm.STEEL_STRONG_GOLD_WEAK
            elif gold_bullish and steel_bullish:
                regime = rgm.BOTH_STRONG
            elif gold_bearish and steel_bearish:
                regime = rgm.BOTH_WEAK
            else:
                regime = rgm.MIXED_OR_UNCERTAIN

            # Re-evaluate mixed regime check
            if regime == rgm.MIXED_OR_UNCERTAIN:
                gold_context = "UNCERTAIN"
                steel_context = "UNCERTAIN"
                gold_support_score = 0.0
                steel_support_score = 0.0
            else:
                # Establish supportive/contradictory contexts
                # For Gold
                if gold_bullish:
                    if regime in (rgm.BOTH_STRONG, rgm.GOLD_STRONG_STEEL_WEAK):
                        gold_context = "SUPPORTIVE"
                        gold_support_score = 1.0
                    else:
                        gold_context = "CONTRADICTORY"
                        gold_support_score = -1.0
                elif gold_bearish:
                    if regime in (rgm.BOTH_WEAK, rgm.STEEL_STRONG_GOLD_WEAK):
                        gold_context = "SUPPORTIVE"
                        gold_support_score = 1.0
                    else:
                        gold_context = "CONTRADICTORY"
                        gold_support_score = -1.0
                else:
                    gold_context = "NEUTRAL"
                    gold_support_score = 0.0

                # For Steel
                if steel_bullish:
                    if regime in (rgm.BOTH_STRONG, rgm.STEEL_STRONG_GOLD_WEAK):
                        steel_context = "SUPPORTIVE"
                        steel_support_score = 1.0
                    else:
                        steel_context = "CONTRADICTORY"
                        steel_support_score = -1.0
                elif steel_bearish:
                    if regime in (rgm.BOTH_WEAK, rgm.GOLD_STRONG_STEEL_WEAK):
                        steel_context = "SUPPORTIVE"
                        steel_support_score = 1.0
                    else:
                        steel_context = "CONTRADICTORY"
                        steel_support_score = -1.0
                else:
                    steel_context = "NEUTRAL"
                    steel_support_score = 0.0

        # Construct explanation
        if regime == rgm.MIXED_OR_UNCERTAIN:
            if not uncertainty_reasons:
                uncertainty_reasons.append("NON_ACTIONABLE_COMPONENTS")
            explanation = f"Cross-metal regime is MIXED_OR_UNCERTAIN due to: {', '.join(uncertainty_reasons)}"
        else:
            explanation = (
                f"Cross-metal regime is {regime}. Gold ({gold_snapshot.target}) is {gold_snapshot.recommended_direction} "
                f"and Steel ({steel_snapshot.target}) is {steel_snapshot.recommended_direction}."
            )

        return {
            "regime_schema_version": "1.0",
            "snapshot_id": cross_snap.snapshot_id,
            "observed_at": cross_snap.observed_at.isoformat(),
            "regime": regime,
            "gold_state": gold_snapshot.to_dict(),
            "steel_state": steel_snapshot.to_dict(),
            "is_synchronized": cross_snap.is_synchronized,
            "timestamp_gap_seconds": cross_snap.timestamp_gap_seconds,
            "gold_context": gold_context,
            "steel_context": steel_context,
            "gold_support_score": gold_support_score,
            "steel_support_score": steel_support_score,
            "uncertainty_reasons": sorted(list(set(uncertainty_reasons))),
            "is_actionable_context": regime != rgm.MIXED_OR_UNCERTAIN,
            "is_historically_calibrated": False,
            "classification_basis": "deterministic_independent_gold_steel_state_proxy",
            "explanation": explanation
        }

    def classify_many(self, pairs: List[Any]) -> List[Dict[str, Any]]:
        if not isinstance(pairs, list):
            raise TypeError("pairs must be a list")
            
        results = []
        seen_ids = set()
        
        for idx, pair in enumerate(pairs):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise TypeError(f"Pair at index {idx} must be a list or tuple of length 2")
            gold, steel = pair
            res = self.classify(gold, steel)
            sid = res["snapshot_id"]
            if sid in seen_ids:
                raise ValueError(f"Duplicate snapshot ID detected: {sid}")
            seen_ids.add(sid)
            results.append(res)
            
        return results
