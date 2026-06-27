import uuid
import hashlib
import json
import copy
from datetime import datetime, timezone
from collections import defaultdict
from typing import List, Dict, Any, Optional

from ai.commodity_replay_config import CommodityReplayConfig
from ai.point_in_time_price_store import PointInTimePriceStore
from ai.commodity_episode_feature_builder import CommodityEpisodeFeatureBuilder
from ai.commodity_feature_profile import STEEL_FEATURE_PROFILE

class CommodityHistoricalReplayRunner:
    """
    Point-in-time safe historical replay executor that runs indicators,
    calculates pressure/inefficiency signals, and creates features.
    """
    def __init__(
        self,
        records: List[Any],
        config: CommodityReplayConfig,
        adapter: Any,
        episode_tracker: Any,
        episode_writer: Any,
        feature_writer: Any
    ):
        self.records = records
        self.config = config
        self.adapter = adapter
        self.episode_tracker = episode_tracker
        self.episode_writer = episode_writer
        self.feature_writer = feature_writer

        # Configure feature builder based on commodity
        if config.commodity == "STEEL":
            self.feature_builder = CommodityEpisodeFeatureBuilder(STEEL_FEATURE_PROFILE)
        else:
            raise ValueError(f"Unsupported commodity profile: {config.commodity}")

        # Inject deterministic episode_id_factory into tracker
        def episode_id_factory(target: str, recommended_direction: str, observed_at: datetime) -> str:
            name = f"{self.config.replay_run_id}:{self.config.commodity}:{target}:{recommended_direction}:{observed_at.isoformat()}"
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))
            
        self.episode_tracker.episode_id_factory = episode_id_factory
        self.price_store = PointInTimePriceStore()

    def run(self) -> Dict[str, Any]:
        """
        Executes the point-in-time replay over all records.
        """
        self.price_store = PointInTimePriceStore()
        # Group records by timestamp
        records_by_ts = defaultdict(list)
        for r in self.records:
            records_by_ts[r.timestamp].append(r)
            
        sorted_timestamps = sorted(list(records_by_ts.keys()))

        # Stats counters
        decision_timestamp_count = 0
        ready_detection_count = 0
        skipped_detection_count = 0
        
        opened_episode_count = 0
        updated_episode_count = 0
        closed_episode_count = 0
        
        written_episode_count = 0
        written_feature_count = 0
        duplicate_episode_count = 0
        duplicate_feature_count = 0

        missing_instrument_counts = {}
        stale_instrument_counts = {}
        outcome_counts = {}

        # Replay loop
        for ts in sorted_timestamps:
            # Set cursor timestamp to prevent future writes
            self.price_store.cursor_timestamp = ts
            
            # Feed current step records into store
            for r in records_by_ts[ts]:
                self.price_store.add(r)

            # Check if any decision instrument updated
            decision_updated = any(r.instrument in self.config.decision_instruments for r in records_by_ts[ts])
            
            if decision_updated:
                decision_timestamp_count += 1
                
                # Check adapter diagnostics
                diag = self.adapter.build_changes(self.price_store, ts)
                
                # Record missing/stale statistics
                for inst in diag.get("missing_instruments", []):
                    missing_instrument_counts[inst] = missing_instrument_counts.get(inst, 0) + 1
                for inst in diag.get("stale_instruments", []):
                    stale_instrument_counts[inst] = stale_instrument_counts.get(inst, 0) + 1

                if diag["is_ready"]:
                    ready_detection_count += 1
                    detection_result = self.adapter.detect(self.price_store, ts)
                else:
                    skipped_detection_count += 1
                    detection_result = self.adapter.detect(self.price_store, ts)

                # Process detection through tracker
                step_result = self.episode_tracker.process(detection_result, ts)
                
                opened_episode_count += len(step_result.get("opened", []))
                updated_episode_count += len(step_result.get("updated", []))
                closed_episode_count += len(step_result.get("closed", []))

                # Write closed episodes and features in point-of-time loop
                for ep in self.episode_tracker.closed_episodes():
                    ep_id = ep.episode_id
                    if not self.episode_writer.contains(ep_id):
                        res_ep = self.episode_writer.write_episode(ep)
                        if res_ep["written"]:
                            written_episode_count += 1
                            outcome_counts[ep.outcome] = outcome_counts.get(ep.outcome, 0) + 1
                            
                            # Build and write features
                            ep_dict = ep.to_dict()
                            built_feat = self.feature_builder.build(ep_dict)
                            res_feat = self.feature_writer.write_example(built_feat)
                            if res_feat["written"]:
                                written_feature_count += 1
                            else:
                                duplicate_feature_count += 1
                        else:
                            duplicate_episode_count += 1

        # Finalize open episodes at the final timestamp
        final_ts = sorted_timestamps[-1] if sorted_timestamps else None
        if final_ts is not None:
            active_episodes = self.episode_tracker.active_episodes()
            strategy = self.config.finalize_open_episodes
            
            for ep in list(active_episodes):
                if strategy == "MANUALLY_CLOSE":
                    self.episode_tracker.manually_close(ep.target, final_ts)
                elif strategy == "EXPIRE_IF_OLD":
                    if self.config.episode_max_age_seconds is not None and ep.duration_seconds >= self.config.episode_max_age_seconds:
                        ep.close("EXPIRED", final_ts)
                        self.episode_tracker._active_by_target.pop(ep.target)
                        self.episode_tracker._closed_episodes.append(ep)

            # Write finalized closed episodes
            for ep in self.episode_tracker.closed_episodes():
                ep_id = ep.episode_id
                if not self.episode_writer.contains(ep_id):
                    res_ep = self.episode_writer.write_episode(ep)
                    if res_ep["written"]:
                        written_episode_count += 1
                        outcome_counts[ep.outcome] = outcome_counts.get(ep.outcome, 0) + 1
                        
                        ep_dict = ep.to_dict()
                        built_feat = self.feature_builder.build(ep_dict)
                        res_feat = self.feature_writer.write_example(built_feat)
                        if res_feat["written"]:
                            written_feature_count += 1
                        else:
                            duplicate_feature_count += 1
                    else:
                        duplicate_episode_count += 1

        # Calculate deterministic run hash
        record_dicts = [r.to_dict() for r in self.records]
        records_json = json.dumps(record_dicts, sort_keys=True)
        
        config_dict = {
            "replay_run_id": self.config.replay_run_id,
            "commodity": self.config.commodity,
            "target_instruments": self.config.target_instruments,
            "driver_instruments": self.config.driver_instruments,
            "minimum_required_driver_count": self.config.minimum_required_driver_count,
            "episode_max_age_seconds": self.config.episode_max_age_seconds,
            "convergence_gap_threshold": self.config.convergence_gap_threshold,
            "finalize_open_episodes": self.config.finalize_open_episodes
        }
        config_json = json.dumps(config_dict, sort_keys=True)
        
        ep_ids = sorted(self.episode_writer.episode_ids())
        ep_ids_json = json.dumps(ep_ids)
        
        feat_ids = sorted(self.feature_writer.episode_ids())
        feat_ids_json = json.dumps(feat_ids)

        combined_payload = f"{records_json}|{config_json}|{ep_ids_json}|{feat_ids_json}"
        deterministic_run_hash = hashlib.sha256(combined_payload.encode("utf-8")).hexdigest()

        summary = {
            "replay_run_id": self.config.replay_run_id,
            "commodity": self.config.commodity,
            "input_record_count": len(self.records),
            "processed_timestamp_count": len(sorted_timestamps),
            "decision_timestamp_count": decision_timestamp_count,
            "ready_detection_count": ready_detection_count,
            "skipped_detection_count": skipped_detection_count,
            "opened_episode_count": opened_episode_count,
            "updated_episode_count": updated_episode_count,
            "closed_episode_count": closed_episode_count,
            "written_episode_count": written_episode_count,
            "written_feature_count": written_feature_count,
            "duplicate_episode_count": duplicate_episode_count,
            "duplicate_feature_count": duplicate_feature_count,
            "remaining_open_episode_count": len(self.episode_tracker.active_episodes()),
            "start_timestamp": sorted_timestamps[0].isoformat() if sorted_timestamps else None,
            "end_timestamp": sorted_timestamps[-1].isoformat() if sorted_timestamps else None,
            "missing_instrument_counts": missing_instrument_counts,
            "stale_instrument_counts": stale_instrument_counts,
            "outcome_counts": outcome_counts,
            "deterministic_run_hash": deterministic_run_hash
        }
        
        return summary

    def manifest(self, input_path: Optional[str] = None, input_sha256: Optional[str] = None) -> Dict[str, Any]:
        """
        Generates a reproducible run manifest for cataloging model training data.
        """
        summary = self.run()
        
        config_dict = {
            "replay_run_id": self.config.replay_run_id,
            "commodity": self.config.commodity,
            "target_instruments": self.config.target_instruments,
            "driver_instruments": self.config.driver_instruments,
            "minimum_required_driver_count": self.config.minimum_required_driver_count,
            "episode_max_age_seconds": self.config.episode_max_age_seconds,
            "convergence_gap_threshold": self.config.convergence_gap_threshold,
            "finalize_open_episodes": self.config.finalize_open_episodes,
            "output_episode_dataset_path": self.config.output_episode_dataset_path,
            "output_feature_dataset_path": self.config.output_feature_dataset_path
        }

        manifest_data = {
            "replay_schema_version": "1.0",
            "replay_run_id": self.config.replay_run_id,
            "commodity": self.config.commodity,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "input_path": input_path,
            "input_sha256": input_sha256,
            "configuration": config_dict,
            "record_summary": {
                "input_record_count": summary["input_record_count"],
                "processed_timestamp_count": summary["processed_timestamp_count"],
                "start_timestamp": summary["start_timestamp"],
                "end_timestamp": summary["end_timestamp"]
            },
            "result_summary": summary,
            "is_historically_calibrated": False
        }
        
        return manifest_data
