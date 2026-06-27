import math
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

class LiveQuoteBuffer:
    """
    Maintains the most recent quote and update statistics for every instrument,
    hardened against stale provider snapshots.
    """
    def __init__(
        self,
        max_quote_age_seconds=10.0,
        max_pair_gap_seconds=10.0,
        min_updates_for_active=2,
        activity_window_seconds=30.0,
        max_provider_age_seconds=10.0,
        min_provider_timestamp_advances_for_active=1
    ):
        self.max_quote_age_seconds = float(max_quote_age_seconds)
        self.max_pair_gap_seconds = float(max_pair_gap_seconds)
        self.min_updates_for_active = int(min_updates_for_active)
        self.activity_window_seconds = float(activity_window_seconds)
        self.max_provider_age_seconds = float(max_provider_age_seconds)
        self.min_provider_timestamp_advances_for_active = int(min_provider_timestamp_advances_for_active)
        
        self.quotes = {}  # key: "exchange:security_id" -> stored_quote dict
        self.stats = {}   # key: "exchange:security_id" -> stats dict

    def _normalize_timestamp(self, ts):
        """
        Parses provider timestamp to UTC timezone-aware datetime.
        """
        if not ts:
            return None
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                return ts.replace(tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
            return ts.astimezone(timezone.utc)
        if isinstance(ts, str):
            try:
                dt = datetime.strptime(ts.strip(), "%d/%m/%Y %H:%M:%S")
                return dt.replace(tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
            except Exception:
                return None
        return None

    def update_quote(self, quote, received_at=None, received_monotonic=None):
        """
        Updates the buffer with a new quote. Performs strict validation and updates statistics.
        """
        if not isinstance(quote, dict):
            raise TypeError("quote must be a dictionary")
            
        exchange = quote.get("exchange")
        if not isinstance(exchange, str) or not exchange.strip():
            raise ValueError("exchange must be a non-empty string")
            
        security_id = quote.get("security_id")
        if security_id is None:
            raise ValueError("security_id must exist")
        try:
            security_id = int(security_id)
        except (TypeError, ValueError):
            raise ValueError("security_id must be numeric")
            
        last_price = quote.get("last_price")
        if isinstance(last_price, bool):
            raise TypeError("last_price must not be a boolean")
        if not isinstance(last_price, (int, float)) or not math.isfinite(last_price):
            raise ValueError("last_price must be finite numeric")
            
        volume = quote.get("volume")
        if volume is not None:
            if isinstance(volume, bool):
                raise TypeError("volume must not be a boolean")
            if not isinstance(volume, (int, float)) or not math.isfinite(volume):
                raise ValueError("volume must be numeric or None")
                
        provider_ts_raw = quote.get("timestamp") or quote.get("last_trade_time") or quote.get("provider_timestamp")
        provider_ts = self._normalize_timestamp(provider_ts_raw)
        
        if received_at is None:
            received_at = datetime.now(timezone.utc)
        else:
            if not isinstance(received_at, datetime) or received_at.tzinfo is None:
                raise ValueError("received_at must be timezone-aware datetime")
                
        if received_monotonic is None:
            received_monotonic = time.perf_counter()
        else:
            if isinstance(received_monotonic, bool) or not isinstance(received_monotonic, (int, float)) or not math.isfinite(received_monotonic):
                raise ValueError("received_monotonic must be finite numeric")

        # Construct stored quote
        stored_quote = {
            "exchange": exchange,
            "security_id": security_id,
            "symbol": quote.get("symbol", ""),
            "last_price": float(last_price),
            "volume": int(volume) if volume is not None else None,
            "provider_timestamp": provider_ts,
            "raw_provider_timestamp": provider_ts_raw,
            "received_at": received_at,
            "received_monotonic": received_monotonic,
            "data_source": quote.get("data_source", ""),
            "raw_quote": quote,
            # Phase 5: timestamp key containing normalized provider timestamp
            "timestamp": provider_ts
        }

        key = f"{exchange}:{security_id}"
        
        if key not in self.stats:
            self.stats[key] = {
                "latest_quote": None,
                "previous_quote": None,
                "update_count": 0,
                "provider_timestamp_advance_count": 0,
                "duplicate_provider_snapshot_count": 0,
                "price_change_count": 0,
                "last_received_at": None,
                "first_received_at": received_at,
                "last_provider_timestamp": None,
                "last_provider_timestamp_advanced_at": None,
                "recent_updates": [],
                "recent_provider_ts": []
            }
            
        stats = self.stats[key]
        prev_quote = stats["latest_quote"]
        
        is_duplicate = False
        is_advanced = False
        
        if provider_ts is not None:
            if stats["last_provider_timestamp"] is not None:
                if provider_ts > stats["last_provider_timestamp"]:
                    is_advanced = True
                elif provider_ts == stats["last_provider_timestamp"]:
                    is_duplicate = True
            else:
                is_advanced = True

        stats["previous_quote"] = prev_quote
        stats["latest_quote"] = stored_quote
        stats["update_count"] += 1
        stats["last_received_at"] = received_at
        stats["recent_updates"].append(received_at)
        
        if is_advanced:
            stats["provider_timestamp_advance_count"] += 1
            stats["last_provider_timestamp"] = provider_ts
            stats["last_provider_timestamp_advanced_at"] = received_at
            stats["recent_provider_ts"].append(provider_ts)
        elif is_duplicate:
            stats["duplicate_provider_snapshot_count"] += 1
            
        if prev_quote is not None:
            if stored_quote["last_price"] != prev_quote["last_price"]:
                stats["price_change_count"] += 1
                
        self.quotes[key] = stored_quote

    def latest(self, exchange, security_id):
        """
        Returns the latest stored quote dict for the given exchange and security_id.
        """
        key = f"{exchange}:{security_id}"
        return self.quotes.get(key)

    def snapshot(self):
        """
        Returns a JSON-serializable snapshot of the current quotes and stats.
        """
        return {
            "quotes": {key: self._serialize_quote(q) for key, q in self.quotes.items()},
            "stats": {key: self._serialize_stats(s) for key, s in self.stats.items()}
        }

    def _serialize_quote(self, q):
        if q is None:
            return None
        return {
            "exchange": q["exchange"],
            "security_id": q["security_id"],
            "symbol": q["symbol"],
            "last_price": q["last_price"],
            "volume": q["volume"],
            "provider_timestamp": q["provider_timestamp"].isoformat() if q["provider_timestamp"] else None,
            "received_at": q["received_at"].isoformat() if q["received_at"] else None,
            "received_monotonic": q["received_monotonic"],
            "data_source": q["data_source"]
        }

    def _serialize_stats(self, s):
        if s is None:
            return None
        return {
            "update_count": s["update_count"],
            "provider_timestamp_advance_count": s["provider_timestamp_advance_count"],
            "duplicate_provider_snapshot_count": s["duplicate_provider_snapshot_count"],
            "price_change_count": s["price_change_count"],
            "last_received_at": s["last_received_at"].isoformat() if s["last_received_at"] else None,
            "first_received_at": s["first_received_at"].isoformat() if s["first_received_at"] else None,
            "latest_price": s["latest_quote"]["last_price"] if s["latest_quote"] else None
        }

    def instrument_status(self, exchange, security_id, now=None):
        """
        Evaluates and returns the status of an instrument.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        else:
            if isinstance(now, str):
                now = self._normalize_timestamp(now)
            elif isinstance(now, datetime):
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)

        key = f"{exchange}:{security_id}"
        if key not in self.quotes:
            return {
                "instrument_key": key,
                "has_quote": False,
                "update_count": 0,
                "provider_timestamp_advance_count": 0,
                "duplicate_provider_snapshot_count": 0,
                "price_change_count": 0,
                "last_price": None,
                "provider_timestamp": None,
                "received_at": None,
                "local_age_seconds": None,
                "provider_age_seconds": None,
                "is_locally_fresh": False,
                "is_provider_fresh": False,
                "provider_timestamp_advanced_recently": False,
                "is_active": False,
                "updates_in_activity_window": 0,
                "reason": "no_quote_received"
            }

        quote = self.quotes[key]
        stats = self.stats[key]
        
        local_age_seconds = (now - quote["received_at"]).total_seconds()
        is_locally_fresh = local_age_seconds <= self.max_quote_age_seconds
        
        provider_age_seconds = None
        is_provider_fresh = False
        provider_timestamp_advanced_recently = False
        
        provider_ts = quote["provider_timestamp"]
        if provider_ts is not None:
            provider_age_seconds = (now - provider_ts).total_seconds()
            is_provider_fresh = provider_age_seconds <= self.max_provider_age_seconds
            
        last_adv = stats["last_provider_timestamp_advanced_at"]
        if last_adv is not None:
            adv_age = (now - last_adv).total_seconds()
            provider_timestamp_advanced_recently = adv_age <= self.activity_window_seconds

        recent_updates_in_window = [
            t for t in stats["recent_updates"] 
            if (now - t).total_seconds() <= self.activity_window_seconds
        ]
        
        # Clean older updates in recent_updates list to prevent memory bloat
        stats["recent_updates"] = [
            t for t in stats["recent_updates"]
            if (now - t).total_seconds() <= 300.0
        ]
        
        updates_in_activity_window = len(recent_updates_in_window)
        has_min_updates = stats["update_count"] >= self.min_updates_for_active
        has_min_advances = stats["provider_timestamp_advance_count"] >= self.min_provider_timestamp_advances_for_active

        is_active = (
            has_min_updates and
            is_locally_fresh and
            (provider_ts is not None) and
            is_provider_fresh and
            has_min_advances and
            provider_timestamp_advanced_recently
        )
        
        reason = "active"
        if not has_min_updates:
            reason = "insufficient_total_updates"
        elif not is_locally_fresh:
            reason = "locally_stale"
        elif provider_ts is None:
            reason = "missing_or_unparseable_provider_timestamp"
        elif not is_provider_fresh:
            reason = "provider_stale"
        elif not has_min_advances:
            reason = "insufficient_provider_timestamp_advances"
        elif not provider_timestamp_advanced_recently:
            reason = "no_recent_provider_timestamp_advance"

        return {
            "instrument_key": key,
            "has_quote": True,
            "update_count": stats["update_count"],
            "provider_timestamp_advance_count": stats["provider_timestamp_advance_count"],
            "duplicate_provider_snapshot_count": stats["duplicate_provider_snapshot_count"],
            "price_change_count": stats["price_change_count"],
            "last_price": quote["last_price"],
            "provider_timestamp": quote["provider_timestamp"],
            "received_at": quote["received_at"],
            "local_age_seconds": local_age_seconds,
            "provider_age_seconds": provider_age_seconds,
            "is_locally_fresh": is_locally_fresh,
            "is_provider_fresh": is_provider_fresh,
            "provider_timestamp_advanced_recently": provider_timestamp_advanced_recently,
            "is_active": is_active,
            "updates_in_activity_window": updates_in_activity_window,
            "reason": reason
        }

    def pair_status(
        self,
        reference_exchange,
        reference_security_id,
        target_exchange,
        target_security_id,
        now=None
    ):
        """
        Evaluates whether a reference-target instrument pair is synchronized.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        else:
            if isinstance(now, str):
                now = self._normalize_timestamp(now)
            elif isinstance(now, datetime):
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)

        ref_status = self.instrument_status(reference_exchange, reference_security_id, now)
        tgt_status = self.instrument_status(target_exchange, target_security_id, now)
        
        both_active = ref_status["is_active"] and tgt_status["is_active"]
        
        blocking_reasons = []
        if not ref_status["is_active"]:
            blocking_reasons.append(f"reference_inactive: {ref_status['reason']}")
        if not tgt_status["is_active"]:
            blocking_reasons.append(f"target_inactive: {tgt_status['reason']}")
            
        local_receive_gap = None
        if ref_status["has_quote"] and tgt_status["has_quote"]:
            local_receive_gap = abs((ref_status["received_at"] - tgt_status["received_at"]).total_seconds())
            if local_receive_gap > self.max_pair_gap_seconds:
                blocking_reasons.append(
                    f"local_receive_gap_too_large: {local_receive_gap:.2f}s > {self.max_pair_gap_seconds}s"
                )
        else:
            blocking_reasons.append("missing_quotes_for_one_or_both_instruments")

        provider_ts_gap = None
        provider_timestamps_comparable = False
        
        if ref_status["has_quote"] and tgt_status["has_quote"]:
            ref_pts = ref_status["provider_timestamp"]
            tgt_pts = tgt_status["provider_timestamp"]
            
            if ref_pts is not None and tgt_pts is not None:
                provider_timestamps_comparable = True
                provider_ts_gap = abs((ref_pts - tgt_pts).total_seconds())
                if provider_ts_gap > self.max_pair_gap_seconds:
                    blocking_reasons.append(
                        f"provider_timestamp_gap_too_large: {provider_ts_gap:.2f}s > {self.max_pair_gap_seconds}s"
                    )
            else:
                blocking_reasons.append("missing_provider_timestamps")
        else:
            blocking_reasons.append("cannot_compare_provider_timestamps_due_to_missing_quotes")
            
        pair_is_synchronized = both_active and len(blocking_reasons) == 0
        
        reference_quote_sequence = ref_status["update_count"]
        target_quote_sequence = tgt_status["update_count"]
        snapshot_identity = f"{ref_status['provider_timestamp_advance_count']}:{tgt_status['provider_timestamp_advance_count']}"
        
        return {
            "reference": ref_status,
            "target": tgt_status,
            "both_active": both_active,
            "local_receive_gap_seconds": local_receive_gap,
            "provider_timestamp_gap_seconds": provider_ts_gap,
            "provider_timestamps_comparable": provider_timestamps_comparable,
            "pair_is_synchronized": pair_is_synchronized,
            "blocking_reasons": blocking_reasons,
            "reference_quote_sequence": reference_quote_sequence,
            "target_quote_sequence": target_quote_sequence,
            "snapshot_identity": snapshot_identity
        }
