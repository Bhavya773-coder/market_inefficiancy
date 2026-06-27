import math
import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional

@dataclass(frozen=True)
class CommodityHistoricalRecord:
    """
    Immutable representation of a point-in-time commodity price observation.
    """
    timestamp: datetime
    instrument: str
    price: float
    volume: Optional[float]
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Timestamp validation
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime instance")
        if self.timestamp.tzinfo is None or self.timestamp.tzinfo.utcoffset(self.timestamp) is None:
            raise ValueError("timestamp must be timezone-aware")

        # Instrument validation
        if not isinstance(self.instrument, str) or not self.instrument.strip() or not self.instrument.isupper():
            raise ValueError("instrument must be a non-empty uppercase string")

        # Price validation
        if type(self.price) is bool:
            raise TypeError("price cannot be a boolean")
        if not isinstance(self.price, (int, float)):
            raise TypeError("price must be a float or int")
        if math.isnan(self.price) or math.isinf(self.price):
            raise ValueError("price must be finite")
        if self.price <= 0:
            raise ValueError("price must be positive")

        # Volume validation
        if self.volume is not None:
            if type(self.volume) is bool:
                raise TypeError("volume cannot be a boolean")
            if not isinstance(self.volume, (int, float)):
                raise TypeError("volume must be a float or int")
            if math.isnan(self.volume) or math.isinf(self.volume):
                raise ValueError("volume must be finite")
            if self.volume < 0:
                raise ValueError("volume must be non-negative")

        # Source validation
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")

        # Metadata validation & defensive copy
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dictionary")
        # Overwrite metadata defensively
        object.__setattr__(self, "metadata", copy.deepcopy(self.metadata))

    def to_dict(self) -> Dict[str, Any]:
        """
        Returns JSON-serializable dictionary representation of the record.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "instrument": self.instrument,
            "price": float(self.price),
            "volume": float(self.volume) if self.volume is not None else None,
            "source": self.source,
            "metadata": copy.deepcopy(self.metadata)
        }

    @classmethod
    def from_dict(cls, record: Dict[str, Any]) -> "CommodityHistoricalRecord":
        """
        Builds a record from a dictionary. Rejects naive timestamps.
        """
        if not isinstance(record, dict):
            raise TypeError("record must be a dictionary")
            
        ts_val = record.get("timestamp")
        if isinstance(ts_val, str):
            try:
                dt = datetime.fromisoformat(ts_val)
            except Exception as e:
                raise ValueError(f"Invalid timestamp ISO string: {e}")
        elif isinstance(ts_val, datetime):
            dt = ts_val
        else:
            raise TypeError("timestamp in dictionary must be ISO string or datetime instance")

        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            raise ValueError("timestamp must be timezone-aware")

        vol = record.get("volume")
        if vol is not None:
            vol = float(vol)

        return cls(
            timestamp=dt,
            instrument=record["instrument"],
            price=float(record["price"]),
            volume=vol,
            source=record["source"],
            metadata=record.get("metadata", {})
        )
