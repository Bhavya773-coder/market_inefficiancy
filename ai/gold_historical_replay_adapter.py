import math
from typing import Dict, Any, List, Optional
from ai.commodity_replay_config import CommodityReplayConfig
from ai.gold_inefficiency_detector import GoldInefficiencyDetector

class GoldHistoricalReplayAdapter:
    """
    Adapts point-in-time cached price store statistics into the format
    expected by GoldInefficiencyDetector.
    """
    def __init__(self, config: CommodityReplayConfig, detector: Optional[GoldInefficiencyDetector] = None):
        if not isinstance(config, CommodityReplayConfig):
            raise TypeError("config must be a CommodityReplayConfig instance")
        self.config = config
        self.detector = detector if detector is not None else GoldInefficiencyDetector(
            minimum_pressure_threshold=0.50,
            minimum_coverage_ratio=0.50,
            efficient_gap_threshold=config.convergence_gap_threshold,
            overreaction_multiplier=1.5
        )

    def build_changes(self, price_store, observed_at: Any) -> Dict[str, Any]:
        """
        Builds the percentage price changes map based only on historical prices.
        """
        changes = {}
        stale_instruments = []
        missing_instruments = []
        available_driver_count = 0

        # Drivers
        for inst in self.config.driver_instruments:
            lookback = self.config.lookback_seconds_by_instrument.get(inst)
            max_age = self.config.maximum_data_age_seconds_by_instrument.get(inst)

            age = price_store.age_seconds(inst, observed_at)
            if age is None:
                missing_instruments.append(inst)
                continue

            if max_age is not None and age > max_age:
                stale_instruments.append(inst)
                continue

            chg = price_store.percentage_change(inst, observed_at, lookback)
            if chg is None or not math.isfinite(chg):
                missing_instruments.append(inst)
                continue

            changes[inst] = chg
            available_driver_count += 1

        # Targets
        for inst in self.config.target_instruments:
            lookback = self.config.lookback_seconds_by_instrument.get(inst)
            max_age = self.config.maximum_data_age_seconds_by_instrument.get(inst)

            age = price_store.age_seconds(inst, observed_at)
            if age is None:
                missing_instruments.append(inst)
                continue

            if max_age is not None and age > max_age:
                stale_instruments.append(inst)
                continue

            chg = price_store.percentage_change(inst, observed_at, lookback)
            if chg is None or not math.isfinite(chg):
                missing_instruments.append(inst)
                continue

            changes[inst] = chg

        # Check readiness
        targets_available = all(t in changes for t in self.config.target_instruments)
        is_ready = targets_available and (available_driver_count >= self.config.minimum_required_driver_count)

        return {
            "changes": changes,
            "available_driver_count": available_driver_count,
            "missing_instruments": sorted(missing_instruments),
            "stale_instruments": sorted(stale_instruments),
            "observed_at": observed_at.isoformat(),
            "is_ready": is_ready
        }

    def detect(self, price_store, observed_at: Any) -> Dict[str, Any]:
        """
        Runs detection if the price store has enough warm-up history.
        """
        diag = self.build_changes(price_store, observed_at)
        if not diag["is_ready"]:
            res_targets = {}
            for target in self.config.target_instruments:
                res_targets[target] = {
                    "target": target,
                    "recommended_direction": "NO_ACTION",
                    "is_inefficient": False,
                    "status": "INSUFFICIENT_DATA",
                    "expected_change": 0.0,
                    "actual_change": None,
                    "residual_gap": None,
                    "absolute_gap": None,
                    "inefficiency_score": None,
                    "coverage_ratio": 0.0,
                    "contributors": []
                }
            return {
                "targets": res_targets,
                "summary": {
                    "targets_evaluated": len(self.config.target_instruments),
                    "inefficiencies_found": 0,
                    "insufficient_data_targets": len(self.config.target_instruments)
                }
            }

        return self.detector.detect(diag["changes"])
