import json
import pathlib
import copy
from typing import Dict, Any, List, Optional

class GoldEpisodeDatasetReader:
    """
    Reader and metrics aggregator for Gold inefficiency episode JSONL datasets.
    """
    def __init__(self, dataset_path: str):
        self.dataset_path = pathlib.Path(dataset_path)

    def read_all(self, strict: bool = True) -> List[Dict[str, Any]]:
        records = []
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
                    
                required = ["record_type", "schema_version", "written_at", "episode"]
                missing_key = False
                for key in required:
                    if key not in record:
                        missing_key = True
                        break
                        
                if missing_key:
                    if strict:
                        raise ValueError(f"Malformed record on line {line_num}: missing required key")
                    continue

                if record.get("record_type") != "gold_inefficiency_episode":
                    if strict:
                        raise ValueError(f"Malformed record on line {line_num}: expected record_type 'gold_inefficiency_episode', got '{record.get('record_type')}'")
                    continue
                    
                records.append(record)
        return records

    def episodes(self, strict: bool = True) -> List[Dict[str, Any]]:
        records = self.read_all(strict=strict)
        return [r["episode"] for r in records]

    def closed_outcome_counts(self, strict: bool = True) -> Dict[str, int]:
        counts = {
            "CONVERGED": 0,
            "DIRECTION_REVERSED": 0,
            "SIGNAL_DECAYED": 0,
            "EXPIRED": 0,
            "MANUALLY_CLOSED": 0
        }
        for ep in self.episodes(strict=strict):
            outcome = ep.get("outcome")
            if outcome in counts:
                counts[outcome] += 1
        return counts

    def summary(self, strict: bool = True) -> Dict[str, Any]:
        records = self.read_all(strict=strict)
        record_count = len(records)
        
        if record_count == 0:
            return {
                "record_count": 0,
                "unique_episode_count": 0,
                "duplicate_episode_id_count": 0,
                "targets": {},
                "directions": {},
                "outcomes": {
                    "CONVERGED": 0,
                    "DIRECTION_REVERSED": 0,
                    "SIGNAL_DECAYED": 0,
                    "EXPIRED": 0,
                    "MANUALLY_CLOSED": 0
                },
                "average_duration_seconds": 0.0,
                "average_convergence_time_seconds": None,
                "average_max_favorable_excursion": 0.0,
                "average_max_adverse_excursion": 0.0,
                "average_update_count": 0.0,
                "average_uncertain_update_count": 0.0
            }

        episode_ids = [r["episode"]["episode_id"] for r in records]
        unique_episode_ids = set(episode_ids)
        unique_episode_count = len(unique_episode_ids)
        duplicate_episode_id_count = record_count - unique_episode_count
        
        targets = {}
        directions = {}
        outcomes = {
            "CONVERGED": 0,
            "DIRECTION_REVERSED": 0,
            "SIGNAL_DECAYED": 0,
            "EXPIRED": 0,
            "MANUALLY_CLOSED": 0
        }
        
        total_duration = 0.0
        total_conv_time = 0.0
        conv_count = 0
        total_mfe = 0.0
        total_mae = 0.0
        total_update_count = 0
        total_uncertain_update_count = 0
        
        for r in records:
            ep = r["episode"]
            
            t = ep.get("target")
            if t:
                targets[t] = targets.get(t, 0) + 1
                
            d = ep.get("recommended_direction")
            if d:
                directions[d] = directions.get(d, 0) + 1
                
            out = ep.get("outcome")
            if out in outcomes:
                outcomes[out] += 1
                
            total_duration += ep.get("duration_seconds", 0.0)
            
            conv_t = ep.get("convergence_time_seconds")
            if conv_t is not None:
                total_conv_time += conv_t
                conv_count += 1
                
            total_mfe += ep.get("max_favorable_excursion", 0.0)
            total_mae += ep.get("max_adverse_excursion", 0.0)
            total_update_count += ep.get("update_count", 0)
            total_uncertain_update_count += ep.get("uncertain_update_count", 0)
            
        def rnd(val):
            return round(float(val), 6)
            
        avg_dur = rnd(total_duration / record_count)
        avg_conv = rnd(total_conv_time / conv_count) if conv_count > 0 else None
        avg_mfe = rnd(total_mfe / record_count)
        avg_mae = rnd(total_mae / record_count)
        avg_up = rnd(total_update_count / record_count)
        avg_unc = rnd(total_uncertain_update_count / record_count)
        
        return {
            "record_count": record_count,
            "unique_episode_count": unique_episode_count,
            "duplicate_episode_id_count": duplicate_episode_id_count,
            "targets": targets,
            "directions": directions,
            "outcomes": outcomes,
            "average_duration_seconds": avg_dur,
            "average_convergence_time_seconds": avg_conv,
            "average_max_favorable_excursion": avg_mfe,
            "average_max_adverse_excursion": avg_mae,
            "average_update_count": avg_up,
            "average_uncertain_update_count": avg_unc
        }
