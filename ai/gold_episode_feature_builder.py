from typing import Dict, Any, List
from ai.commodity_feature_profile import GOLD_FEATURE_PROFILE
from ai.commodity_episode_feature_builder import CommodityEpisodeFeatureBuilder

class GoldEpisodeFeatureBuilder:
    """
    Compatibility wrapper around CommodityEpisodeFeatureBuilder for GOLD.
    """
    def __init__(self, feature_schema_version: str = "1.0"):
        self.builder = CommodityEpisodeFeatureBuilder(GOLD_FEATURE_PROFILE)
        self.feature_schema_version = feature_schema_version

    def build(self, episode: Dict[str, Any]) -> Dict[str, Any]:
        return self.builder.build(episode)

    def feature_columns(self) -> List[str]:
        return self.builder.feature_columns()

    def label_columns(self) -> List[str]:
        return self.builder.label_columns()

    def flatten(self, built_example: Dict[str, Any]) -> Dict[str, Any]:
        return self.builder.flatten(built_example)

    def build_many(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.builder.build_many(episodes)

    def audit_for_leakage(self, built_example: Dict[str, Any]) -> Dict[str, Any]:
        return self.builder.audit_for_leakage(built_example)
