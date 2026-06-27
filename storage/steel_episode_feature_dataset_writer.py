from typing import Dict, Any, List
from ai.commodity_feature_profile import STEEL_FEATURE_PROFILE
from storage.commodity_episode_feature_dataset_writer import CommodityEpisodeFeatureDatasetWriter

class SteelEpisodeFeatureDatasetWriter:
    """
    Compatibility wrapper around CommodityEpisodeFeatureDatasetWriter for STEEL,
    preserving the original interface.
    """
    def __init__(self, dataset_path: str = "storage/steel_episode_features.jsonl"):
        self.writer = CommodityEpisodeFeatureDatasetWriter(dataset_path, STEEL_FEATURE_PROFILE)
        self.dataset_path = self.writer.dataset_path

    def write_example(self, built_example: Dict[str, Any]) -> Dict[str, Any]:
        return self.writer.write_example(built_example)

    def write_from_episode_dataset(self, episode_dataset_path: str, strict: bool = True) -> Dict[str, Any]:
        return self.writer.write_from_episode_dataset(episode_dataset_path, strict=strict)

    def contains(self, episode_id: str) -> bool:
        return self.writer.contains(episode_id)

    def record_count(self) -> int:
        return self.writer.record_count()

    def episode_ids(self) -> List[str]:
        return self.writer.episode_ids()

    def dataset_exists(self) -> bool:
        return self.writer.dataset_exists()
