import os
import json
import pathlib
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Set
from ai.commodity_feature_profile import CommodityFeatureProfile
from ai.commodity_episode_feature_builder import CommodityEpisodeFeatureBuilder

class CommodityEpisodeFeatureDatasetWriter:
    """
    Leakage-safe, thread-safe writer to record flattened commodity feature examples.
    """
    def __init__(self, dataset_path: str, profile: CommodityFeatureProfile):
        if not isinstance(profile, CommodityFeatureProfile):
            raise TypeError("profile must be a CommodityFeatureProfile instance")
            
        self.dataset_path = pathlib.Path(dataset_path)
        self.profile = profile
        self._lock = threading.Lock()
        self._episode_ids: Set[str] = set()
        self._physical_record_count = 0
        
        self.dataset_path.parent.mkdir(parents=True, exist_ok=True)
        self._scan_existing_dataset()

    def _scan_existing_dataset(self):
        self._physical_record_count = 0
        episode_id_first_seen_at = {}
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
                    if record.get("record_type") != "commodity_episode_feature_row":
                        raise ValueError(f"Record on line {line_num} has incorrect record_type: {record.get('record_type')}")
                    if record.get("feature_schema_version") != "1.0":
                        raise ValueError(f"Record on line {line_num} has incorrect feature_schema_version: {record.get('feature_schema_version')}")
                    
                    commodity = record.get("commodity")
                    if commodity != self.profile.commodity:
                        raise ValueError(f"Record on line {line_num} has mismatching commodity '{commodity}' (expected '{self.profile.commodity}')")
                        
                    ep_id = record.get("episode_id")
                    if not ep_id or not isinstance(ep_id, str):
                        raise ValueError(f"Record on line {line_num} is missing episode_id")
                        
                    if ep_id in episode_id_first_seen_at:
                        first_line = episode_id_first_seen_at[ep_id]
                        raise ValueError(
                            f"Duplicate episode ID {ep_id} found on line {line_num}. "
                            f"It was first seen on line {first_line}."
                        )
                        
                    episode_id_first_seen_at[ep_id] = line_num
                    self._episode_ids.add(ep_id)
                    self._physical_record_count += 1

    def write_example(self, built_example: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates, flattens, and appends a built example to the JSONL dataset file.
        """
        if not isinstance(built_example, dict):
            raise TypeError("built_example must be a dictionary")
        if "metadata" not in built_example or not isinstance(built_example["metadata"], dict):
            raise KeyError("built_example must contain a 'metadata' dictionary")
        if "features" not in built_example or not isinstance(built_example["features"], dict):
            raise KeyError("built_example must contain a 'features' dictionary")
        if "labels" not in built_example or not isinstance(built_example["labels"], dict):
            raise KeyError("built_example must contain a 'labels' dictionary")
            
        meta = built_example["metadata"]
        ep_id = meta.get("episode_id")
        if not ep_id or not isinstance(ep_id, str):
            raise ValueError("built_example metadata must contain a non-empty string episode_id")
            
        if meta.get("feature_schema_version") != "1.0":
            raise ValueError("Unsupported feature_schema_version")

        builder = CommodityEpisodeFeatureBuilder(self.profile)
        flat_row = builder.flatten(built_example)
        
        record = {
            "record_type": "commodity_episode_feature_row",
            "feature_schema_version": "1.0",
            "commodity": self.profile.commodity,
            "written_at": datetime.now(timezone.utc).isoformat(),
            "episode_id": ep_id,
            "row": flat_row
        }
        line = json.dumps(record, sort_keys=True, allow_nan=False, separators=(",", ":"))
        
        with self._lock:
            if ep_id in self._episode_ids:
                return {
                    "written": False,
                    "duplicate": True,
                    "episode_id": ep_id,
                    "record_count": self._physical_record_count,
                    "dataset_path": str(self.dataset_path)
                }
                
            with open(self.dataset_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
                
            self._episode_ids.add(ep_id)
            self._physical_record_count += 1
            
            return {
                "written": True,
                "duplicate": False,
                "episode_id": ep_id,
                "record_count": self._physical_record_count,
                "dataset_path": str(self.dataset_path)
            }

    def write_from_episode_dataset(self, episode_dataset_path: str, strict: bool = True) -> Dict[str, Any]:
        """
        Reads episodes from an episode dataset file, processes features, and saves them.
        """
        from storage.steel_episode_dataset_reader import SteelEpisodeDatasetReader
        
        reader = SteelEpisodeDatasetReader(episode_dataset_path)
        builder = CommodityEpisodeFeatureBuilder(self.profile)
        
        episodes_list = reader.episodes(strict=strict)
        
        source_episode_count = len(episodes_list)
        written_count = 0
        duplicate_count = 0
        written_episode_ids = []
        duplicate_episode_ids = []
        
        for ep in episodes_list:
            built = builder.build(ep)
            res = self.write_example(built)
            if res["written"]:
                written_count += 1
                written_episode_ids.append(ep["episode_id"])
            else:
                duplicate_count += 1
                duplicate_episode_ids.append(ep["episode_id"])
                
        return {
            "source_episode_count": source_episode_count,
            "written_count": written_count,
            "duplicate_count": duplicate_count,
            "record_count": self.record_count(),
            "written_episode_ids": written_episode_ids,
            "duplicate_episode_ids": duplicate_episode_ids
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
