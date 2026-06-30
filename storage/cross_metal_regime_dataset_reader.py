import json
import pathlib
from datetime import datetime
from typing import Dict, Any, List, Optional

class CrossMetalRegimeDatasetReader:
    """
    Reader and summary aggregator for Cross-Metal Regime JSONL datasets.
    """
    def __init__(self, dataset_path: str):
        self.dataset_path = pathlib.Path(dataset_path)

    def read_all(self, strict: bool = True) -> List[Dict[str, Any]]:
        records = []
        seen_ids = set()
        
        if not self.dataset_path.exists():
            return records
            
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except Exception as e:
                    if strict:
                        raise ValueError(f"Malformed JSON on line {line_num}: {e}")
                    continue
                    
                # Validate schema fields
                required_keys = ["record_type", "schema_version", "written_at", "snapshot_id", "regime", "record"]
                missing_key = False
                for k in required_keys:
                    if k not in record:
                        missing_key = True
                        break
                        
                if missing_key:
                    if strict:
                        raise ValueError(f"Record on line {line_num} is missing required fields")
                    continue
                    
                if record["record_type"] != "cross_metal_regime_snapshot":
                    if strict:
                        raise ValueError(f"Record on line {line_num} has invalid record_type: {record['record_type']}")
                    continue
                    
                if record["schema_version"] != "1.0":
                    if strict:
                        raise ValueError(f"Record on line {line_num} has invalid schema_version: {record['schema_version']}")
                    continue
                    
                # Timezone aware written_at validation
                written_at_str = record["written_at"]
                try:
                    dt = datetime.fromisoformat(written_at_str.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        raise ValueError("Naive datetime")
                except Exception as e:
                    if strict:
                        raise ValueError(f"Record on line {line_num} written_at must be timezone-aware ISO string: {e}")
                    continue
                    
                snapshot_id = record["snapshot_id"]
                if not isinstance(snapshot_id, str) or not snapshot_id.strip():
                    if strict:
                        raise ValueError(f"Record on line {line_num} snapshot_id must be non-empty string")
                    continue
                    
                if snapshot_id in seen_ids:
                    if strict:
                        raise ValueError(f"Duplicate snapshot ID detected on line {line_num}: {snapshot_id}")
                    continue
                seen_ids.add(snapshot_id)
                
                # Validate inner record payload
                inner = record["record"]
                if not isinstance(inner, dict):
                    if strict:
                        raise ValueError(f"Record on line {line_num} inner record must be a dict")
                    continue
                    
                # Check for Gold and Steel states
                if "gold_state" not in inner or "steel_state" not in inner:
                    if strict:
                        raise ValueError(f"Record on line {line_num} is missing gold_state or steel_state")
                    continue
                    
                if inner.get("is_historically_calibrated") is not False:
                    if strict:
                        raise ValueError(f"Record on line {line_num} is_historically_calibrated must be False")
                    continue
                    
                records.append(record)
                
        return records

    def records(self, strict: bool = True) -> List[Dict[str, Any]]:
        return [r["record"] for r in self.read_all(strict=strict)]

    def summary(self, strict: bool = True) -> Dict[str, Any]:
        rows = self.read_all(strict=strict)
        record_count = len(rows)
        
        regime_counts = {
            "GOLD_STRONG_STEEL_WEAK": 0,
            "STEEL_STRONG_GOLD_WEAK": 0,
            "BOTH_STRONG": 0,
            "BOTH_WEAK": 0,
            "MIXED_OR_UNCERTAIN": 0
        }
        
        synchronized_count = 0
        unsynchronized_count = 0
        actionable_context_count = 0
        uncertain_context_count = 0
        
        gold_supportive_count = 0
        gold_contradictory_count = 0
        steel_supportive_count = 0
        steel_contradictory_count = 0
        
        total_timestamp_gap = 0.0
        gap_count = 0
        
        seen_ids = set()
        unique_snapshot_count = 0
        duplicate_snapshot_count = 0
        
        for r in rows:
            sid = r["snapshot_id"]
            if sid in seen_ids:
                duplicate_snapshot_count += 1
            else:
                seen_ids.add(sid)
                unique_snapshot_count += 1
                
            inner = r["record"]
            regime = inner.get("regime")
            if regime in regime_counts:
                regime_counts[regime] += 1
            else:
                regime_counts["MIXED_OR_UNCERTAIN"] += 1
                
            if inner.get("is_synchronized", False):
                synchronized_count += 1
            else:
                unsynchronized_count += 1
                
            if inner.get("is_actionable_context", False):
                actionable_context_count += 1
            else:
                uncertain_context_count += 1
                
            gold_context = inner.get("gold_context")
            if gold_context == "SUPPORTIVE":
                gold_supportive_count += 1
            elif gold_context == "CONTRADICTORY":
                gold_contradictory_count += 1
                
            steel_context = inner.get("steel_context")
            if steel_context == "SUPPORTIVE":
                steel_supportive_count += 1
            elif steel_context == "CONTRADICTORY":
                steel_contradictory_count += 1
                
            gap = inner.get("timestamp_gap_seconds")
            if gap is not None:
                total_timestamp_gap += float(gap)
                gap_count += 1
                
        average_timestamp_gap = total_timestamp_gap / gap_count if gap_count > 0 else None
        if average_timestamp_gap is not None:
            average_timestamp_gap = round(average_timestamp_gap, 6)
            
        return {
            "record_count": record_count,
            "unique_snapshot_count": unique_snapshot_count,
            "duplicate_snapshot_count": duplicate_snapshot_count,
            "regime_counts": regime_counts,
            "synchronized_count": synchronized_count,
            "unsynchronized_count": unsynchronized_count,
            "actionable_context_count": actionable_context_count,
            "uncertain_context_count": uncertain_context_count,
            "gold_supportive_count": gold_supportive_count,
            "gold_contradictory_count": gold_contradictory_count,
            "steel_supportive_count": steel_supportive_count,
            "steel_contradictory_count": steel_contradictory_count,
            "average_timestamp_gap_seconds": average_timestamp_gap
        }
