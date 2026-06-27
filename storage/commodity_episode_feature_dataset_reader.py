import json
import pathlib
import math
from datetime import datetime
from typing import Dict, Any, List, Set

class CommodityEpisodeFeatureDatasetReader:
    """
    Reader and validator for commodity episode feature rows written in JSONL format.
    """
    def __init__(self, dataset_path: str, expected_commodity: str = None):
        self.dataset_path = pathlib.Path(dataset_path)
        self.expected_commodity = expected_commodity
        self._duplicate_count = 0

    def read_all(self, strict: bool = True) -> List[Dict[str, Any]]:
        """
        Reads, parses, and validates outer records from the JSONL file.
        """
        records = []
        self._duplicate_count = 0
        if not self.dataset_path.exists():
            return records
            
        seen_ids = set()
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
                    
                if not isinstance(record, dict):
                    if strict:
                        raise ValueError(f"Record on line {line_num} is not a dictionary")
                    continue
                    
                if record.get("record_type") != "commodity_episode_feature_row":
                    if strict:
                        raise ValueError(f"Record on line {line_num} has incorrect record_type: {record.get('record_type')}")
                    continue
                if record.get("feature_schema_version") != "1.0":
                    if strict:
                        raise ValueError(f"Record on line {line_num} has incorrect feature_schema_version: {record.get('feature_schema_version')}")
                    continue
                    
                commodity = record.get("commodity")
                if not commodity or not isinstance(commodity, str):
                    if strict:
                        raise ValueError(f"Record on line {line_num} is missing commodity")
                    continue
                if self.expected_commodity and commodity != self.expected_commodity:
                    if strict:
                        raise ValueError(f"Record on line {line_num} has mismatching commodity '{commodity}'")
                    continue
                    
                written_at = record.get("written_at")
                try:
                    dt = datetime.fromisoformat(written_at)
                    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                        raise ValueError("Timestamp must be timezone-aware")
                except Exception as e:
                    if strict:
                        raise ValueError(f"Record on line {line_num} written_at is not timezone-aware: {e}")
                    continue
                    
                episode_id = record.get("episode_id")
                if not episode_id or not isinstance(episode_id, str):
                    if strict:
                        raise ValueError(f"Record on line {line_num} is missing episode_id")
                    continue
                    
                if episode_id in seen_ids:
                    self._duplicate_count += 1
                    if strict:
                        raise ValueError(f"Duplicate episode_id '{episode_id}' found on line {line_num}")
                    continue
                
                row = record.get("row")
                if not isinstance(row, dict):
                    if strict:
                        raise ValueError(f"Record on line {line_num} is missing inner row dictionary")
                    continue
                    
                if row.get("meta_episode_id") != episode_id:
                    if strict:
                        raise ValueError(f"Record on line {line_num} meta_episode_id mismatch")
                    continue
                if row.get("meta_commodity") != commodity:
                    if strict:
                        raise ValueError(f"Record on line {line_num} meta_commodity mismatch")
                    continue
                    
                # Validate numeric features and labels are finite
                numeric_validation_failed = False
                for k, v in row.items():
                    if k.startswith("feature_"):
                        if type(v) is bool:
                            if strict:
                                raise TypeError(f"Numeric feature {k} cannot be boolean")
                            numeric_validation_failed = True
                            break
                        if isinstance(v, (int, float)):
                            if math.isnan(v) or math.isinf(v):
                                if strict:
                                    raise ValueError(f"Numeric feature {k} must be finite")
                                numeric_validation_failed = True
                                break
                    elif k.startswith("label_"):
                        if v is not None:
                            if type(v) is bool:
                                if strict:
                                    raise TypeError(f"Numeric label {k} cannot be boolean")
                                numeric_validation_failed = True
                                break
                            if isinstance(v, (int, float)):
                                if math.isnan(v) or math.isinf(v):
                                    if strict:
                                        raise ValueError(f"Numeric label {k} must be finite")
                                    numeric_validation_failed = True
                                    break
                                    
                if numeric_validation_failed:
                    continue
                    
                seen_ids.add(episode_id)
                records.append(record)
        return records

    def rows(self, strict: bool = True) -> List[Dict[str, Any]]:
        """
        Returns validated inner row dictionaries.
        """
        return [rec["row"] for rec in self.read_all(strict=strict)]

    def feature_columns(self, strict: bool = True) -> List[str]:
        """
        Returns sorted feature column names starting with 'feature_'.
        """
        rows = self.rows(strict=strict)
        if not rows:
            return []
        return sorted([k for k in rows[0].keys() if k.startswith("feature_")])

    def label_columns(self, strict: bool = True) -> List[str]:
        """
        Returns sorted label column names starting with 'label_'.
        """
        rows = self.rows(strict=strict)
        if not rows:
            return []
        return sorted([k for k in rows[0].keys() if k.startswith("label_")])

    def summary(self, strict: bool = True) -> Dict[str, Any]:
        """
        Calculates descriptive summary statistics of the dataset.
        """
        records = self.read_all(strict=strict)
        unique_episode_count = len(records)
        
        if unique_episode_count == 0:
            return {
                "record_count": 0,
                "unique_episode_count": 0,
                "duplicate_episode_id_count": self._duplicate_count,
                "commodity_counts": {},
                "target_counts": {},
                "direction_counts": {},
                "outcome_counts": {},
                "converged_count": 0,
                "non_converged_count": 0,
                "average_duration_seconds": 0.0,
                "average_convergence_time_seconds": 0.0,
                "average_max_favorable_excursion": 0.0,
                "average_max_adverse_excursion": 0.0,
                "average_update_count": 0.0,
                "average_uncertain_update_count": 0.0,
                "feature_column_count": 0,
                "label_column_count": 0
            }

        commodity_counts = {}
        target_counts = {}
        direction_counts = {}
        outcome_counts = {}
        converged_count = 0
        non_converged_count = 0
        
        durations = []
        conv_times = []
        mfes = []
        maes = []
        updates = []
        uncertain_updates = []

        OUTCOME_CODE_TO_NAME = {
            1: "CONVERGED",
            2: "DIRECTION_REVERSED",
            3: "SIGNAL_DECAYED",
            4: "EXPIRED",
            5: "MANUALLY_CLOSED"
        }

        first_row = records[0]["row"]
        feature_column_count = len([k for k in first_row.keys() if k.startswith("feature_")])
        label_column_count = len([k for k in first_row.keys() if k.startswith("label_")])

        for rec in records:
            row = rec["row"]
            
            comm = rec["commodity"]
            commodity_counts[comm] = commodity_counts.get(comm, 0) + 1
            
            tgt = row.get("meta_target")
            target_counts[tgt] = target_counts.get(tgt, 0) + 1
            
            direc = row.get("meta_recommended_direction")
            direction_counts[direc] = direction_counts.get(direc, 0) + 1
            
            out_code = row.get("label_outcome_code")
            out_name = OUTCOME_CODE_TO_NAME.get(out_code, f"UNKNOWN_{out_code}")
            outcome_counts[out_name] = outcome_counts.get(out_name, 0) + 1
            
            is_conv = row.get("label_converged")
            if is_conv == 1:
                converged_count += 1
            else:
                non_converged_count += 1
                
            durations.append(row["label_duration_seconds"])
            
            conv_t = row.get("label_convergence_time_seconds")
            if conv_t is not None:
                conv_times.append(conv_t)
                
            mfes.append(row["label_max_favorable_excursion"])
            maes.append(row["label_max_adverse_excursion"])
            updates.append(row["label_update_count"])
            uncertain_updates.append(row["label_uncertain_update_count"])

        return {
            "record_count": unique_episode_count,
            "unique_episode_count": unique_episode_count,
            "duplicate_episode_id_count": self._duplicate_count,
            "commodity_counts": commodity_counts,
            "target_counts": target_counts,
            "direction_counts": direction_counts,
            "outcome_counts": outcome_counts,
            "converged_count": converged_count,
            "non_converged_count": non_converged_count,
            "average_duration_seconds": round(sum(durations) / len(durations), 6),
            "average_convergence_time_seconds": round(sum(conv_times) / len(conv_times) if conv_times else 0.0, 6),
            "average_max_favorable_excursion": round(sum(mfes) / len(mfes), 6),
            "average_max_adverse_excursion": round(sum(maes) / len(maes), 6),
            "average_update_count": round(sum(updates) / len(updates), 6),
            "average_uncertain_update_count": round(sum(uncertain_updates) / len(uncertain_updates), 6),
            "feature_column_count": feature_column_count,
            "label_column_count": label_column_count
        }
