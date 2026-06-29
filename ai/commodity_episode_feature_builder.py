import math
import copy
import statistics
from datetime import datetime
from typing import Dict, Any, List, Optional
from ai.commodity_feature_profile import CommodityFeatureProfile

class CommodityEpisodeFeatureBuilder:
    """
    Leakage-safe, commodity-expandable feature engineering engine.
    Transforms closed inefficiency episodes into model training rows.
    """
    def __init__(self, profile: CommodityFeatureProfile):
        if not isinstance(profile, CommodityFeatureProfile):
            raise TypeError("profile must be a CommodityFeatureProfile instance")
        self.profile = profile

    def _validate_number(self, val, name):
        if val is None:
            return
        if type(val) is bool:
            raise TypeError(f"{name} cannot be a boolean")
        if not isinstance(val, (int, float)):
            raise TypeError(f"{name} must be a float or int, got {type(val).__name__}")
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"{name} cannot be NaN or infinity")

    def _validate_iso_tz_string(self, val, name):
        if not isinstance(val, str):
            raise TypeError(f"{name} must be a string")
        try:
            dt = datetime.fromisoformat(val)
        except Exception as e:
            raise ValueError(f"Invalid ISO-8601 string for {name}: {e}")
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            raise ValueError(f"{name} must be timezone-aware")

    def build(self, episode: Dict[str, Any]) -> Dict[str, Any]:
        """
        Builds features and labels for a single closed episode.
        Does not mutate the input.
        """
        if not isinstance(episode, dict):
            raise TypeError("episode must be a dictionary")
        if episode.get("schema_version") != "1.0":
            raise ValueError(f"Unsupported episode schema_version: {episode.get('schema_version')}")
            
        expected_type = self.profile.episode_type
        if episode.get("episode_type") != expected_type:
            raise ValueError(f"Unsupported episode_type: {episode.get('episode_type')} (expected {expected_type})")
        
        episode_id = episode.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError("episode_id must be a non-empty string")
            
        if episode.get("is_open") is not False:
            raise ValueError("episode must be closed (is_open must be False)")
            
        outcome = episode.get("outcome")
        if outcome not in self.profile.outcome_codes:
            raise ValueError(f"Invalid outcome: {outcome}")
            
        obs_list = episode.get("observations")
        if not isinstance(obs_list, list) or not obs_list:
            raise ValueError("observations must be a non-empty list")
            
        first_obs = obs_list[0]
        if not isinstance(first_obs, dict):
            raise TypeError("First observation must be a dictionary")

        target = episode.get("target")
        if not isinstance(target, str) or not target or target not in self.profile.target_codes:
            raise ValueError(f"Invalid target: {target}")

        direction = episode.get("recommended_direction")
        if direction not in ("LONG_TARGET", "SHORT_TARGET"):
            raise ValueError(f"Invalid recommended_direction: {direction}")

        # Validate dates
        self._validate_iso_tz_string(episode.get("opened_at"), "opened_at")
        self._validate_iso_tz_string(episode.get("closed_at"), "closed_at")

        # Validate numeric episode fields
        self._validate_number(episode.get("opening_expected_change"), "opening_expected_change")
        self._validate_number(episode.get("opening_actual_change"), "opening_actual_change")
        self._validate_number(episode.get("opening_residual_gap"), "opening_residual_gap")
        self._validate_number(episode.get("opening_inefficiency_score"), "opening_inefficiency_score")
        self._validate_number(episode.get("opening_coverage_ratio"), "opening_coverage_ratio")
        self._validate_number(episode.get("max_favorable_excursion"), "max_favorable_excursion")
        self._validate_number(episode.get("max_adverse_excursion"), "max_adverse_excursion")
        self._validate_number(episode.get("duration_seconds"), "duration_seconds")
        self._validate_number(episode.get("convergence_time_seconds"), "convergence_time_seconds")
        self._validate_number(episode.get("update_count"), "update_count")
        self._validate_number(episode.get("uncertain_update_count"), "uncertain_update_count")

        # Validate numeric observation fields
        obs_numeric = [
            "expected_change", "actual_change", "residual_gap", "absolute_gap",
            "inefficiency_score", "coverage_ratio"
        ]
        for key in obs_numeric:
            if key not in first_obs:
                raise KeyError(f"First observation missing required key: {key}")
            self._validate_number(first_obs[key], f"observation.{key}")

        # Validate contributor fields
        contribs = first_obs.get("contributors")
        seen_contribs = set()
        if contribs is not None:
            if not isinstance(contribs, list):
                raise TypeError("contributors in first observation must be a list")
            for idx, c in enumerate(contribs):
                if not isinstance(c, dict):
                    raise TypeError(f"Contributor at index {idx} must be a dictionary")
                if "source" not in c:
                    raise KeyError(f"Contributor at index {idx} missing 'source' key")
                src = c["source"]
                if not isinstance(src, str) or not src or not src.isupper():
                    raise ValueError(f"Contributor source at index {idx} must be non-empty uppercase string")
                if src in seen_contribs:
                    raise ValueError(f"Duplicate contributor source found: {src}")
                seen_contribs.add(src)
                
                if "relationship_direction" not in c:
                    raise KeyError(f"Contributor at index {idx} missing 'relationship_direction' key")
                if c["relationship_direction"] not in ("positive", "negative"):
                    raise ValueError(f"Contributor relationship_direction at index {idx} must be positive/negative")
                
                for key in ["change", "weight", "direction_multiplier", "contribution"]:
                    if key not in c:
                        raise KeyError(f"Contributor at index {idx} missing numeric key: {key}")
                    self._validate_number(c[key], f"Contributor at index {idx}.{key}")

        # Copy to prevent mutation
        ep_copy = copy.deepcopy(episode)
        obs = ep_copy["observations"][0]

        # Metadata
        metadata = {
            "feature_schema_version": self.profile.feature_schema_version,
            "source_episode_schema_version": ep_copy["schema_version"],
            "episode_id": ep_copy["episode_id"],
            "commodity": self.profile.commodity,
            "commodity_code": self.profile.commodity_code,
            "target": ep_copy["target"],
            "recommended_direction": ep_copy["recommended_direction"],
            "opened_at": ep_copy["opened_at"],
            "closed_at": ep_copy["closed_at"]
        }

        # Features
        features = {
            "commodity_code": self.profile.commodity_code,
            "target_code": self.profile.target_codes[ep_copy["target"]],
            "direction_code": 1 if ep_copy["recommended_direction"] == "LONG_TARGET" else -1,
            "opening_status_code": self.profile.status_codes[obs["status"]],
            "opening_expected_change": ep_copy["opening_expected_change"],
            "opening_actual_change": ep_copy["opening_actual_change"],
            "opening_residual_gap": ep_copy["opening_residual_gap"],
            "opening_absolute_gap": obs["absolute_gap"],
            "opening_inefficiency_score": ep_copy["opening_inefficiency_score"],
            "opening_coverage_ratio": ep_copy["opening_coverage_ratio"],
            "opening_raw_pressure_score": obs.get("raw_pressure_score", 0.0),
            "opening_total_possible_weight": obs.get("total_possible_weight", 0.0),
            "opening_observed_weight": obs.get("observed_weight", 0.0),
            "opening_is_historically_calibrated": 1 if obs.get("is_historically_calibrated") is True else 0
        }

        # Observed weight ratio calculation
        tot_wt = features["opening_total_possible_weight"]
        obs_wt = features["opening_observed_weight"]
        features["opening_observed_weight_ratio"] = obs_wt / tot_wt if tot_wt > 0.0 else 0.0

        # Contributor aggregate calculations
        contrib_list = obs.get("contributors") or []
        features["contributor_count"] = len(contrib_list)
        features["positive_contributor_count"] = sum(1 for c in contrib_list if c["contribution"] > 0)
        features["negative_contributor_count"] = sum(1 for c in contrib_list if c["contribution"] < 0)
        
        contributions = [c["contribution"] for c in contrib_list]
        features["sum_contribution"] = sum(contributions)
        features["sum_absolute_contribution"] = sum(abs(x) for x in contributions)
        features["largest_absolute_contribution"] = max((abs(x) for x in contributions), default=0.0)
        features["mean_absolute_contribution"] = (
            features["sum_absolute_contribution"] / features["contributor_count"]
            if features["contributor_count"] > 0
            else 0.0
        )
        
        changes = [c["change"] for c in contrib_list]
        features["mean_driver_change"] = sum(changes) / len(changes) if len(changes) > 0 else 0.0
        
        if len(changes) < 2:
            features["driver_change_dispersion"] = 0.0
        else:
            features["driver_change_dispersion"] = statistics.pstdev(changes)

        sum_abs_cont = features["sum_absolute_contribution"]
        features["positive_contribution_share"] = (
            sum(c["contribution"] for c in contrib_list if c["contribution"] > 0) / sum_abs_cont
            if sum_abs_cont > 0.0
            else 0.0
        )
        features["negative_contribution_share"] = (
            sum(abs(c["contribution"]) for c in contrib_list if c["contribution"] < 0) / sum_abs_cont
            if sum_abs_cont > 0.0
            else 0.0
        )

        # Fixed driver columns
        contrib_map = {c["source"]: c for c in contrib_list}
        for src in self.profile.driver_sources:
            src_lower = src.lower()
            c = contrib_map.get(src)
            if c is not None:
                features[f"driver_{src_lower}_present"] = 1
                features[f"driver_{src_lower}_change"] = float(c["change"])
                features[f"driver_{src_lower}_weight"] = float(c["weight"])
                features[f"driver_{src_lower}_direction_multiplier"] = float(c["direction_multiplier"])
                features[f"driver_{src_lower}_contribution"] = float(c["contribution"])
            else:
                features[f"driver_{src_lower}_present"] = 0
                features[f"driver_{src_lower}_change"] = 0.0
                features[f"driver_{src_lower}_weight"] = 0.0
                features[f"driver_{src_lower}_direction_multiplier"] = 0.0
                features[f"driver_{src_lower}_contribution"] = 0.0

        # Labels
        labels = {
            "label_converged": 1 if outcome == "CONVERGED" else 0,
            "label_direction_reversed": 1 if outcome == "DIRECTION_REVERSED" else 0,
            "label_signal_decayed": 1 if outcome == "SIGNAL_DECAYED" else 0,
            "label_expired": 1 if outcome == "EXPIRED" else 0,
            "label_manually_closed": 1 if outcome == "MANUALLY_CLOSED" else 0,
            "label_outcome_code": self.profile.outcome_codes[outcome],
            "label_duration_seconds": float(ep_copy["duration_seconds"]),
            "label_convergence_time_seconds": (
                float(ep_copy["convergence_time_seconds"])
                if outcome == "CONVERGED" and ep_copy.get("convergence_time_seconds") is not None
                else None
            ),
            "label_max_favorable_excursion": float(ep_copy["max_favorable_excursion"]),
            "label_max_adverse_excursion": float(ep_copy["max_adverse_excursion"]),
            "label_update_count": int(ep_copy["update_count"]),
            "label_uncertain_update_count": int(ep_copy["uncertain_update_count"])
        }

        # Round floats
        def _round_dict(d):
            for k, v in d.items():
                if isinstance(v, float):
                    d[k] = round(v, 6)

        _round_dict(features)
        _round_dict(labels)

        built_example = {
            "metadata": metadata,
            "features": features,
            "labels": labels
        }
        
        # Self-audit leakage
        audit = self.audit_for_leakage(built_example)
        if not audit["passed"]:
            raise ValueError(f"Leakage check failed: {audit['violations']}")

        return built_example

    def audit_for_leakage(self, built_example: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates that features do not contain any target labels or future indicators.
        """
        violations = []
        features = built_example.get("features", {})
        
        banned_concepts = [
            "outcome", "closed", "duration", "convergence_time", "favorable",
            "adverse", "latest", "update_count", "uncertain", "final",
            "future", "realized", "profit", "loss"
        ]
        
        for k in features.keys():
            k_lower = k.lower()
            for concept in banned_concepts:
                if concept in k_lower:
                    violations.append(f"Feature key '{k}' contains banned leakage concept '{concept}'")

        # Check for mutable references
        # Ensure primitive copies in values
        for k, v in features.items():
            if isinstance(v, (list, dict, set)):
                violations.append(f"Feature key '{k}' contains mutable reference of type '{type(v).__name__}'")

        return {
            "passed": len(violations) == 0,
            "violations": violations
        }

    def feature_columns(self) -> List[str]:
        """
        Returns a sorted list of all feature names.
        """
        keys = [
            "commodity_code", "target_code", "direction_code", "opening_status_code",
            "opening_expected_change", "opening_actual_change", "opening_residual_gap", "opening_absolute_gap",
            "opening_inefficiency_score", "opening_coverage_ratio", "opening_raw_pressure_score",
            "opening_total_possible_weight", "opening_observed_weight", "opening_observed_weight_ratio",
            "opening_is_historically_calibrated", "contributor_count", "positive_contributor_count",
            "negative_contributor_count", "sum_contribution", "sum_absolute_contribution",
            "largest_absolute_contribution", "mean_absolute_contribution", "mean_driver_change",
            "driver_change_dispersion", "positive_contribution_share", "negative_contribution_share"
        ]
        for src in self.profile.driver_sources:
            src_lower = src.lower()
            keys.append(f"driver_{src_lower}_present")
            keys.append(f"driver_{src_lower}_change")
            keys.append(f"driver_{src_lower}_weight")
            keys.append(f"driver_{src_lower}_direction_multiplier")
            keys.append(f"driver_{src_lower}_contribution")
        return sorted(keys)

    def label_columns(self) -> List[str]:
        """
        Returns a sorted list of all label names.
        """
        keys = [
            "label_converged", "label_direction_reversed", "label_signal_decayed",
            "label_expired", "label_manually_closed", "label_outcome_code",
            "label_duration_seconds", "label_convergence_time_seconds",
            "label_max_favorable_excursion", "label_max_adverse_excursion",
            "label_update_count", "label_uncertain_update_count"
        ]
        return sorted(keys)

    def flatten(self, built_example: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flattens the built example dictionary into a single dictionary
        using flat prefixes meta_, feature_ and label_.
        """
        flat = {}
        for k, v in built_example["metadata"].items():
            flat[f"meta_{k}"] = v
        for k, v in built_example["features"].items():
            flat[f"feature_{k}"] = v
        for k, v in built_example["labels"].items():
            key = k if k.startswith("label_") else f"label_{k}"
            flat[key] = v
        return flat

    def build_many(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Builds features for multiple episodes, checking for uniqueness.
        """
        seen_ids = set()
        built = []
        for ep in episodes:
            if not isinstance(ep, dict):
                raise TypeError("Each episode must be a dictionary")
            ep_id = ep.get("episode_id")
            if not ep_id:
                raise ValueError("Episode missing episode_id")
            if ep_id in seen_ids:
                raise ValueError(f"Duplicate episode ID {ep_id} in build_many call")
            seen_ids.add(ep_id)
            built.append(self.build(ep))
        return built
