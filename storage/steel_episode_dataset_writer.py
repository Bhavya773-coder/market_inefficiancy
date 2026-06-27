import os
import json
import pathlib
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Set
from ai.steel_inefficiency_episode import SteelInefficiencyEpisode
from ai.steel_inefficiency_episode_tracker import SteelInefficiencyEpisodeTracker

class SteelEpisodeDatasetWriter:
    def __init__(self, dataset_path: str = "storage/steel_inefficiency_episodes.jsonl"):
        self.dataset_path = pathlib.Path(dataset_path)
        self._lock = threading.Lock()
        self._episode_ids: Set[str] = set()
        self._physical_record_count = 0
        
        # Ensure parent directory exists
        self.dataset_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Scan existing dataset to populate the episode ID cache
        self._scan_existing_dataset()

    def _scan_existing_dataset(self):
        self._physical_record_count = 0
        episode_id_first_seen_at = {}  # maps episode_id -> first_seen_line_number
        
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
                    if record.get("record_type") != "steel_inefficiency_episode":
                        raise ValueError(f"Record on line {line_num} has incorrect record_type: {record.get('record_type')}")
                    if record.get("schema_version") != "1.0":
                        raise ValueError(f"Record on line {line_num} has incorrect schema_version: {record.get('schema_version')}")
                    if not isinstance(record.get("written_at"), str):
                        raise ValueError(f"Record on line {line_num} written_at must be a string")
                    
                    episode = record.get("episode")
                    if not isinstance(episode, dict):
                        raise ValueError(f"Record on line {line_num} episode must be a dictionary")
                    if episode.get("schema_version") != "1.0":
                        raise ValueError(f"Record on line {line_num} episode schema_version must be '1.0'")
                    if episode.get("episode_type") != "steel_inefficiency_episode":
                        raise ValueError(f"Record on line {line_num} episode_type must be 'steel_inefficiency_episode'")
                    
                    episode_id = episode.get("episode_id")
                    if not isinstance(episode_id, str) or not episode_id:
                        raise ValueError(f"Record on line {line_num} episode_id must be a non-empty string")
                    if episode.get("is_open") is not False:
                        raise ValueError(f"Record on line {line_num} is_open must be False")
                    
                    outcome = episode.get("outcome")
                    valid_outcomes = {
                        "CONVERGED", "DIRECTION_REVERSED", "SIGNAL_DECAYED", "EXPIRED", "MANUALLY_CLOSED"
                    }
                    if outcome not in valid_outcomes:
                        raise ValueError(f"Record on line {line_num} outcome must be one of {valid_outcomes}, got: {outcome}")
                    
                    if episode_id in episode_id_first_seen_at:
                        first_line = episode_id_first_seen_at[episode_id]
                        raise ValueError(
                            f"Duplicate episode ID {episode_id} found on line {line_num}. "
                            f"It was first seen on line {first_line}."
                        )
                    
                    episode_id_first_seen_at[episode_id] = line_num
                    self._episode_ids.add(episode_id)
                    self._physical_record_count += 1

    def write_episode(self, episode: SteelInefficiencyEpisode) -> Dict[str, Any]:
        if not isinstance(episode, SteelInefficiencyEpisode):
            raise TypeError("episode must be a SteelInefficiencyEpisode")
            
        if episode.is_open or episode.outcome == "OPEN":
            raise ValueError("Cannot write an open episode")
            
        episode_id = episode.episode_id
        
        with self._lock:
            if episode_id in self._episode_ids:
                return {
                    "written": False,
                    "duplicate": True,
                    "episode_id": episode_id,
                    "dataset_path": str(self.dataset_path),
                    "record_count": self._physical_record_count
                }
                
            record = {
                "record_type": "steel_inefficiency_episode",
                "schema_version": "1.0",
                "written_at": datetime.now(timezone.utc).isoformat(),
                "episode": episode.to_dict()
            }
            line = json.dumps(record, sort_keys=True, allow_nan=False, separators=(",", ":"))
            
            with open(self.dataset_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
                
            self._episode_ids.add(episode_id)
            self._physical_record_count += 1
            
            return {
                "written": True,
                "duplicate": False,
                "episode_id": episode_id,
                "dataset_path": str(self.dataset_path),
                "record_count": self._physical_record_count
            }

    def write_new_closed_episodes(self, tracker) -> Dict[str, Any]:
        if not isinstance(tracker, SteelInefficiencyEpisodeTracker):
            raise TypeError("tracker must be a SteelInefficiencyEpisodeTracker")
            
        written_ids = []
        duplicate_ids = []
        
        for ep in tracker.closed_episodes():
            res = self.write_episode(ep)
            if res["written"]:
                written_ids.append(ep.episode_id)
            else:
                duplicate_ids.append(ep.episode_id)
                
        return {
            "written_count": len(written_ids),
            "duplicate_count": len(duplicate_ids),
            "record_count": self.record_count(),
            "written_episode_ids": written_ids,
            "duplicate_episode_ids": duplicate_ids
        }

    def contains(self, episode_id: str) -> bool:
        with self._lock:
            return episode_id in self._episode_ids

    def record_count(self) -> int:
        with self._lock:
            return self._physical_record_count

    def episode_ids(self) -> List[str]:
        with self._lock:
            return sorted(list(self._episode_ids))

    def dataset_exists(self) -> bool:
        return self.dataset_path.exists()
