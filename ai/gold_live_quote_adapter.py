import math
from datetime import datetime
from typing import Dict, Any, List, Optional
from ai.commodity_replay_config import CommodityReplayConfig
from ai.gold_inefficiency_detector import GoldInefficiencyDetector
from ai.gold_historical_replay_adapter import GoldHistoricalReplayAdapter
from ai.point_in_time_price_store import PointInTimePriceStore
from ai.commodity_historical_record import CommodityHistoricalRecord

class GoldLiveQuoteAdapter:
    """
    Live quote adapter for Gold. Wraps GoldHistoricalReplayAdapter
    and updates an internal PointInTimePriceStore from LiveQuoteBuffer.
    """
    def __init__(self, config: CommodityReplayConfig, detector: Optional[GoldInefficiencyDetector] = None):
        self.config = config
        self.price_store = PointInTimePriceStore()
        self.underlying_adapter = GoldHistoricalReplayAdapter(config, detector)

    def update_prices(self, quote_buffer, observed_at: datetime, instrument_dhan_map: Dict[str, Any]):
        """
        Updates the internal price store using the latest quotes in quote_buffer.
        """
        for inst in list(self.config.driver_instruments) + list(self.config.target_instruments):
            dhan_cfg = instrument_dhan_map.get(inst)
            if dhan_cfg is None:
                continue
            quote = quote_buffer.latest(dhan_cfg["exchange"], dhan_cfg["security_id"])
            if quote is not None:
                ts = quote.get("provider_timestamp") or quote.get("received_at")
                if ts is None:
                    continue
                # Ensure timestamp is timezone-aware
                if ts.tzinfo is None:
                    continue
                latest_rec = self.price_store.latest_at_or_before(inst, observed_at)
                if latest_rec is None or ts > latest_rec.timestamp:
                    rec = CommodityHistoricalRecord(
                        timestamp=ts,
                        instrument=inst,
                        price=quote["last_price"],
                        volume=quote["volume"],
                        source="dhan_live"
                    )
                    self.price_store.add(rec)

    def detect(self, observed_at: datetime) -> Dict[str, Any]:
        """
        Runs the underlying detection using the populated price store.
        """
        return self.underlying_adapter.detect(self.price_store, observed_at)
