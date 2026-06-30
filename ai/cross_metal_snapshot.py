import hashlib
import copy
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from ai.commodity_detection_snapshot import CommodityDetectionSnapshot

@dataclass(frozen=True)
class CrossMetalSnapshot:
    observed_at: datetime
    gold: CommodityDetectionSnapshot
    steel: CommodityDetectionSnapshot
    timestamp_gap_seconds: float
    synchronization_limit_seconds: float
    is_synchronized: bool
    snapshot_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Validation checks
        if not isinstance(self.gold, CommodityDetectionSnapshot):
            raise TypeError("gold must be a CommodityDetectionSnapshot")
        if self.gold.commodity != "GOLD":
            raise ValueError(f"gold commodity must be 'GOLD', got {self.gold.commodity}")
            
        if not isinstance(self.steel, CommodityDetectionSnapshot):
            raise TypeError("steel must be a CommodityDetectionSnapshot")
        if self.steel.commodity != "STEEL":
            raise ValueError(f"steel commodity must be 'STEEL', got {self.steel.commodity}")
            
        if not isinstance(self.observed_at, datetime) or self.observed_at.tzinfo is None or self.observed_at.tzinfo.utcoffset(self.observed_at) is None:
            raise ValueError("observed_at must be timezone-aware")
            
        if isinstance(self.synchronization_limit_seconds, bool) or not isinstance(self.synchronization_limit_seconds, (int, float)):
            raise TypeError("synchronization_limit_seconds must be a float or int")
        if self.synchronization_limit_seconds <= 0:
            raise ValueError("synchronization_limit_seconds must be positive")
            
        if isinstance(self.timestamp_gap_seconds, bool) or not isinstance(self.timestamp_gap_seconds, (int, float)):
            raise TypeError("timestamp_gap_seconds must be a float or int")
        if self.timestamp_gap_seconds < 0:
            raise ValueError("timestamp_gap_seconds must be non-negative")
            
        if type(self.is_synchronized) is not bool:
            raise TypeError("is_synchronized must be bool")
            
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
            
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dictionary")
        object.__setattr__(self, "metadata", copy.deepcopy(self.metadata))

    @classmethod
    def from_snapshots(
        cls,
        gold: CommodityDetectionSnapshot,
        steel: CommodityDetectionSnapshot,
        synchronization_limit_seconds: float = 300.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> "CrossMetalSnapshot":
        if not isinstance(gold, CommodityDetectionSnapshot):
            raise TypeError("gold must be a CommodityDetectionSnapshot")
        if not isinstance(steel, CommodityDetectionSnapshot):
            raise TypeError("steel must be a CommodityDetectionSnapshot")
            
        if isinstance(synchronization_limit_seconds, bool) or not isinstance(synchronization_limit_seconds, (int, float)):
            raise TypeError("synchronization_limit_seconds must be a float or int")
        if synchronization_limit_seconds <= 0:
            raise ValueError("synchronization_limit_seconds must be positive")
            
        # observed_at is the later timestamp
        observed_at = max(gold.observed_at, steel.observed_at)
        
        # timestamp_gap_seconds is absolute difference in seconds
        timestamp_gap_seconds = abs((gold.observed_at - steel.observed_at).total_seconds())
        
        # synchronized only when gap <= limit
        is_synchronized = timestamp_gap_seconds <= synchronization_limit_seconds
        
        # Generate deterministic snapshot ID via SHA-256
        payload = (
            f"GOLD:{gold.target}:{gold.observed_at.isoformat()}:{gold.status}:{gold.recommended_direction}|"
            f"STEEL:{steel.target}:{steel.observed_at.isoformat()}:{steel.status}:{steel.recommended_direction}"
        )
        snapshot_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        
        meta = copy.deepcopy(metadata) if metadata is not None else {}
        
        return cls(
            observed_at=observed_at,
            gold=gold,
            steel=steel,
            timestamp_gap_seconds=timestamp_gap_seconds,
            synchronization_limit_seconds=float(synchronization_limit_seconds),
            is_synchronized=is_synchronized,
            snapshot_id=snapshot_id,
            metadata=meta
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "gold": self.gold.to_dict(),
            "steel": self.steel.to_dict(),
            "timestamp_gap_seconds": self.timestamp_gap_seconds,
            "synchronization_limit_seconds": self.synchronization_limit_seconds,
            "is_synchronized": self.is_synchronized,
            "snapshot_id": self.snapshot_id,
            "metadata": copy.deepcopy(self.metadata)
        }
