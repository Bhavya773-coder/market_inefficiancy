from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from ai.commodity_historical_record import CommodityHistoricalRecord

class PointInTimePriceStore:
    """
    Maintains point-in-time safe historical record observations by instrument.
    Enforces forward-only ingestion and prevents lookahead leakage.
    """
    def __init__(self, max_records_per_instrument: Optional[int] = None):
        self.max_records_per_instrument = max_records_per_instrument
        self._store: Dict[str, List[CommodityHistoricalRecord]] = {}
        self.last_global_timestamp: Optional[datetime] = None
        self.cursor_timestamp: Optional[datetime] = None

    def add(self, record: CommodityHistoricalRecord):
        """
        Ingests a record. Enforces timezone-aware chronology and uniqueness.
        """
        if not isinstance(record, CommodityHistoricalRecord):
            raise TypeError("record must be a CommodityHistoricalRecord instance")

        ts = record.timestamp
        inst = record.instrument

        # Check cursor
        if self.cursor_timestamp is not None and ts > self.cursor_timestamp:
            raise ValueError(f"Cannot accept future record at {ts} relative to cursor {self.cursor_timestamp}")

        # Check global chronology
        if self.last_global_timestamp is not None and ts < self.last_global_timestamp:
            raise ValueError(f"Ingestion chronology violation: timestamp {ts} is earlier than last global timestamp {self.last_global_timestamp}")

        # Initialize list
        if inst not in self._store:
            self._store[inst] = []

        # Check duplicate
        for r in self._store[inst]:
            if r.timestamp == ts:
                raise ValueError(f"Duplicate observation for {inst} at {ts}")

        # Chronological insertion (since we process in order, we can append, but let's check)
        self._store[inst].append(record)
        self._store[inst].sort(key=lambda x: x.timestamp)
        
        # Enforce max records per instrument
        if self.max_records_per_instrument is not None:
            if len(self._store[inst]) > self.max_records_per_instrument:
                self._store[inst] = self._store[inst][-self.max_records_per_instrument:]

        self.last_global_timestamp = ts

    def latest_at_or_before(self, instrument: str, timestamp: datetime) -> Optional[CommodityHistoricalRecord]:
        """
        Returns the latest record for an instrument at or before a timestamp.
        """
        records = self._store.get(instrument, [])
        for r in reversed(records):
            if r.timestamp <= timestamp:
                return r
        return None

    def previous_at_or_before(self, instrument: str, timestamp: datetime, lookback_seconds: float) -> Optional[CommodityHistoricalRecord]:
        """
        Returns the latest record whose timestamp is <= timestamp - lookback_seconds.
        """
        limit_ts = timestamp - timedelta(seconds=lookback_seconds)
        return self.latest_at_or_before(instrument, limit_ts)

    def percentage_change(self, instrument: str, timestamp: datetime, lookback_seconds: float) -> Optional[float]:
        """
        Calculates percentage price change over the lookback window.
        """
        curr = self.latest_at_or_before(instrument, timestamp)
        if curr is None:
            return None
        prev = self.previous_at_or_before(instrument, timestamp, lookback_seconds)
        if prev is None:
            return None
        return (curr.price - prev.price) / prev.price * 100.0

    def age_seconds(self, instrument: str, timestamp: datetime) -> Optional[float]:
        """
        Returns the age of the latest record relative to the reference timestamp.
        """
        curr = self.latest_at_or_before(instrument, timestamp)
        if curr is None:
            return None
        return (timestamp - curr.timestamp).total_seconds()

    def snapshot(self, timestamp: datetime) -> Dict[str, CommodityHistoricalRecord]:
        """
        Returns a mapping of all instrument names to their latest record at or before timestamp.
        """
        snap = {}
        for inst in self._store.keys():
            r = self.latest_at_or_before(inst, timestamp)
            if r is not None:
                snap[inst] = r
        return snap
