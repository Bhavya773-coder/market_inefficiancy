import csv
import json
import copy
import pathlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from ai.commodity_historical_record import CommodityHistoricalRecord

class CommodityHistoricalDatasetReader:
    """
    Reader for commodity historical price datasets (CSV or JSONL).
    Enforces sorted order and points-in-time duplicate protection.
    """
    def __init__(self, dataset_path: str, strict: bool = True):
        self.dataset_path = pathlib.Path(dataset_path)
        self.strict = strict
        self._records: List[CommodityHistoricalRecord] = []
        self._summary_data: Optional[Dict[str, Any]] = None

    def read_all(self) -> List[CommodityHistoricalRecord]:
        """
        Reads, parses, validates, and sorts all records.
        """
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset path not found: {self.dataset_path}")
            
        ext = self.dataset_path.suffix.lower()
        if ext not in (".csv", ".jsonl", ".json"):
            raise ValueError(f"Unsupported file extension: {ext}")

        raw_records = []
        if ext == ".csv":
            with open(self.dataset_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                required_cols = ["timestamp", "instrument", "price", "volume", "source"]
                for col in required_cols:
                    if not reader.fieldnames or col not in reader.fieldnames:
                        raise ValueError(f"CSV file missing required column: {col}")
                        
                for line_num, row in enumerate(reader, 2):
                    try:
                        ts_str = row["timestamp"]
                        inst = row["instrument"]
                        price_str = row["price"]
                        vol_str = row["volume"]
                        src = row["source"]
                        
                        vol = None
                        if vol_str and vol_str.strip():
                            vol = float(vol_str)
                            
                        # Extra columns go to metadata
                        metadata = {}
                        for k, v in row.items():
                            if k not in required_cols:
                                metadata[k] = v
                                
                        raw_records.append({
                            "timestamp": ts_str,
                            "instrument": inst,
                            "price": float(price_str),
                            "volume": vol,
                            "source": src,
                            "metadata": metadata,
                            "line_num": line_num
                        })
                    except Exception as e:
                        raise ValueError(f"Malformed CSV row on line {line_num}: {e}")
        else:
            with open(self.dataset_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        data = json.loads(stripped)
                        raw_records.append({
                            "timestamp": data["timestamp"],
                            "instrument": data["instrument"],
                            "price": data["price"],
                            "volume": data.get("volume"),
                            "source": data["source"],
                            "metadata": data.get("metadata", {}),
                            "line_num": line_num
                        })
                    except Exception as e:
                        raise ValueError(f"Malformed JSONL on line {line_num}: {e}")

        # Instantiate records
        records_instantiated = []
        for r in raw_records:
            try:
                rec = CommodityHistoricalRecord.from_dict(r)
                records_instantiated.append(rec)
            except Exception as e:
                raise ValueError(f"Validation failed for record on line {r['line_num']}: {e}")

        # Process ordering and duplicates
        self._records = []
        seen_keys = set()
        duplicate_count = 0
        out_of_order_count = 0
        missing_volume_count = 0
        source_counts = {}
        unique_instruments = set()
        
        max_ts = None
        for rec in records_instantiated:
            ts = rec.timestamp
            inst = rec.instrument
            key = (ts, inst)
            
            # Check chronology
            if max_ts is not None and ts < max_ts:
                out_of_order_count += 1
                if self.strict:
                    raise ValueError(f"Chronology violation: timestamp {ts} is earlier than max timestamp {max_ts}")
                continue
                
            # Check duplicate
            if key in seen_keys:
                duplicate_count += 1
                if self.strict:
                    raise ValueError(f"Duplicate record found for {inst} at {ts}")
                continue

            seen_keys.add(key)
            if ts is not None:
                if max_ts is None or ts > max_ts:
                    max_ts = ts
                    
            self._records.append(rec)
            unique_instruments.add(inst)
            
            if rec.volume is None:
                missing_volume_count += 1
                
            source_counts[rec.source] = source_counts.get(rec.source, 0) + 1

        self._summary_data = {
            "record_count": len(self._records),
            "instrument_count": len(unique_instruments),
            "instruments": sorted(list(unique_instruments)),
            "start_timestamp": self._records[0].timestamp if self._records else None,
            "end_timestamp": self._records[-1].timestamp if self._records else None,
            "duplicate_count": duplicate_count,
            "out_of_order_count": out_of_order_count,
            "missing_volume_count": missing_volume_count,
            "source_counts": source_counts
        }
        
        return self._records

    def summary(self) -> Dict[str, Any]:
        """
        Returns summary dictionary. Runs read_all if not loaded yet.
        """
        if self._summary_data is None:
            self.read_all()
        return copy.deepcopy(self._summary_data)
