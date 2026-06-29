from typing import Dict, Any, List
from storage.commodity_episode_feature_dataset_reader import CommodityEpisodeFeatureDatasetReader

class GoldEpisodeFeatureDatasetReader:
    """
    Compatibility wrapper around CommodityEpisodeFeatureDatasetReader for GOLD.
    """
    def __init__(self, dataset_path: str = "storage/gold_episode_features.jsonl"):
        self.reader = CommodityEpisodeFeatureDatasetReader(dataset_path, expected_commodity="GOLD")
        self.dataset_path = self.reader.dataset_path

    def read_all(self, strict: bool = True) -> List[Dict[str, Any]]:
        return self.reader.read_all(strict=strict)

    def rows(self, strict: bool = True) -> List[Dict[str, Any]]:
        return self.reader.rows(strict=strict)

    def feature_columns(self, strict: bool = True) -> List[str]:
        return self.reader.feature_columns(strict=strict)

    def label_columns(self, strict: bool = True) -> List[str]:
        return self.reader.label_columns(strict=strict)

    def summary(self, strict: bool = True) -> Dict[str, Any]:
        return self.reader.summary(strict=strict)
