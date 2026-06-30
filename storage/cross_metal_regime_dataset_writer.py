import os
import json
import pathlib
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Set

class CrossMetalRegimeDatasetWriter:
    """
    Thread-safe, append-only JSONL dataset writer for Cross-Metal Regime snapshots.
    """
    def __init__(self, dataset_path: str = "storage/cross_metal_regime_snapshots.jsonl"):
        self.dataset_path = pathlib.Path(dataset_path)
        self._lock = threading.Lock()
        self._snapshot_ids: Set[str] = set()
        self._physical_record_count = 0
        
        # Ensure parent directory exists
        self.dataset_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Scan existing dataset to populate snapshot ID cache
        self._scan_existing_dataset()

    def _scan_existing_dataset(self):
        self._physical_record_count = 0
        snapshot_id_first_seen_at = {}  # maps snapshot_id -> first_seen_line_number
        
        if self.dataset_path.exists():
            with open(self.dataset_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        record = json.loads(stripped)
                    except Exception as e:
                        raise ValueError(f"Malformed JSON on line {line_num} in dataset: {e}")
                    
                    if not isinstance(record, dict):
                        raise ValueError(f"Record on line {line_num} must be a dictionary")
                    if record.get("record_type") != "cross_metal_regime_snapshot":
                        raise ValueError(f"Record on line {line_num} has incorrect record_type: {record.get('record_type')}")
                    if record.get("schema_version") != "1.0":
                        raise ValueError(f"Record on line {line_num} has incorrect schema_version: {record.get('schema_version')}")
                    if not isinstance(record.get("written_at"), str):
                        raise ValueError(f"Record on line {line_num} written_at must be a string")
                        
                    snapshot_id = record.get("snapshot_id")
                    if not isinstance(snapshot_id, str) or not snapshot_id:
                        raise ValueError(f"Record on line {line_num} snapshot_id must be a non-empty string")
                        
                    regime = record.get("regime")
                    if not isinstance(regime, str) or not regime:
                        raise ValueError(f"Record on line {line_num} regime must be a non-empty string")
                        
                    rec_payload = record.get("record")
                    if not isinstance(rec_payload, dict):
                        raise ValueError(f"Record on line {line_num} record must be a dictionary")
                    if rec_payload.get("is_historically_calibrated") is not False:
                        raise ValueError(f"Record on line {line_num} is_historically_calibrated must be False")
                        
                    if snapshot_id in snapshot_id_first_seen_at:
                        first_line = snapshot_id_first_seen_at[snapshot_id]
                        raise ValueError(
                            f"Duplicate snapshot ID {snapshot_id} found on line {line_num}. "
                            f"It was first seen on line {first_line}."
                        )
                        
                    snapshot_id_first_seen_at[snapshot_id] = line_num
                    self._snapshot_ids.add(snapshot_id)
                    self._physical_record_count += 1

    def write(self, regime_result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(regime_result, dict):
            raise TypeError("regime_result must be a dictionary")
            
        required_keys = ["snapshot_id", "regime", "observed_at", "is_historically_calibrated", "gold_state", "steel_state"]
        for k in required_keys:
            if k not in regime_result:
                raise KeyError(f"Missing required key in regime_result: {k}")
                
        snapshot_id = regime_result["snapshot_id"]
        regime = regime_result["regime"]
        
        if regime_result["is_historically_calibrated"] is not False:
            raise ValueError("is_historically_calibrated must be False")
            
        with self._lock:
            if snapshot_id in self._snapshot_ids:
                return {
                    "written": False,
                    "duplicate": True,
                    "snapshot_id": snapshot_id,
                    "dataset_path": str(self.dataset_path),
                    "record_count": self._physical_record_count
                }
                
            record = {
                "record_type": "cross_metal_regime_snapshot",
                "schema_version": "1.0",
                "written_at": datetime.now(timezone.utc).isoformat(),
                "snapshot_id": snapshot_id,
                "regime": regime,
                "record": regime_result
            }
            line = json.dumps(record, sort_keys=True, allow_nan=False, separators=(",", ":"))
            
            with open(self.dataset_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
                
            self._snapshot_ids.add(snapshot_id)
            self._physical_record_count += 1
            
            return {
                "written": True,
                "duplicate": False,
                "snapshot_id": snapshot_id,
                "dataset_path": str(self.dataset_path),
                "record_count": self._physical_record_count
            }

    def contains(self, snapshot_id: str) -> bool:
        with self._lock:
            return snapshot_id in self._snapshot_ids

    def record_count(self) -> int:
        with self._lock:
            return self._physical_record_count

    def snapshot_ids(self) -> List[str]:
        with self._lock:
            return sorted(list(self._snapshot_ids))

    def dataset_exists(self) -> bool:
        return self.dataset_path.exists()
