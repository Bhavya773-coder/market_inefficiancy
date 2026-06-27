import os
import json
import pathlib
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Set
from ai.steel_inefficiency_episode import SteelInefficiencyEpisode

class SteelEpisodeDatasetWriter:
    def __init__(self, dataset_path: str = "storage/steel_inefficiency_episodes.jsonl"):
        self.dataset_path = pathlib.Path(dataset_path)
        self._lock = threading.Lock()
        self._episode_ids: Set[str] = set()
        
        # Ensure parent directory exists
        self.dataset_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Scan existing dataset to populate the episode ID cache
        self._scan_existing_dataset()

    def _scan_existing_dataset(self):
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
                    
                    if "episode" not in record or "episode_id" not in record["episode"]:
                        raise ValueError(f"Malformed record on line {line_num}: missing episode or episode_id")
                    
                    self._episode_ids.add(record["episode"]["episode_id"])

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
                    "record_count": len(self._episode_ids)
                }
                
            record = {
                "record_type": "steel_inefficiency_episode",
                "schema_version": "1.0",
                "written_at": datetime.now(timezone.utc).isoformat(),
                "episode": episode.to_dict()
            }
            line = json.dumps(record, sort_keys=True)
            
            with open(self.dataset_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
                
            self._episode_ids.add(episode_id)
            
            return {
                "written": True,
                "duplicate": False,
                "episode_id": episode_id,
                "dataset_path": str(self.dataset_path),
                "record_count": len(self._episode_ids)
            }

    def write_new_closed_episodes(self, tracker) -> Dict[str, Any]:
        if tracker.__class__.__name__ != "SteelInefficiencyEpisodeTracker":
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
            return len(self._episode_ids)

    def episode_ids(self) -> List[str]:
        with self._lock:
            return list(self._episode_ids)

    def dataset_exists(self) -> bool:
        return self.dataset_path.exists()
