import os
import sys
import json
import pprint
import argparse
import hashlib
import dataclasses
from datetime import datetime, timezone

from ai.commodity_replay_config import GOLD_HISTORICAL_REPLAY_CONFIG
from storage.commodity_historical_dataset_reader import CommodityHistoricalDatasetReader
from ai.gold_historical_replay_adapter import GoldHistoricalReplayAdapter
from ai.gold_inefficiency_episode_tracker import GoldInefficiencyEpisodeTracker
from storage.gold_episode_dataset_writer import GoldEpisodeDatasetWriter
from storage.gold_episode_feature_dataset_writer import GoldEpisodeFeatureDatasetWriter
from replay.commodity_historical_replay_runner import CommodityHistoricalReplayRunner

def main():
    parser = argparse.ArgumentParser(description="Deterministic point-in-time Gold Historical Replay Runner CLI")
    parser.add_argument("--input", required=True, help="Path to input CSV or JSONL historical price records")
    parser.add_argument("--episode-output", required=True, help="Path to output JSONL closed episode dataset")
    parser.add_argument("--feature-output", required=True, help="Path to output JSONL leakage-safe feature dataset")
    parser.add_argument("--replay-run-id", required=True, help="Unique identifier for the backtest replay run")
    parser.add_argument("--strict", action="store_true", default=True, help="Enforce strict chronological sorting (default: True)")
    parser.add_argument("--overwrite-output", action="store_true", help="Overwrite existing output files if present")
    
    args = parser.parse_args()

    # Pre-execution overwrite checks
    if not args.overwrite_output:
        if os.path.exists(args.episode_output):
            print(f"Error: Episode output file '{args.episode_output}' already exists. Use --overwrite-output to replace it.")
            sys.exit(1)
        if os.path.exists(args.feature_output):
            print(f"Error: Feature output file '{args.feature_output}' already exists. Use --overwrite-output to replace it.")
            sys.exit(1)
    else:
        # Only delete files, never directories
        if os.path.exists(args.episode_output):
            if os.path.isdir(args.episode_output):
                print(f"Error: Episode output path '{args.episode_output}' is a directory. Cannot overwrite.")
                sys.exit(1)
            os.remove(args.episode_output)
        if os.path.exists(args.feature_output):
            if os.path.isdir(args.feature_output):
                print(f"Error: Feature output path '{args.feature_output}' is a directory. Cannot overwrite.")
                sys.exit(1)
            os.remove(args.feature_output)

    # Compute input file hash
    if not os.path.exists(args.input):
        print(f"Error: Input path '{args.input}' does not exist.")
        sys.exit(1)
        
    sha = hashlib.sha256()
    with open(args.input, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    input_sha256 = sha.hexdigest()

    # Read dataset records
    print("=== READING INPUT DATASET ===")
    reader = CommodityHistoricalDatasetReader(args.input, strict=args.strict)
    try:
        records = reader.read_all()
    except Exception as e:
        print(f"Error parsing input dataset: {e}")
        sys.exit(1)
        
    pprint.pprint(reader.summary())

    # Build config
    config = dataclasses.replace(
        GOLD_HISTORICAL_REPLAY_CONFIG,
        output_episode_dataset_path=args.episode_output,
        output_feature_dataset_path=args.feature_output,
        replay_run_id=args.replay_run_id,
        strict_chronology=args.strict
    )

    # Instantiate runner dependencies
    adapter = GoldHistoricalReplayAdapter(config)
    tracker = GoldInefficiencyEpisodeTracker(
        convergence_gap_threshold=config.convergence_gap_threshold,
        max_episode_age_seconds=config.episode_max_age_seconds
    )
    episode_writer = GoldEpisodeDatasetWriter(args.episode_output)
    feature_writer = GoldEpisodeFeatureDatasetWriter(args.feature_output)

    runner = CommodityHistoricalReplayRunner(
        records=records,
        config=config,
        adapter=adapter,
        episode_tracker=tracker,
        episode_writer=episode_writer,
        feature_writer=feature_writer
    )

    print("\n=== RUNNING HISTORICAL REPLAY ===")
    manifest_data = runner.manifest(input_path=args.input, input_sha256=input_sha256)
    summary = manifest_data["result_summary"]
    pprint.pprint(summary)

    # Print remaining open episodes
    print("\n=== REMAINING ACTIVE OPEN EPISODES ===")
    active = tracker.active_episodes()
    if not active:
        print("None")
    else:
        for ep in active:
            print(f" - Target: {ep.target}, Direction: {ep.recommended_direction}, Opened: {ep.opened_at.isoformat()}")

    # Write manifest file
    manifest_path = f"{args.feature_output}.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, sort_keys=True)
    print(f"\nManifest successfully written to: {manifest_path}")

if __name__ == "__main__":
    main()
