import math
import uuid
import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

def _validate_target_result(target_result: Dict[str, Any], observed_at: datetime):
    if not isinstance(target_result, dict):
        raise TypeError("target_result must be a dictionary")
    
    # Required keys
    required_keys = [
        "target", "recommended_direction", "is_inefficient", "status",
        "expected_change", "actual_change", "residual_gap", "absolute_gap",
        "inefficiency_score", "coverage_ratio"
    ]
    for key in required_keys:
        if key not in target_result:
            raise KeyError(f"Missing required key in target_result: {key}")
            
    # Check timezone-aware datetime
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.tzinfo.utcoffset(observed_at) is None:
        raise ValueError("observed_at must be a timezone-aware datetime")
        
    # Check numeric types and reject bool/nan/inf
    numeric_keys = ["expected_change", "actual_change", "residual_gap", "absolute_gap", "inefficiency_score", "coverage_ratio"]
    for key in numeric_keys:
        val = target_result[key]
        if val is not None:
            if isinstance(val, bool):
                raise TypeError(f"Value for key '{key}' cannot be a boolean")
            if not isinstance(val, (int, float)):
                raise TypeError(f"Value for key '{key}' must be a float or int, got {type(val).__name__}")
            if math.isnan(val) or math.isinf(val):
                raise ValueError(f"Value for key '{key}' cannot be NaN or infinity")

    # Validate contributors when present
    if "contributors" in target_result and target_result["contributors"] is not None:
        contribs = target_result["contributors"]
        if not isinstance(contribs, list):
            raise TypeError("contributors must be a list")
        for c in contribs:
            if not isinstance(c, dict):
                raise TypeError("Each contributor must be a dictionary")
            
            # Source validation
            if "source" not in c:
                raise KeyError("Contributor missing 'source' key")
            if not isinstance(c["source"], str) or not c["source"]:
                raise ValueError("Contributor 'source' must be a non-empty string")
                
            # Relationship direction validation
            if "relationship_direction" not in c:
                raise KeyError("Contributor missing 'relationship_direction' key")
            if c["relationship_direction"] not in ("positive", "negative", "mixed"):
                raise ValueError(f"Contributor 'relationship_direction' must be 'positive', 'negative' or 'mixed', got: {c.get('relationship_direction')}")

            # Numeric fields to validate
            contrib_numeric_keys = ["change", "weight", "direction_multiplier", "contribution"]
            for key in contrib_numeric_keys:
                if key not in c:
                    raise KeyError(f"Contributor missing numeric key: {key}")
                val = c[key]
                if isinstance(val, bool):
                    raise TypeError(f"Contributor value for key '{key}' cannot be a boolean")
                if not isinstance(val, (int, float)):
                    raise TypeError(f"Contributor value for key '{key}' must be a float or int, got {type(val).__name__}")
                if math.isnan(val) or math.isinf(val):
                    raise ValueError(f"Contributor value for key '{key}' cannot be NaN or infinity")

@dataclass
class GoldInefficiencyEpisode:
    episode_id: str
    target: str
    recommended_direction: str
    opened_at: datetime
    last_updated_at: datetime
    closed_at: Optional[datetime]
    opening_status: str
    latest_status: str
    opening_expected_change: float
    latest_expected_change: float
    opening_actual_change: Optional[float]
    latest_actual_change: Optional[float]
    opening_residual_gap: Optional[float]
    latest_residual_gap: Optional[float]
    opening_inefficiency_score: Optional[float]
    latest_inefficiency_score: Optional[float]
    opening_coverage_ratio: float
    latest_coverage_ratio: float
    update_count: int
    uncertain_update_count: int
    max_favorable_excursion: float
    max_adverse_excursion: float
    convergence_time_seconds: Optional[float]
    outcome: str
    is_open: bool
    observations: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_detection(cls, target_result: Dict[str, Any], observed_at: datetime, episode_id: Optional[str] = None) -> "GoldInefficiencyEpisode":
        _validate_target_result(target_result, observed_at)
        
        if not target_result.get("is_inefficient"):
            raise ValueError("target_result is not inefficient")
            
        direction = target_result.get("recommended_direction")
        if direction not in ("LONG_TARGET", "SHORT_TARGET"):
            raise ValueError(f"Invalid recommended_direction: {direction}")
            
        if episode_id is not None:
            if not isinstance(episode_id, str) or not episode_id.strip():
                raise ValueError("episode_id must be a non-empty string")
            ep_id = episode_id
        else:
            ep_id = str(uuid.uuid4())
        
        obs = {
            "observed_at": observed_at,
            "status": target_result["status"],
            "expected_change": target_result["expected_change"],
            "actual_change": target_result["actual_change"],
            "residual_gap": target_result["residual_gap"],
            "absolute_gap": target_result["absolute_gap"],
            "inefficiency_score": target_result["inefficiency_score"],
            "coverage_ratio": target_result["coverage_ratio"],
            "recommended_direction": target_result["recommended_direction"],
            "is_inefficient": target_result["is_inefficient"]
        }
        
        # Additional learning metadata
        additional_keys = [
            "raw_pressure_score",
            "expected_change_basis",
            "is_historically_calibrated",
            "total_possible_weight",
            "observed_weight",
            "explanation"
        ]
        for key in additional_keys:
            if key in target_result:
                obs[key] = copy.deepcopy(target_result[key])
                
        if "contributors" in target_result:
            obs["contributors"] = copy.deepcopy(target_result["contributors"])
        
        return cls(
            episode_id=ep_id,
            target=target_result["target"],
            recommended_direction=direction,
            opened_at=observed_at,
            last_updated_at=observed_at,
            closed_at=None,
            opening_status=target_result["status"],
            latest_status=target_result["status"],
            opening_expected_change=target_result["expected_change"],
            latest_expected_change=target_result["expected_change"],
            opening_actual_change=target_result["actual_change"],
            latest_actual_change=target_result["actual_change"],
            opening_residual_gap=target_result["residual_gap"],
            latest_residual_gap=target_result["residual_gap"],
            opening_inefficiency_score=target_result["inefficiency_score"],
            latest_inefficiency_score=target_result["inefficiency_score"],
            opening_coverage_ratio=target_result["coverage_ratio"],
            latest_coverage_ratio=target_result["coverage_ratio"],
            update_count=1,
            uncertain_update_count=0,
            max_favorable_excursion=0.0,
            max_adverse_excursion=0.0,
            convergence_time_seconds=None,
            outcome="OPEN",
            is_open=True,
            observations=[obs]
        )

    def update(self, target_result: Dict[str, Any], observed_at: datetime):
        if not self.is_open:
            raise ValueError("Cannot update a closed episode")
            
        _validate_target_result(target_result, observed_at)
        
        if observed_at < self.last_updated_at:
            raise ValueError("observed_at cannot be earlier than last_updated_at")
            
        self.last_updated_at = observed_at
        self.update_count += 1
        
        # Update latest fields
        self.latest_status = target_result["status"]
        self.latest_expected_change = target_result["expected_change"]
        self.latest_actual_change = target_result["actual_change"]
        self.latest_residual_gap = target_result["residual_gap"]
        self.latest_inefficiency_score = target_result["inefficiency_score"]
        self.latest_coverage_ratio = target_result["coverage_ratio"]
        
        # Calculate excursions
        if self.latest_actual_change is not None and self.opening_actual_change is not None:
            if self.recommended_direction == "LONG_TARGET":
                directional_excursion = self.latest_actual_change - self.opening_actual_change
            elif self.recommended_direction == "SHORT_TARGET":
                directional_excursion = self.opening_actual_change - self.latest_actual_change
            else:
                directional_excursion = 0.0
                
            fav = max(0.0, directional_excursion)
            adv = max(0.0, -directional_excursion)
            
            self.max_favorable_excursion = max(self.max_favorable_excursion, fav)
            self.max_adverse_excursion = max(self.max_adverse_excursion, adv)
            
        if target_result["status"] in ("INSUFFICIENT_DATA", "LOW_COVERAGE"):
            self.uncertain_update_count += 1
                
        # Append observation
        obs = {
            "observed_at": observed_at,
            "status": target_result["status"],
            "expected_change": target_result["expected_change"],
            "actual_change": target_result["actual_change"],
            "residual_gap": target_result["residual_gap"],
            "absolute_gap": target_result["absolute_gap"],
            "inefficiency_score": target_result["inefficiency_score"],
            "coverage_ratio": target_result["coverage_ratio"],
            "recommended_direction": target_result["recommended_direction"],
            "is_inefficient": target_result["is_inefficient"]
        }
        
        # Additional learning metadata
        additional_keys = [
            "raw_pressure_score",
            "expected_change_basis",
            "is_historically_calibrated",
            "total_possible_weight",
            "observed_weight",
            "explanation"
        ]
        for key in additional_keys:
            if key in target_result:
                obs[key] = copy.deepcopy(target_result[key])
                
        if "contributors" in target_result:
            obs["contributors"] = copy.deepcopy(target_result["contributors"])
            
        self.observations.append(obs)

    def close(self, outcome: str, closed_at: datetime):
        if not self.is_open:
            raise ValueError("Episode is already closed")
            
        if outcome not in ("CONVERGED", "DIRECTION_REVERSED", "SIGNAL_DECAYED", "EXPIRED", "MANUALLY_CLOSED"):
            raise ValueError(f"Invalid closing outcome: {outcome}")
            
        if not isinstance(closed_at, datetime) or closed_at.tzinfo is None or closed_at.tzinfo.utcoffset(closed_at) is None:
            raise ValueError("closed_at must be a timezone-aware datetime")
            
        if closed_at < self.opened_at or closed_at < self.last_updated_at:
            raise ValueError("closed_at cannot be earlier than opened_at or last_updated_at")
            
        self.closed_at = closed_at
        self.last_updated_at = closed_at
        self.outcome = outcome
        self.is_open = False
        
        if outcome == "CONVERGED":
            self.convergence_time_seconds = (closed_at - self.opened_at).total_seconds()

    @property
    def duration_seconds(self) -> float:
        if self.is_open:
            return (self.last_updated_at - self.opened_at).total_seconds()
        else:
            return (self.closed_at - self.opened_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        def clean_dt(dt: Optional[datetime]) -> Optional[str]:
            if dt is None:
                return None
            return dt.isoformat()
            
        def rnd_val(v: Any) -> Any:
            if v is None:
                return None
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return round(float(v), 6)
            return v
            
        serialized_obs = []
        for o in self.observations:
            obs_dict = {
                "observed_at": clean_dt(o["observed_at"]),
                "status": o["status"],
                "expected_change": rnd_val(o["expected_change"]),
                "actual_change": rnd_val(o["actual_change"]),
                "residual_gap": rnd_val(o["residual_gap"]),
                "absolute_gap": rnd_val(o["absolute_gap"]),
                "inefficiency_score": rnd_val(o["inefficiency_score"]),
                "coverage_ratio": rnd_val(o["coverage_ratio"]),
                "recommended_direction": o["recommended_direction"],
                "is_inefficient": o["is_inefficient"]
            }
            
            # Additional learning metadata fields
            if "raw_pressure_score" in o:
                obs_dict["raw_pressure_score"] = rnd_val(o["raw_pressure_score"])
            if "expected_change_basis" in o:
                obs_dict["expected_change_basis"] = o["expected_change_basis"]
            if "is_historically_calibrated" in o:
                obs_dict["is_historically_calibrated"] = o["is_historically_calibrated"]
            if "total_possible_weight" in o:
                obs_dict["total_possible_weight"] = rnd_val(o["total_possible_weight"])
            if "observed_weight" in o:
                obs_dict["observed_weight"] = rnd_val(o["observed_weight"])
            if "explanation" in o:
                obs_dict["explanation"] = o["explanation"]
                
            if "contributors" in o:
                if o["contributors"] is None:
                    obs_dict["contributors"] = None
                else:
                    serialized_contribs = []
                    for c in o["contributors"]:
                        serialized_contribs.append({
                            "source": c["source"],
                            "change": rnd_val(c["change"]),
                            "weight": rnd_val(c["weight"]),
                            "relationship_direction": c["relationship_direction"],
                            "direction_multiplier": rnd_val(c["direction_multiplier"]),
                            "contribution": rnd_val(c["contribution"])
                        })
                    obs_dict["contributors"] = serialized_contribs
            
            serialized_obs.append(obs_dict)
            
        return {
            "schema_version": "1.0",
            "episode_type": "gold_inefficiency_episode",
            "episode_id": self.episode_id,
            "target": self.target,
            "recommended_direction": self.recommended_direction,
            "opened_at": clean_dt(self.opened_at),
            "last_updated_at": clean_dt(self.last_updated_at),
            "closed_at": clean_dt(self.closed_at),
            "opening_status": self.opening_status,
            "latest_status": self.latest_status,
            "opening_expected_change": rnd_val(self.opening_expected_change),
            "latest_expected_change": rnd_val(self.latest_expected_change),
            "opening_actual_change": rnd_val(self.opening_actual_change),
            "latest_actual_change": rnd_val(self.latest_actual_change),
            "opening_residual_gap": rnd_val(self.opening_residual_gap),
            "latest_residual_gap": rnd_val(self.latest_residual_gap),
            "opening_inefficiency_score": rnd_val(self.opening_inefficiency_score),
            "latest_inefficiency_score": rnd_val(self.latest_inefficiency_score),
            "opening_coverage_ratio": rnd_val(self.opening_coverage_ratio),
            "latest_coverage_ratio": rnd_val(self.latest_coverage_ratio),
            "update_count": self.update_count,
            "uncertain_update_count": self.uncertain_update_count,
            "max_favorable_excursion": rnd_val(self.max_favorable_excursion),
            "max_adverse_excursion": rnd_val(self.max_adverse_excursion),
            "duration_seconds": rnd_val(self.duration_seconds),
            "convergence_time_seconds": rnd_val(self.convergence_time_seconds),
            "outcome": self.outcome,
            "is_open": self.is_open,
            "observations": serialized_obs
        }
