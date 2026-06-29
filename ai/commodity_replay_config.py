import math
from dataclasses import dataclass, field
from typing import Dict, Any, Tuple, Optional

@dataclass(frozen=True)
class CommodityReplayConfig:
    """
    Immutable replay configuration controlling parameters for historical backtests.
    """
    commodity: str
    target_instruments: Tuple[str, ...]
    driver_instruments: Tuple[str, ...]
    lookback_seconds_by_instrument: Dict[str, float]
    maximum_data_age_seconds_by_instrument: Dict[str, float]
    decision_instruments: Tuple[str, ...]
    minimum_required_driver_count: int
    episode_max_age_seconds: Optional[float] = None
    convergence_gap_threshold: float = 0.35
    output_episode_dataset_path: str = "storage/steel_replay_episodes.jsonl"
    output_feature_dataset_path: str = "storage/steel_replay_features.jsonl"
    replay_run_id: str = "default_run_id"
    strict_chronology: bool = True
    finalize_open_episodes: str = "LEAVE_OPEN"
    metadata: Dict[str, Any] = field(default_factory=lambda: {"is_historically_calibrated": False})

    def __post_init__(self):
        # Validate commodity
        if not isinstance(self.commodity, str) or not self.commodity.strip() or not self.commodity.isupper():
            raise ValueError("commodity must be a non-empty uppercase string")

        # Validate target_instruments
        if not isinstance(self.target_instruments, tuple) or not self.target_instruments:
            raise ValueError("target_instruments must be a non-empty tuple")
        for inst in self.target_instruments:
            if not isinstance(inst, str) or not inst.strip() or not inst.isupper():
                raise ValueError("target instrument name must be uppercase")

        # Validate driver_instruments
        if not isinstance(self.driver_instruments, tuple) or not self.driver_instruments:
            raise ValueError("driver_instruments must be a non-empty tuple")
        for inst in self.driver_instruments:
            if not isinstance(inst, str) or not inst.strip() or not inst.isupper():
                raise ValueError("driver instrument name must be uppercase")

        # Validate lookbacks
        if not isinstance(self.lookback_seconds_by_instrument, dict) or not self.lookback_seconds_by_instrument:
            raise ValueError("lookback_seconds_by_instrument must be a non-empty dict")
        for k, v in self.lookback_seconds_by_instrument.items():
            if type(v) is bool or not isinstance(v, (int, float)) or v <= 0:
                raise ValueError(f"lookback for {k} must be positive numeric")

        # Validate maximum ages
        if not isinstance(self.maximum_data_age_seconds_by_instrument, dict) or not self.maximum_data_age_seconds_by_instrument:
            raise ValueError("maximum_data_age_seconds_by_instrument must be a non-empty dict")
        for k, v in self.maximum_data_age_seconds_by_instrument.items():
            if type(v) is bool or not isinstance(v, (int, float)) or v <= 0:
                raise ValueError(f"maximum data age for {k} must be positive numeric")

        # Validate decision instruments
        if not isinstance(self.decision_instruments, tuple) or not self.decision_instruments:
            raise ValueError("decision_instruments must be a non-empty tuple")
        for inst in self.decision_instruments:
            if not isinstance(inst, str) or not inst.strip() or not inst.isupper():
                raise ValueError("decision instrument name must be uppercase")

        # Validate minimum required drivers
        if type(self.minimum_required_driver_count) is bool or not isinstance(self.minimum_required_driver_count, int) or self.minimum_required_driver_count < 0:
            raise TypeError("minimum_required_driver_count must be a non-negative integer and not bool")

        # Validate episode max age
        if self.episode_max_age_seconds is not None:
            if type(self.episode_max_age_seconds) is bool or not isinstance(self.episode_max_age_seconds, (int, float)) or self.episode_max_age_seconds <= 0:
                raise ValueError("episode_max_age_seconds must be positive numeric")

        # Validate convergence threshold
        if type(self.convergence_gap_threshold) is bool or not isinstance(self.convergence_gap_threshold, (int, float)) or self.convergence_gap_threshold < 0 or math.isnan(self.convergence_gap_threshold) or math.isinf(self.convergence_gap_threshold):
            raise ValueError("convergence_gap_threshold must be non-negative finite numeric")

        # Validate replay run ID
        if not isinstance(self.replay_run_id, str) or not self.replay_run_id.strip():
            raise ValueError("replay_run_id must be a non-empty string")

        # Validate finalization strategy
        if self.finalize_open_episodes not in ("LEAVE_OPEN", "EXPIRE_IF_OLD", "MANUALLY_CLOSE"):
            raise ValueError(f"Invalid finalize_open_episodes strategy: {self.finalize_open_episodes}")

# Predefined steel historical replay configuration
STEEL_HISTORICAL_REPLAY_CONFIG = CommodityReplayConfig(
    commodity="STEEL",
    target_instruments=("STEEL_FUTURE", "STEEL_PHYSICAL_PLATE"),
    driver_instruments=(
        "IRON_ORE", "COKING_COAL", "SCRAP_STEEL", "BALTIC_DRY",
        "CRUDE_OIL", "USDINR", "NIFTY_METAL", "TATASTEEL", "JSWSTEEL", "GOLD"
    ),
    lookback_seconds_by_instrument={
        "STEEL_FUTURE": 3600.0,
        "STEEL_PHYSICAL_PLATE": 86400.0,
        "IRON_ORE": 86400.0,
        "COKING_COAL": 86400.0,
        "SCRAP_STEEL": 86400.0,
        "BALTIC_DRY": 86400.0,
        "CRUDE_OIL": 86400.0,
        "USDINR": 86400.0,
        "NIFTY_METAL": 3600.0,
        "TATASTEEL": 3600.0,
        "JSWSTEEL": 3600.0,
        "GOLD": 86400.0
    },
    maximum_data_age_seconds_by_instrument={
        "STEEL_FUTURE": 172800.0,
        "STEEL_PHYSICAL_PLATE": 172800.0,
        "IRON_ORE": 172800.0,
        "COKING_COAL": 172800.0,
        "SCRAP_STEEL": 172800.0,
        "BALTIC_DRY": 172800.0,
        "CRUDE_OIL": 172800.0,
        "USDINR": 172800.0,
        "NIFTY_METAL": 172800.0,
        "TATASTEEL": 172800.0,
        "JSWSTEEL": 172800.0,
        "GOLD": 172800.0
    },
    decision_instruments=("STEEL_FUTURE", "STEEL_PHYSICAL_PLATE"),
    minimum_required_driver_count=5,
    episode_max_age_seconds=172800.0,
    convergence_gap_threshold=0.35,
    output_episode_dataset_path="storage/test_steel_replay_episodes.jsonl",
    output_feature_dataset_path="storage/test_steel_replay_features.jsonl",
    replay_run_id="steel-default-replay-id",
    strict_chronology=True,
    finalize_open_episodes="LEAVE_OPEN"
)

# Predefined gold historical replay configuration
GOLD_HISTORICAL_REPLAY_CONFIG = CommodityReplayConfig(
    commodity="GOLD",
    target_instruments=("GOLD_GLOBAL", "GOLD_INR", "GOLD_FUTURE"),
    driver_instruments=(
        "DXY", "USDINR", "US_REAL_YIELD", "US_NOMINAL_YIELD", "INFLATION_EXPECTATION",
        "SILVER", "CRUDE_OIL", "VIX", "SP500", "GOLD_ETF_FLOW",
        "CENTRAL_BANK_BUYING", "GLOBAL_LIQUIDITY"
    ),
    lookback_seconds_by_instrument={
        "GOLD_GLOBAL": 86400.0,
        "GOLD_INR": 86400.0,
        "GOLD_FUTURE": 3600.0,
        "DXY": 86400.0,
        "USDINR": 86400.0,
        "US_REAL_YIELD": 86400.0,
        "US_NOMINAL_YIELD": 86400.0,
        "INFLATION_EXPECTATION": 86400.0,
        "SILVER": 86400.0,
        "CRUDE_OIL": 86400.0,
        "VIX": 86400.0,
        "SP500": 86400.0,
        "GOLD_ETF_FLOW": 86400.0,
        "CENTRAL_BANK_BUYING": 86400.0,
        "GLOBAL_LIQUIDITY": 86400.0
    },
    maximum_data_age_seconds_by_instrument={
        "GOLD_GLOBAL": 172800.0,
        "GOLD_INR": 172800.0,
        "GOLD_FUTURE": 172800.0,
        "DXY": 172800.0,
        "USDINR": 172800.0,
        "US_REAL_YIELD": 172800.0,
        "US_NOMINAL_YIELD": 172800.0,
        "INFLATION_EXPECTATION": 172800.0,
        "SILVER": 172800.0,
        "CRUDE_OIL": 172800.0,
        "VIX": 172800.0,
        "SP500": 172800.0,
        "GOLD_ETF_FLOW": 172800.0,
        "CENTRAL_BANK_BUYING": 172800.0,
        "GLOBAL_LIQUIDITY": 172800.0
    },
    decision_instruments=("GOLD_GLOBAL", "GOLD_INR", "GOLD_FUTURE"),
    minimum_required_driver_count=5,
    episode_max_age_seconds=172800.0,
    convergence_gap_threshold=0.75,
    output_episode_dataset_path="storage/test_gold_replay_episodes.jsonl",
    output_feature_dataset_path="storage/test_gold_replay_features.jsonl",
    replay_run_id="gold-default-replay-id",
    strict_chronology=True,
    finalize_open_episodes="LEAVE_OPEN"
)

