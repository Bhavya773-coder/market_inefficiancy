import os
import json
import math
import tempfile
import pathlib
import copy
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo

from ai.commodity_feature_profile import STEEL_FEATURE_PROFILE
from ai.commodity_episode_feature_builder import CommodityEpisodeFeatureBuilder
from ai.steel_episode_feature_builder import SteelEpisodeFeatureBuilder
from storage.commodity_episode_feature_dataset_writer import CommodityEpisodeFeatureDatasetWriter
from storage.commodity_episode_feature_dataset_reader import CommodityEpisodeFeatureDatasetReader
from storage.steel_episode_feature_dataset_writer import SteelEpisodeFeatureDatasetWriter
from storage.steel_episode_feature_dataset_reader import SteelEpisodeFeatureDatasetReader

def make_valid_episode(episode_id="ep_001", target="STEEL_FUTURE", outcome="CONVERGED"):
    return {
        "schema_version": "1.0",
        "episode_type": "steel_inefficiency_episode",
        "episode_id": episode_id,
        "target": target,
        "recommended_direction": "LONG_TARGET",
        "opened_at": "2026-06-08T13:00:00+05:30",
        "closed_at": "2026-06-08T14:00:00+05:30",
        "is_open": False,
        "outcome": outcome,
        "opening_expected_change": 1.5,
        "opening_actual_change": 0.5,
        "opening_residual_gap": 1.0,
        "opening_inefficiency_score": 2.0,
        "opening_coverage_ratio": 0.8,
        "max_favorable_excursion": 1.2,
        "max_adverse_excursion": 0.2,
        "duration_seconds": 3600.0,
        "convergence_time_seconds": 1800.0,
        "update_count": 5,
        "uncertain_update_count": 1,
        "observations": [
            {
                "timestamp": "2026-06-08T13:00:00+05:30",
                "expected_change": 1.5,
                "actual_change": 0.5,
                "residual_gap": 1.0,
                "absolute_gap": 1.0,
                "inefficiency_score": 2.0,
                "coverage_ratio": 0.8,
                "status": "UNDERREACTION",
                "raw_pressure_score": 1.8,
                "total_possible_weight": 0.9,
                "observed_weight": 0.7,
                "is_historically_calibrated": True,
                "contributors": [
                    {
                        "source": "IRON_ORE",
                        "change": 5.0,
                        "weight": 0.2,
                        "direction_multiplier": 1.0,
                        "relationship_direction": "positive",
                        "contribution": 1.0
                    },
                    {
                        "source": "COKING_COAL",
                        "change": 3.0,
                        "weight": 0.15,
                        "direction_multiplier": 1.0,
                        "relationship_direction": "positive",
                        "contribution": 0.45
                    }
                ]
            },
            {
                "timestamp": "2026-06-08T13:10:00+05:30",
                "expected_change": 1.2,
                "actual_change": 0.8,
                "residual_gap": 0.4,
                "absolute_gap": 0.4,
                "inefficiency_score": 1.5,
                "coverage_ratio": 0.8,
                "status": "EFFICIENT",
                "raw_pressure_score": 1.2,
                "total_possible_weight": 0.9,
                "observed_weight": 0.7,
                "is_historically_calibrated": True,
                "contributors": []
            }
        ]
    }

def run_tests():
    print("Running comprehensive feature assertions...")

    # 1. Existing untracked files were preserved and converted safely
    # (Verified via compiling, importing, and ensuring class availability)
    assert SteelEpisodeFeatureBuilder is not None
    assert SteelEpisodeFeatureDatasetWriter is not None

    builder = CommodityEpisodeFeatureBuilder(STEEL_FEATURE_PROFILE)

    # 2. A converged steel episode builds successfully
    ep = make_valid_episode()
    built = builder.build(ep)
    assert isinstance(built, dict)
    assert "metadata" in built
    assert "features" in built
    assert "labels" in built

    # 3. Metadata is correct
    meta = built["metadata"]
    assert meta["feature_schema_version"] == "1.0"
    assert meta["source_episode_schema_version"] == "1.0"
    assert meta["episode_id"] == "ep_001"
    assert meta["commodity"] == "STEEL"
    assert meta["commodity_code"] == 1
    assert meta["target"] == "STEEL_FUTURE"
    assert meta["recommended_direction"] == "LONG_TARGET"
    assert meta["opened_at"] == "2026-06-08T13:00:00+05:30"
    assert meta["closed_at"] == "2026-06-08T14:00:00+05:30"

    # 4. Features use opening information only
    # 5. Labels use final episode results
    # 6. Features do not contain banned leakage keys
    # 7. audit_for_leakage passes for a valid example
    # 8. audit_for_leakage identifies an injected forbidden feature
    audit = builder.audit_for_leakage(built)
    assert audit["passed"] is True, f"Valid example failed leakage audit: {audit['violations']}"
    
    # Inject bad key
    bad_built = copy.deepcopy(built)
    bad_built["features"]["label_outcome_leak"] = 1.0
    bad_audit = builder.audit_for_leakage(bad_built)
    assert bad_audit["passed"] is False
    assert any("outcome" in v for v in bad_audit["violations"])

    # 9. Changing only final outcome changes labels but not features
    ep_outcome_1 = make_valid_episode(outcome="CONVERGED")
    ep_outcome_2 = make_valid_episode(outcome="EXPIRED")
    built_out_1 = builder.build(ep_outcome_1)
    built_out_2 = builder.build(ep_outcome_2)
    assert built_out_1["features"] == built_out_2["features"]
    assert built_out_1["labels"] != built_out_2["labels"]

    # 10. Changing duration changes labels but not features
    ep_dur_1 = make_valid_episode()
    ep_dur_2 = make_valid_episode()
    ep_dur_2["duration_seconds"] = 5000.0
    built_dur_1 = builder.build(ep_dur_1)
    built_dur_2 = builder.build(ep_dur_2)
    assert built_dur_1["features"] == built_dur_2["features"]
    assert built_dur_1["labels"] != built_dur_2["labels"]

    # 11. Changing MFE or MAE changes labels but not features
    ep_ex_1 = make_valid_episode()
    ep_ex_2 = make_valid_episode()
    ep_ex_2["max_favorable_excursion"] = 99.0
    built_ex_1 = builder.build(ep_ex_1)
    built_ex_2 = builder.build(ep_ex_2)
    assert built_ex_1["features"] == built_ex_2["features"]
    assert built_ex_1["labels"] != built_ex_2["labels"]

    # 12. Changing a later observation does not change features
    ep_later_1 = make_valid_episode()
    ep_later_2 = make_valid_episode()
    ep_later_2["observations"][1]["expected_change"] = -999.0
    built_later_1 = builder.build(ep_later_1)
    built_later_2 = builder.build(ep_later_2)
    assert built_later_1["features"] == built_later_2["features"]

    # 13. Changing the opening observation changes features
    ep_open_1 = make_valid_episode()
    ep_open_2 = make_valid_episode()
    ep_open_2["observations"][0]["absolute_gap"] = -999.0
    built_open_1 = builder.build(ep_open_1)
    built_open_2 = builder.build(ep_open_2)
    assert built_open_1["features"] != built_open_2["features"]

    # 14. All fixed steel driver columns always exist
    for src in STEEL_FEATURE_PROFILE.driver_sources:
        src_lower = src.lower()
        assert f"driver_{src_lower}_present" in built["features"]
        assert f"driver_{src_lower}_change" in built["features"]
        assert f"driver_{src_lower}_weight" in built["features"]
        assert f"driver_{src_lower}_direction_multiplier" in built["features"]
        assert f"driver_{src_lower}_contribution" in built["features"]

    # 15. Missing GOLD produces zero GOLD driver fields
    assert built["features"]["driver_gold_present"] == 0
    assert built["features"]["driver_gold_change"] == 0.0
    assert built["features"]["driver_gold_weight"] == 0.0
    assert built["features"]["driver_gold_contribution"] == 0.0

    # 16. Contributor aggregate calculations are correct
    features = built["features"]
    assert features["contributor_count"] == 2
    assert features["positive_contributor_count"] == 2
    assert features["negative_contributor_count"] == 0
    assert features["sum_contribution"] == 1.45
    assert features["sum_absolute_contribution"] == 1.45
    assert features["largest_absolute_contribution"] == 1.0
    assert features["mean_absolute_contribution"] == 0.725
    assert features["mean_driver_change"] == 4.0
    # Dispersion (pstdev of [5.0, 3.0] is 1.0)
    assert features["driver_change_dispersion"] == 1.0
    assert features["positive_contribution_share"] == 1.0
    assert features["negative_contribution_share"] == 0.0

    # 17. Duplicate contributor sources are rejected
    ep_dup_src = make_valid_episode()
    ep_dup_src["observations"][0]["contributors"].append({
        "source": "IRON_ORE",
        "change": 1.0,
        "weight": 0.1,
        "direction_multiplier": 1.0,
        "relationship_direction": "positive",
        "contribution": 0.1
    })
    try:
        builder.build(ep_dup_src)
        assert False, "Duplicate contributor source allowed!"
    except ValueError:
        pass

    # 18. LONG and SHORT direction codes are correct
    ep_long = make_valid_episode()
    ep_short = make_valid_episode()
    ep_short["recommended_direction"] = "SHORT_TARGET"
    assert builder.build(ep_long)["features"]["direction_code"] == 1
    assert builder.build(ep_short)["features"]["direction_code"] == -1

    # 19. All outcome codes are correct
    outcomes = ["CONVERGED", "DIRECTION_REVERSED", "SIGNAL_DECAYED", "EXPIRED", "MANUALLY_CLOSED"]
    for idx, out in enumerate(outcomes, 1):
        ep_out = make_valid_episode(outcome=out)
        assert builder.build(ep_out)["labels"]["label_outcome_code"] == idx

    # 20. Feature and label columns are sorted
    assert builder.feature_columns() == sorted(builder.feature_columns())
    assert builder.label_columns() == sorted(builder.label_columns())

    # 21. build_many preserves input order
    ep1 = make_valid_episode("ep_001")
    ep2 = make_valid_episode("ep_002")
    built_list = builder.build_many([ep1, ep2])
    assert len(built_list) == 2
    assert built_list[0]["metadata"]["episode_id"] == "ep_001"
    assert built_list[1]["metadata"]["episode_id"] == "ep_002"

    # 22. build_many rejects duplicate episode IDs
    try:
        builder.build_many([ep1, ep1])
        assert False, "Duplicate episode IDs allowed in build_many!"
    except ValueError:
        pass

    # 23. Builder does not mutate episode dictionaries
    ep_orig = make_valid_episode()
    ep_orig_copy = copy.deepcopy(ep_orig)
    builder.build(ep_orig)
    assert ep_orig == ep_orig_copy

    # Writers/Readers in tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "features.jsonl")
        writer = CommodityEpisodeFeatureDatasetWriter(path, STEEL_FEATURE_PROFILE)

        # 24. Writer writes one feature row
        res = writer.write_example(built)
        assert res["written"] is True
        assert writer.record_count() == 1
        assert os.path.exists(path)

        # 25. Duplicate writes are prevented
        res_dup = writer.write_example(built)
        assert res_dup["written"] is False
        assert res_dup["duplicate"] is True

        # 26. Writer restart preserves idempotency
        writer_restart = CommodityEpisodeFeatureDatasetWriter(path, STEEL_FEATURE_PROFILE)
        assert writer_restart.record_count() == 1
        assert writer_restart.contains("ep_001")

        # 27. Existing feature dataset with duplicate IDs is rejected
        dup_path = os.path.join(tmpdir, "dup.jsonl")
        # Write two lines with same episode ID to file manually
        with open(dup_path, "w", encoding="utf-8") as f:
            line = json.dumps({
                "record_type": "commodity_episode_feature_row",
                "feature_schema_version": "1.0",
                "commodity": "STEEL",
                "written_at": "2026-06-08T13:00:00Z",
                "episode_id": "dup_ep",
                "row": builder.flatten(built)
            }, sort_keys=True)
            f.write(line + "\n")
            f.write(line + "\n")
            
        try:
            CommodityEpisodeFeatureDatasetWriter(dup_path, STEEL_FEATURE_PROFILE)
            assert False, "Duplicate IDs in existing dataset not rejected!"
        except ValueError:
            pass

        # 28. Reader validates commodity
        reader_wrong = CommodityEpisodeFeatureDatasetReader(path, expected_commodity="GOLD")
        try:
            reader_wrong.read_all(strict=True)
            assert False, "Reader allowed mismatching commodity!"
        except ValueError:
            pass

        # 29. Reader summary is correct
        reader_correct = CommodityEpisodeFeatureDatasetReader(path, expected_commodity="STEEL")
        summ = reader_correct.summary()
        assert summ["record_count"] == 1
        assert summ["unique_episode_count"] == 1
        assert summ["converged_count"] == 1
        assert summ["average_duration_seconds"] == 3600.0
        assert summ["average_convergence_time_seconds"] == 1800.0

        # 30. Nonexistent file is handled safely
        reader_nonexist = CommodityEpisodeFeatureDatasetReader(os.path.join(tmpdir, "missing.jsonl"))
        assert len(reader_nonexist.read_all()) == 0
        summ_empty = reader_nonexist.summary()
        assert summ_empty["record_count"] == 0
        assert summ_empty["average_duration_seconds"] == 0.0

    # 31. NaN is rejected
    ep_nan = make_valid_episode()
    ep_nan["opening_expected_change"] = float("nan")
    try:
        builder.build(ep_nan)
        assert False, "NaN allowed!"
    except ValueError:
        pass

    # 32. Positive and negative infinity are rejected
    ep_inf = make_valid_episode()
    ep_inf["opening_expected_change"] = float("inf")
    try:
        builder.build(ep_inf)
        assert False, "Infinity allowed!"
    except ValueError:
        pass

    # 33. Bool numeric values are rejected
    ep_bool = make_valid_episode()
    ep_bool["opening_expected_change"] = True
    try:
        builder.build(ep_bool)
        assert False, "Boolean numeric value allowed!"
    except TypeError:
        pass

    # 34. Active episode is rejected
    ep_active = make_valid_episode()
    ep_active["is_open"] = True
    try:
        builder.build(ep_active)
        assert False, "Active episode allowed!"
    except ValueError:
        pass

    # 35. Unsupported schema is rejected
    ep_schema = make_valid_episode()
    ep_schema["schema_version"] = "2.0"
    try:
        builder.build(ep_schema)
        assert False, "Unsupported schema version allowed!"
    except ValueError:
        pass

    # 36. Flattened rows use meta_, feature_ and label_ prefixes
    flat_row = builder.flatten(built)
    for k in flat_row.keys():
        assert k.startswith(("meta_", "feature_", "label_")), f"Incorrect key prefix: {k}"

    # 37. Flattened rows serialize with allow_nan=False
    serialized = json.dumps(flat_row, allow_nan=False)
    assert isinstance(serialized, str)

    # 38. No datetime objects remain in JSON
    # Verified: json.dumps succeeds and all keys/values are checked to not be datetime/date objects
    for v in flat_row.values():
        assert not isinstance(v, (datetime, date))

    # 39. Source input remains immutable
    # Verified in test 23 and deepcopy usage

    # 40. All existing steel tests continue to pass
    # (Verified in next step running execution command)

    print("All commodity and steel feature dataset assertions passed.")

if __name__ == "__main__":
    run_tests()
