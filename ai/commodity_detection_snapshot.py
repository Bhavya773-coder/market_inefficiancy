import math
import copy
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass(frozen=True)
class CommodityDetectionSnapshot:
    commodity: str
    target: str
    observed_at: datetime
    status: str
    recommended_direction: str
    expected_change: Optional[float]
    actual_change: Optional[float]
    residual_gap: Optional[float]
    absolute_gap: Optional[float]
    inefficiency_score: Optional[float]
    coverage_ratio: float
    raw_pressure_score: Optional[float]
    observed_weight: Optional[float]
    total_possible_weight: Optional[float]
    is_historically_calibrated: bool
    data_is_fresh: bool
    source_episode_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # String validations
        if not isinstance(self.commodity, str) or not self.commodity.strip() or not self.commodity.isupper():
            raise ValueError("commodity must be uppercase and non-empty")
        if not isinstance(self.target, str) or not self.target.strip() or not self.target.isupper():
            raise ValueError("target must be uppercase and non-empty")
        if not isinstance(self.status, str) or not self.status.strip():
            raise ValueError("status must be non-empty string")
            
        # Timestamp validation
        if not isinstance(self.observed_at, datetime) or self.observed_at.tzinfo is None or self.observed_at.tzinfo.utcoffset(self.observed_at) is None:
            raise ValueError("observed_at must be timezone-aware")
            
        # Direction validation
        if self.recommended_direction not in ("LONG_TARGET", "SHORT_TARGET", "NO_ACTION"):
            raise ValueError("recommended_direction must be LONG_TARGET, SHORT_TARGET, or NO_ACTION")
            
        # Numeric validations
        numeric_fields = {
            "expected_change": self.expected_change,
            "actual_change": self.actual_change,
            "residual_gap": self.residual_gap,
            "absolute_gap": self.absolute_gap,
            "inefficiency_score": self.inefficiency_score,
            "coverage_ratio": self.coverage_ratio,
            "raw_pressure_score": self.raw_pressure_score,
            "observed_weight": self.observed_weight,
            "total_possible_weight": self.total_possible_weight,
        }
        for name, val in numeric_fields.items():
            if val is not None:
                if isinstance(val, bool):
                    raise TypeError(f"{name} must not be a boolean")
                if not isinstance(val, (int, float)):
                    raise TypeError(f"{name} must be float or int")
                if not math.isfinite(val):
                    raise ValueError(f"{name} must be finite")
                    
        # coverage_ratio bounds
        if self.coverage_ratio < 0.0 or self.coverage_ratio > 1.0:
            raise ValueError("coverage_ratio must be between 0 and 1")
            
        # Boolean validations
        if type(self.is_historically_calibrated) is not bool:
            raise TypeError("is_historically_calibrated must be bool")
        if type(self.data_is_fresh) is not bool:
            raise TypeError("data_is_fresh must be bool")
            
        # source_episode_id validation
        if self.source_episode_id is not None:
            if not isinstance(self.source_episode_id, str) or not self.source_episode_id.strip():
                raise ValueError("source_episode_id must be non-empty string or None")
                
        # Defensive copy of metadata
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dictionary")
        object.__setattr__(self, "metadata", copy.deepcopy(self.metadata))

    @classmethod
    def from_detection(
        cls,
        commodity: str,
        detection: Dict[str, Any],
        observed_at: datetime,
        data_is_fresh: bool = True,
        source_episode_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> "CommodityDetectionSnapshot":
        if not isinstance(detection, dict):
            raise TypeError("detection must be a dictionary")
            
        target = detection.get("target")
        status = detection.get("status")
        recommended_direction = detection.get("recommended_direction")
        
        # Support both Gold (NO_ACTION) and Steel (NO_TRADE) default directions by standardizing
        if recommended_direction == "NO_TRADE":
            recommended_direction = "NO_ACTION"
            
        expected_change = detection.get("expected_change")
        actual_change = detection.get("actual_change")
        residual_gap = detection.get("residual_gap")
        absolute_gap = detection.get("absolute_gap")
        inefficiency_score = detection.get("inefficiency_score")
        coverage_ratio = detection.get("coverage_ratio", 0.0)
        raw_pressure_score = detection.get("raw_pressure_score")
        observed_weight = detection.get("observed_weight")
        total_possible_weight = detection.get("total_possible_weight")
        is_historically_calibrated = detection.get("is_historically_calibrated", False)
        
        meta = copy.deepcopy(metadata) if metadata is not None else {}
        
        return cls(
            commodity=commodity,
            target=target,
            observed_at=observed_at,
            status=status,
            recommended_direction=recommended_direction,
            expected_change=expected_change,
            actual_change=actual_change,
            residual_gap=residual_gap,
            absolute_gap=absolute_gap,
            inefficiency_score=inefficiency_score,
            coverage_ratio=coverage_ratio,
            raw_pressure_score=raw_pressure_score,
            observed_weight=observed_weight,
            total_possible_weight=total_possible_weight,
            is_historically_calibrated=is_historically_calibrated,
            data_is_fresh=data_is_fresh,
            source_episode_id=source_episode_id,
            metadata=meta
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commodity": self.commodity,
            "target": self.target,
            "observed_at": self.observed_at.isoformat(),
            "status": self.status,
            "recommended_direction": self.recommended_direction,
            "expected_change": self.expected_change,
            "actual_change": self.actual_change,
            "residual_gap": self.residual_gap,
            "absolute_gap": self.absolute_gap,
            "inefficiency_score": self.inefficiency_score,
            "coverage_ratio": self.coverage_ratio,
            "raw_pressure_score": self.raw_pressure_score,
            "observed_weight": self.observed_weight,
            "total_possible_weight": self.total_possible_weight,
            "is_historically_calibrated": self.is_historically_calibrated,
            "data_is_fresh": self.data_is_fresh,
            "source_episode_id": self.source_episode_id,
            "metadata": copy.deepcopy(self.metadata)
        }

    @property
    def is_actionable(self) -> bool:
        actionable_statuses = {"NON_REACTION", "UNDERREACTION", "OVERREACTION", "DIVERGENCE"}
        return (
            self.status in actionable_statuses
            and self.recommended_direction in ("LONG_TARGET", "SHORT_TARGET")
            and self.data_is_fresh
            and self.coverage_ratio >= 0.5
        )

    @property
    def is_bullish(self) -> bool:
        return self.is_actionable and self.recommended_direction == "LONG_TARGET"

    @property
    def is_bearish(self) -> bool:
        return self.is_actionable and self.recommended_direction == "SHORT_TARGET"

    @property
    def is_uncertain(self) -> bool:
        return self.status in {"INSUFFICIENT_DATA", "LOW_COVERAGE", "LOW_PRESSURE"}

    @property
    def is_neutral(self) -> bool:
        return self.status == "EFFICIENT"
