from datetime import datetime
from typing import Dict, Any, List, Optional
from ai.gold_inefficiency_episode import GoldInefficiencyEpisode

class GoldInefficiencyEpisodeTracker:
    """
    Tracks lifecycles of gold inefficiency episodes.
    """
    def __init__(
        self,
        convergence_gap_threshold: float = 0.75,
        max_episode_age_seconds: Optional[float] = None,
        episode_id_factory: Optional[Any] = None
    ):
        self.convergence_gap_threshold = convergence_gap_threshold
        self.max_episode_age_seconds = max_episode_age_seconds
        self.episode_id_factory = episode_id_factory
        
        self._active_by_target: Dict[str, GoldInefficiencyEpisode] = {}
        self._closed_episodes: List[GoldInefficiencyEpisode] = []
        self.last_updated_at: Optional[datetime] = None

    def active_for(self, target: str) -> Optional[GoldInefficiencyEpisode]:
        return self._active_by_target.get(target)

    def active_episodes(self) -> List[GoldInefficiencyEpisode]:
        return list(self._active_by_target.values())

    def closed_episodes(self) -> List[GoldInefficiencyEpisode]:
        return self._closed_episodes

    def all_episodes(self) -> List[GoldInefficiencyEpisode]:
        return list(self._active_by_target.values()) + self._closed_episodes

    def manually_close(self, target: str, closed_at: datetime):
        active_ep = self._active_by_target.get(target)
        if active_ep is None:
            raise ValueError(f"No active episode to manually close for target: {target}")
            
        if not isinstance(closed_at, datetime) or closed_at.tzinfo is None or closed_at.tzinfo.utcoffset(closed_at) is None:
            raise ValueError("closed_at must be a timezone-aware datetime")
            
        if self.last_updated_at is not None and closed_at < self.last_updated_at:
            raise ValueError("closed_at cannot be earlier than tracker's last_updated_at")
            
        active_ep.close("MANUALLY_CLOSED", closed_at)
        self._active_by_target.pop(target)
        self._closed_episodes.append(active_ep)
        self.last_updated_at = closed_at

    def snapshot(self) -> Dict[str, Any]:
        return {
            "active": [ep.to_dict() for ep in self.active_episodes()],
            "closed": [ep.to_dict() for ep in self.closed_episodes()],
            "summary": {
                "active_count": len(self.active_episodes()),
                "closed_count": len(self.closed_episodes()),
                "total_count": len(self.all_episodes()),
                "converged_count": len([ep for ep in self.closed_episodes() if ep.outcome == "CONVERGED"]),
                "reversed_count": len([ep for ep in self.closed_episodes() if ep.outcome == "DIRECTION_REVERSED"]),
                "decayed_count": len([ep for ep in self.closed_episodes() if ep.outcome == "SIGNAL_DECAYED"]),
                "expired_count": len([ep for ep in self.closed_episodes() if ep.outcome == "EXPIRED"])
            }
        }

    def process(self, detection_result: Dict[str, Any], observed_at: datetime) -> Dict[str, Any]:
        if not isinstance(detection_result, dict):
            raise TypeError("detection_result must be a dictionary")
        if "targets" not in detection_result or not isinstance(detection_result["targets"], dict):
            raise KeyError("detection_result must contain a 'targets' dictionary")
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.tzinfo.utcoffset(observed_at) is None:
            raise ValueError("observed_at must be a timezone-aware datetime")
            
        if self.last_updated_at is not None and observed_at < self.last_updated_at:
            raise ValueError("observed_at cannot be earlier than tracker's last_updated_at")

        opened_this_step = []
        updated_this_step = []
        closed_this_step = []

        # Process each target
        for target, target_result in detection_result["targets"].items():
            active_ep = self._active_by_target.get(target)

            if active_ep is None:
                # Rule A: No active episode
                if target_result.get("is_inefficient") and target_result.get("recommended_direction") in ("LONG_TARGET", "SHORT_TARGET"):
                    ep_id = None
                    if self.episode_id_factory is not None:
                        ep_id = self.episode_id_factory(
                            target,
                            target_result.get("recommended_direction"),
                            observed_at
                        )
                    new_ep = GoldInefficiencyEpisode.from_detection(target_result, observed_at, episode_id=ep_id)
                    self._active_by_target[target] = new_ep
                    opened_this_step.append(new_ep)
            else:
                # Rule B: Existing active episode
                if observed_at < active_ep.last_updated_at:
                    raise ValueError(f"observed_at {observed_at} is earlier than last_updated_at of active episode")

                # Update the active episode first
                active_ep.update(target_result, observed_at)
                updated_this_step.append(active_ep)

                # Evaluate closure rules
                # 1. Expiry
                if self.max_episode_age_seconds is not None and active_ep.duration_seconds >= self.max_episode_age_seconds:
                    active_ep.close("EXPIRED", observed_at)
                    self._active_by_target.pop(target)
                    self._closed_episodes.append(active_ep)
                    closed_this_step.append(active_ep)
                    continue

                # 2. Uncertain data
                if target_result.get("status") in ("INSUFFICIENT_DATA", "LOW_COVERAGE"):
                    continue

                # 3. Convergence
                abs_gap = target_result.get("absolute_gap")
                is_converged = (target_result.get("status") == "EFFICIENT") or (abs_gap is not None and abs_gap <= self.convergence_gap_threshold)
                if is_converged:
                    active_ep.close("CONVERGED", observed_at)
                    self._active_by_target.pop(target)
                    self._closed_episodes.append(active_ep)
                    closed_this_step.append(active_ep)
                    continue

                # 4. Signal decay
                if target_result.get("status") == "LOW_PRESSURE":
                    active_ep.close("SIGNAL_DECAYED", observed_at)
                    self._active_by_target.pop(target)
                    self._closed_episodes.append(active_ep)
                    closed_this_step.append(active_ep)
                    continue

                # 5. Direction reversal
                is_ineff = target_result.get("is_inefficient")
                rec_dir = target_result.get("recommended_direction")
                if is_ineff and rec_dir in ("LONG_TARGET", "SHORT_TARGET") and rec_dir != active_ep.recommended_direction:
                    # Close current
                    active_ep.close("DIRECTION_REVERSED", observed_at)
                    self._active_by_target.pop(target)
                    self._closed_episodes.append(active_ep)
                    closed_this_step.append(active_ep)

                    # Open new immediately
                    ep_id = None
                    if self.episode_id_factory is not None:
                        ep_id = self.episode_id_factory(
                            target,
                            target_result.get("recommended_direction"),
                            observed_at
                        )
                    new_ep = GoldInefficiencyEpisode.from_detection(target_result, observed_at, episode_id=ep_id)
                    self._active_by_target[target] = new_ep
                    opened_this_step.append(new_ep)
                    continue

        self.last_updated_at = observed_at

        return {
            "opened": [ep.to_dict() for ep in opened_this_step],
            "updated": [ep.to_dict() for ep in updated_this_step],
            "closed": [ep.to_dict() for ep in closed_this_step],
            "active_count": len(self._active_by_target),
            "closed_count": len(self._closed_episodes)
        }
