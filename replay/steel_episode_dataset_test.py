import os
import json
import math
import copy
import tempfile
import pathlib
from datetime import datetime, timezone, timedelta
from ai.steel_inefficiency_detector import SteelInefficiencyDetector
from ai.steel_inefficiency_episode import SteelInefficiencyEpisode
from ai.steel_inefficiency_episode_tracker import SteelInefficiencyEpisodeTracker
from storage.steel_episode_dataset_writer import SteelEpisodeDatasetWriter
from storage.steel_episode_dataset_reader import SteelEpisodeDatasetReader

def main():
    print("Starting comprehensive dataset regression tests...")

    base_positive_drivers = {
        "IRON_ORE": 5.0,
        "COKING_COAL": 3.0,
        "SCRAP_STEEL": 1.0,
        "BALTIC_DRY": 2.0,
        "CRUDE_OIL": 1.5,
        "USDINR": 0.5,
        "NIFTY_METAL": 2.0,
        "TATASTEEL": 1.0,
        "JSWSTEEL": 1.0,
        "GOLD": -1.0
    }

    base_negative_drivers = {
        "IRON_ORE": -5.0,
        "COKING_COAL": -3.0,
        "SCRAP_STEEL": -1.0,
        "BALTIC_DRY": -2.0,
        "CRUDE_OIL": -1.5,
        "USDINR": -0.5,
        "NIFTY_METAL": -2.0,
        "TATASTEEL": -1.0,
        "JSWSTEEL": -1.0,
        "GOLD": 1.0
    }

    detector = SteelInefficiencyDetector()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = pathlib.Path(tmpdir) / "test_dataset.jsonl"
        writer = SteelEpisodeDatasetWriter(dataset_path=str(tmp_path))
        reader = SteelEpisodeDatasetReader(dataset_path=str(tmp_path))

        # -------------------------------------------------------------------------
        # SCENARIO 1 — Closed convergence episode is written
        # -------------------------------------------------------------------------
        print("\nScenario 1: Closed convergence episode is written")
        tracker_s1 = SteelInefficiencyEpisodeTracker()
        t1 = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        
        # Filter changes to STEEL_FUTURE only
        changes_s1 = dict(base_positive_drivers)
        changes_s1["STEEL_FUTURE"] = 0.50
        res_s1 = detector.detect(changes_s1)
        res_s1_f = {
            "targets": {"STEEL_FUTURE": res_s1["targets"]["STEEL_FUTURE"]},
            "summary": res_s1["summary"]
        }
        
        tracker_s1.process(res_s1_f, t1)
        active_ep = tracker_s1.active_for("STEEL_FUTURE")
        assert active_ep is not None
        
        # Converge at t2
        t2 = t1 + timedelta(hours=1)
        expected_fut = res_s1_f["targets"]["STEEL_FUTURE"]["expected_change"]
        changes_s2 = dict(base_positive_drivers)
        changes_s2["STEEL_FUTURE"] = expected_fut
        res_s2 = detector.detect(changes_s2)
        res_s2_f = {
            "targets": {"STEEL_FUTURE": res_s2["targets"]["STEEL_FUTURE"]},
            "summary": res_s2["summary"]
        }
        
        tracker_s1.process(res_s2_f, t2)
        assert tracker_s1.active_for("STEEL_FUTURE") is None
        assert len(tracker_s1.closed_episodes()) == 1
        
        # Write to dataset
        write_res = writer.write_new_closed_episodes(tracker_s1)
        assert write_res["written_count"] == 1
        assert write_res["duplicate_count"] == 0
        assert write_res["record_count"] == 1
        
        # Confirm file exists
        assert tmp_path.exists()
        
        # Check that we can read it back
        episodes_read = reader.episodes()
        assert len(episodes_read) == 1
        assert episodes_read[0]["target"] == "STEEL_FUTURE"
        assert episodes_read[0]["outcome"] == "CONVERGED"

        # -------------------------------------------------------------------------
        # SCENARIO 2 — Duplicate write prevention
        # -------------------------------------------------------------------------
        print("\nScenario 2: Duplicate write prevention")
        closed_ep = tracker_s1.closed_episodes()[0]
        
        # Re-write the same episode
        write_res2 = writer.write_episode(closed_ep)
        assert write_res2["written"] is False
        assert write_res2["duplicate"] is True
        assert write_res2["record_count"] == 1
        
        # Verify lines count in file did not increase
        with open(tmp_path, "r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == 1

        # -------------------------------------------------------------------------
        # SCENARIO 3 — Writer restart idempotency
        # -------------------------------------------------------------------------
        print("\nScenario 3: Writer restart idempotency")
        writer_restart = SteelEpisodeDatasetWriter(dataset_path=str(tmp_path))
        assert writer_restart.contains(closed_ep.episode_id) is True
        assert writer_restart.record_count() == 1
        
        write_res3 = writer_restart.write_episode(closed_ep)
        assert write_res3["written"] is False
        assert write_res3["duplicate"] is True
        assert write_res3["record_count"] == 1

        # -------------------------------------------------------------------------
        # SCENARIO 4 — Active episode rejected
        # -------------------------------------------------------------------------
        print("\nScenario 4: Active episode rejected")
        active_ep_test = SteelInefficiencyEpisode.from_detection(res_s1_f["targets"]["STEEL_FUTURE"], t1)
        assert active_ep_test.is_open is True
        
        try:
            writer.write_episode(active_ep_test)
            assert False, "Active episode was not rejected"
        except ValueError:
            pass

        # -------------------------------------------------------------------------
        # SCENARIO 5 — Multiple outcomes
        # -------------------------------------------------------------------------
        print("\nScenario 5: Multiple outcomes")
        # Clean the file first by using a new temp path
        tmp_path_s5 = pathlib.Path(tmpdir) / "test_dataset_s5.jsonl"
        writer_s5 = SteelEpisodeDatasetWriter(dataset_path=str(tmp_path_s5))
        reader_s5 = SteelEpisodeDatasetReader(dataset_path=str(tmp_path_s5))
        
        # 1. CONVERGED (already tested, let's make one)
        tracker_s5 = SteelInefficiencyEpisodeTracker()
        tracker_s5.process(res_s1_f, t1)
        tracker_s5.process(res_s2_f, t2)
        
        # 2. DIRECTION_REVERSED
        t3 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        tracker_s5.process(res_s1_f, t3) # Opens LONG
        
        changes_rev = dict(base_negative_drivers)
        changes_rev["STEEL_FUTURE"] = -0.50
        res_rev = detector.detect(changes_rev)
        res_rev_f = {
            "targets": {"STEEL_FUTURE": res_rev["targets"]["STEEL_FUTURE"]},
            "summary": res_rev["summary"]
        }
        t4 = t3 + timedelta(hours=1)
        tracker_s5.process(res_rev_f, t4) # Closes LONG as DIRECTION_REVERSED, opens SHORT
        
        # 3. SIGNAL_DECAYED
        tracker_s5_decay = SteelInefficiencyEpisodeTracker()
        tracker_s5_decay.process(res_s1_f, t3) # Opens LONG
        
        changes_decay = {
            "IRON_ORE": 0.1,
            "COKING_COAL": 0.1,
            "SCRAP_STEEL": 0.1,
            "BALTIC_DRY": 0.1,
            "CRUDE_OIL": 0.1,
            "USDINR": 0.1,
            "NIFTY_METAL": 0.1,
            "TATASTEEL": 0.1,
            "JSWSTEEL": 0.1,
            "STEEL_FUTURE": 1.0
        }
        res_decay = detector.detect(changes_decay)
        res_decay_f = {
            "targets": {"STEEL_FUTURE": res_decay["targets"]["STEEL_FUTURE"]},
            "summary": res_decay["summary"]
        }
        tracker_s5_decay.process(res_decay_f, t4) # Closes LONG as SIGNAL_DECAYED
        
        # 4. EXPIRED
        tracker_s5_expire = SteelInefficiencyEpisodeTracker(max_episode_age_seconds=1800)
        tracker_s5_expire.process(res_s1_f, t3) # Opens LONG
        t5_expire = t3 + timedelta(hours=1) # 3600 seconds > 1800 seconds
        tracker_s5_expire.process(res_s1_f, t5_expire) # Closes LONG as EXPIRED
        
        # 5. MANUALLY_CLOSED
        tracker_s5_manual = SteelInefficiencyEpisodeTracker()
        tracker_s5_manual.process(res_s1_f, t3) # Opens LONG
        tracker_s5_manual.manually_close("STEEL_FUTURE", t4) # Closes LONG as MANUALLY_CLOSED
        
        # Collect and write all closed
        all_closed = []
        all_closed.extend(tracker_s5.closed_episodes())
        all_closed.extend(tracker_s5_decay.closed_episodes())
        all_closed.extend(tracker_s5_expire.closed_episodes())
        all_closed.extend(tracker_s5_manual.closed_episodes())
        
        # Check that we have all 5 outcomes
        outcomes_seen = [ep.outcome for ep in all_closed]
        print(f"Outcomes to write: {outcomes_seen}")
        for ep in all_closed:
            writer_s5.write_episode(ep)
            
        counts = reader_s5.closed_outcome_counts()
        print(f"Reader outcome counts: {counts}")
        assert counts["CONVERGED"] == 1
        assert counts["DIRECTION_REVERSED"] == 1
        assert counts["SIGNAL_DECAYED"] == 1
        assert counts["EXPIRED"] == 1
        assert counts["MANUALLY_CLOSED"] == 1

        # -------------------------------------------------------------------------
        # SCENARIO 6 — Reader summary
        # -------------------------------------------------------------------------
        print("\nScenario 6: Reader summary")
        summary = reader_s5.summary()
        print(f"Reader summary: {json.dumps(summary, indent=2)}")
        
        assert summary["record_count"] == 5
        assert summary["unique_episode_count"] == 5
        assert summary["duplicate_episode_id_count"] == 0
        assert summary["targets"]["STEEL_FUTURE"] == 5
        assert summary["directions"]["LONG_TARGET"] == 5
        assert summary["outcomes"]["CONVERGED"] == 1
        assert summary["outcomes"]["EXPIRED"] == 1
        assert summary["average_duration_seconds"] > 0
        assert summary["average_max_favorable_excursion"] >= 0
        assert summary["average_max_adverse_excursion"] >= 0
        assert summary["average_update_count"] > 0

        # -------------------------------------------------------------------------
        # SCENARIO 7 — Complete learning metadata
        # -------------------------------------------------------------------------
        print("\nScenario 7: Complete learning metadata")
        records_s7 = reader_s5.read_all()
        first_record = records_s7[0]
        
        assert "schema_version" in first_record
        assert "record_type" in first_record
        assert "episode" in first_record
        
        ep_dict = first_record["episode"]
        assert "schema_version" in ep_dict
        assert "episode_type" in ep_dict
        assert "observations" in ep_dict
        assert isinstance(ep_dict["observations"], list)
        
        first_obs = ep_dict["observations"][0]
        assert "raw_pressure_score" in first_obs
        assert "expected_change_basis" in first_obs
        assert "is_historically_calibrated" in first_obs
        assert "total_possible_weight" in first_obs
        assert "observed_weight" in first_obs
        assert "contributors" in first_obs
        assert "explanation" in first_obs
        
        assert isinstance(first_obs["contributors"], list)

        # -------------------------------------------------------------------------
        # SCENARIO 8 — Datetime serialization
        # -------------------------------------------------------------------------
        print("\nScenario 8: Datetime serialization")
        def assert_no_datetimes(val):
            if isinstance(val, dict):
                for k, v in val.items():
                    assert not isinstance(k, datetime)
                    assert_no_datetimes(v)
            elif isinstance(val, list):
                for item in val:
                    assert_no_datetimes(item)
            else:
                assert not isinstance(val, datetime)
                
        assert_no_datetimes(first_record)
        print("Verified that recursively no datetime objects remain in serialized output.")

        # -------------------------------------------------------------------------
        # SCENARIO 9 — Input immutability
        # -------------------------------------------------------------------------
        print("\nScenario 9: Input immutability")
        ep_s9 = tracker_s5.closed_episodes()[0]
        ep_dict_s9 = ep_s9.to_dict()
        ep_dict_s9_copy = copy.deepcopy(ep_dict_s9)
        
        snap_s9 = tracker_s5.snapshot()
        snap_s9_copy = copy.deepcopy(snap_s9)
        
        det_res_s9 = copy.deepcopy(res_s1)
        det_res_s9_copy = copy.deepcopy(det_res_s9)
        
        # Perform writes
        writer_s5.write_episode(ep_s9)
        
        # Verify no mutations
        assert ep_s9.to_dict() == ep_dict_s9_copy, "Episode mutated during write"
        assert tracker_s5.snapshot() == snap_s9_copy, "Tracker mutated during write"
        assert res_s1 == det_res_s9_copy, "Detector result mutated during write"
        print("Verified input immutability.")

        # -------------------------------------------------------------------------
        # SCENARIO 10 — Malformed JSONL strict mode
        # -------------------------------------------------------------------------
        print("\nScenario 10: Malformed JSONL strict mode")
        tmp_path_malformed = pathlib.Path(tmpdir) / "malformed.jsonl"
        with open(tmp_path_malformed, "w", encoding="utf-8") as f:
            f.write(json.dumps(first_record) + "\n")
            f.write("{\n") # Malformed line
            
        reader_malformed = SteelEpisodeDatasetReader(dataset_path=str(tmp_path_malformed))
        try:
            reader_malformed.read_all(strict=True)
            assert False, "Malformed JSON did not raise ValueError in strict mode"
        except ValueError as e:
            assert "line 2" in str(e) or "Line 2" in str(e) or "line" in str(e).lower(), f"Error message missing line details: {e}"
            print(f"Correctly raised ValueError with details: {e}")

        # -------------------------------------------------------------------------
        # SCENARIO 11 — Malformed JSONL non-strict mode
        # -------------------------------------------------------------------------
        print("\nScenario 11: Malformed JSONL non-strict mode")
        records_non_strict = reader_malformed.read_all(strict=False)
        assert len(records_non_strict) == 1
        assert records_non_strict[0]["episode"]["target"] == "STEEL_FUTURE"
        print("Malformed line skipped successfully in non-strict mode.")

        # -------------------------------------------------------------------------
        # SCENARIO 12 — Empty dataset
        # -------------------------------------------------------------------------
        print("\nScenario 12: Empty dataset")
        tmp_path_empty = pathlib.Path(tmpdir) / "nonexistent.jsonl"
        reader_empty = SteelEpisodeDatasetReader(dataset_path=str(tmp_path_empty))
        
        summary_empty = reader_empty.summary()
        assert summary_empty["record_count"] == 0
        assert summary_empty["unique_episode_count"] == 0
        assert summary_empty["average_convergence_time_seconds"] is None
        print("Empty dataset summary handled safely.")

        # -------------------------------------------------------------------------
        # SCENARIO 13 — Contributor validation
        # -------------------------------------------------------------------------
        print("\nScenario 13: Contributor validation")
        target_res_base = copy.deepcopy(res_s1_f["targets"]["STEEL_FUTURE"])
        
        # 13.1 bool numeric field
        try:
            bad_res = copy.deepcopy(target_res_base)
            bad_res["contributors"] = [{
                "source": "IRON_ORE",
                "change": True,
                "weight": 0.2,
                "relationship_direction": "positive",
                "direction_multiplier": 1.0,
                "contribution": 0.2
            }]
            SteelInefficiencyEpisode.from_detection(bad_res, t1)
            assert False, "Boolean contributor field not rejected"
        except TypeError:
            pass

        # 13.2 NaN numeric field
        try:
            bad_res = copy.deepcopy(target_res_base)
            bad_res["contributors"] = [{
                "source": "IRON_ORE",
                "change": float("nan"),
                "weight": 0.2,
                "relationship_direction": "positive",
                "direction_multiplier": 1.0,
                "contribution": 0.2
            }]
            SteelInefficiencyEpisode.from_detection(bad_res, t1)
            assert False, "NaN contributor field not rejected"
        except ValueError:
            pass

        # 13.3 positive infinity
        try:
            bad_res = copy.deepcopy(target_res_base)
            bad_res["contributors"] = [{
                "source": "IRON_ORE",
                "change": float("inf"),
                "weight": 0.2,
                "relationship_direction": "positive",
                "direction_multiplier": 1.0,
                "contribution": 0.2
            }]
            SteelInefficiencyEpisode.from_detection(bad_res, t1)
            assert False, "+inf contributor field not rejected"
        except ValueError:
            pass

        # 13.4 negative infinity
        try:
            bad_res = copy.deepcopy(target_res_base)
            bad_res["contributors"] = [{
                "source": "IRON_ORE",
                "change": float("-inf"),
                "weight": 0.2,
                "relationship_direction": "positive",
                "direction_multiplier": 1.0,
                "contribution": 0.2
            }]
            SteelInefficiencyEpisode.from_detection(bad_res, t1)
            assert False, "-inf contributor field not rejected"
        except ValueError:
            pass

        # 13.5 string in numeric field
        try:
            bad_res = copy.deepcopy(target_res_base)
            bad_res["contributors"] = [{
                "source": "IRON_ORE",
                "change": "1.0",
                "weight": 0.2,
                "relationship_direction": "positive",
                "direction_multiplier": 1.0,
                "contribution": 0.2
            }]
            SteelInefficiencyEpisode.from_detection(bad_res, t1)
            assert False, "String contributor field not rejected"
        except TypeError:
            pass
        print("Contributor validation rules verified successfully.")

        # -------------------------------------------------------------------------
        # SCENARIO 14 — Real immutability regression
        # -------------------------------------------------------------------------
        print("\nScenario 14: Real immutability regression")
        
        target_res_input = copy.deepcopy(res_s1_f["targets"]["STEEL_FUTURE"])
        target_res_input_copy = copy.deepcopy(target_res_input)
        
        # Test from_detection()
        test_ep_s14 = SteelInefficiencyEpisode.from_detection(target_res_input, t1)
        assert target_res_input == target_res_input_copy, "from_detection mutated target_result"
        
        # Test update()
        target_res_input2 = copy.deepcopy(res_s2_f["targets"]["STEEL_FUTURE"])
        target_res_input2_copy = copy.deepcopy(target_res_input2)
        test_ep_s14.update(target_res_input2, t2)
        assert target_res_input2 == target_res_input2_copy, "update mutated target_result"
        
        # Test write_episode()
        # First close the episode
        test_ep_s14.close("CONVERGED", t2)
        test_ep_s14_dict = test_ep_s14.to_dict()
        test_ep_s14_dict_copy = copy.deepcopy(test_ep_s14_dict)
        writer.write_episode(test_ep_s14)
        assert test_ep_s14.to_dict() == test_ep_s14_dict_copy, "write_episode mutated episode"
        
        print("Verified that original source dictionaries remain identical after every call.")

        # -------------------------------------------------------------------------
        # SCENARIO 15 — Dataset and contributor validation hardening
        # -------------------------------------------------------------------------
        print("\nScenario 15: Dataset and contributor validation hardening")
        
        # 6. Dataset startup rejects duplicate episode IDs
        tmp_dup_path = pathlib.Path(tmpdir) / "startup_duplicate.jsonl"
        with open(tmp_dup_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(first_record) + "\n")
            f.write(json.dumps(first_record) + "\n")
        try:
            SteelEpisodeDatasetWriter(dataset_path=str(tmp_dup_path))
            assert False, "Duplicate episode ID did not raise ValueError during startup scan"
        except ValueError as e:
            assert "Duplicate episode ID" in str(e)
            print("Verified: Duplicate episode ID on startup scan correctly rejected.")

        # 7. Dataset startup rejects an active episode record
        tmp_active_path = pathlib.Path(tmpdir) / "startup_active.jsonl"
        active_record = copy.deepcopy(first_record)
        active_record["episode"]["is_open"] = True
        with open(tmp_active_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(active_record) + "\n")
        try:
            SteelEpisodeDatasetWriter(dataset_path=str(tmp_active_path))
            assert False, "Active episode did not raise ValueError during startup scan"
        except ValueError as e:
            assert "is_open must be False" in str(e)
            print("Verified: Active episode on startup scan correctly rejected.")

        # 8. Dataset startup rejects outcome OPEN
        tmp_open_outcome_path = pathlib.Path(tmpdir) / "startup_open_outcome.jsonl"
        open_outcome_record = copy.deepcopy(first_record)
        open_outcome_record["episode"]["outcome"] = "OPEN"
        with open(tmp_open_outcome_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(open_outcome_record) + "\n")
        try:
            SteelEpisodeDatasetWriter(dataset_path=str(tmp_open_outcome_path))
            assert False, "Outcome OPEN did not raise ValueError during startup scan"
        except ValueError as e:
            assert "outcome must be one of" in str(e)
            print("Verified: Outcome OPEN on startup scan correctly rejected.")

        # 9. Dataset startup rejects unsupported schema version
        tmp_schema_path = pathlib.Path(tmpdir) / "startup_schema.jsonl"
        bad_schema_record = copy.deepcopy(first_record)
        bad_schema_record["schema_version"] = "2.0"
        with open(tmp_schema_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(bad_schema_record) + "\n")
        try:
            SteelEpisodeDatasetWriter(dataset_path=str(tmp_schema_path))
            assert False, "Unsupported schema version did not raise ValueError during startup scan"
        except ValueError as e:
            assert "schema_version" in str(e)
            print("Verified: Unsupported schema version correctly rejected.")

        # 10. Dataset startup rejects incorrect record_type
        tmp_type_path = pathlib.Path(tmpdir) / "startup_type.jsonl"
        bad_type_record = copy.deepcopy(first_record)
        bad_type_record["record_type"] = "bad_record_type"
        with open(tmp_type_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(bad_type_record) + "\n")
        try:
            SteelEpisodeDatasetWriter(dataset_path=str(tmp_type_path))
            assert False, "Incorrect record_type did not raise ValueError during startup scan"
        except ValueError as e:
            assert "record_type" in str(e)
            print("Verified: Incorrect record_type correctly rejected.")

        # 11. Writer uses real isinstance tracker validation
        class SpoofedTracker:
            pass
        
        spoof = SpoofedTracker()
        try:
            writer.write_new_closed_episodes(spoof)
            assert False, "Spoofed tracker was not rejected"
        except TypeError as e:
            assert "tracker must be a SteelInefficiencyEpisodeTracker" in str(e)
            print("Verified: Spoofed tracker correctly rejected with TypeError.")

        # 12. episode_ids() is sorted
        tmp_sort_path = pathlib.Path(tmpdir) / "test_sort.jsonl"
        writer_sort = SteelEpisodeDatasetWriter(dataset_path=str(tmp_sort_path))
        
        ep_z = copy.deepcopy(test_ep_s14)
        ep_z.episode_id = "z_episode_id"
        ep_a = copy.deepcopy(test_ep_s14)
        ep_a.episode_id = "a_episode_id"
        
        writer_sort.write_episode(ep_z)
        writer_sort.write_episode(ep_a)
        
        sorted_ids = writer_sort.episode_ids()
        assert sorted_ids == ["a_episode_id", "z_episode_id"]
        print("Verified: episode_ids() is sorted alphabetically.")

        # 13. Contributor source validation
        try:
            bad_res = copy.deepcopy(target_res_base)
            bad_res["contributors"] = [{
                "change": 1.0,
                "weight": 0.2,
                "relationship_direction": "positive",
                "direction_multiplier": 1.0,
                "contribution": 0.2
            }]
            SteelInefficiencyEpisode.from_detection(bad_res, t1)
            assert False, "Missing source key did not raise KeyError"
        except KeyError:
            pass
            
        try:
            bad_res = copy.deepcopy(target_res_base)
            bad_res["contributors"] = [{
                "source": "",
                "change": 1.0,
                "weight": 0.2,
                "relationship_direction": "positive",
                "direction_multiplier": 1.0,
                "contribution": 0.2
            }]
            SteelInefficiencyEpisode.from_detection(bad_res, t1)
            assert False, "Empty source did not raise ValueError"
        except ValueError as e:
            assert "source" in str(e)
            pass
        print("Verified: Contributor source validation behaves correctly.")

        # 14. Contributor relationship-direction validation
        try:
            bad_res = copy.deepcopy(target_res_base)
            bad_res["contributors"] = [{
                "source": "IRON_ORE",
                "change": 1.0,
                "weight": 0.2,
                "direction_multiplier": 1.0,
                "contribution": 0.2
            }]
            SteelInefficiencyEpisode.from_detection(bad_res, t1)
            assert False, "Missing relationship_direction key did not raise KeyError"
        except KeyError:
            pass
            
        try:
            bad_res = copy.deepcopy(target_res_base)
            bad_res["contributors"] = [{
                "source": "IRON_ORE",
                "change": 1.0,
                "weight": 0.2,
                "relationship_direction": "neutral",
                "direction_multiplier": 1.0,
                "contribution": 0.2
            }]
            SteelInefficiencyEpisode.from_detection(bad_res, t1)
            assert False, "Invalid relationship_direction did not raise ValueError"
        except ValueError as e:
            assert "relationship_direction" in str(e)
            pass
        print("Verified: Contributor relationship_direction validation behaves correctly.")

        # 15. json.dumps rejects NaN using allow_nan=False
        nan_ep = copy.deepcopy(test_ep_s14)
        nan_ep.episode_id = "new_unique_nan_episode_id"
        nan_ep.opening_expected_change = float("nan")
        try:
            writer.write_episode(nan_ep)
            assert False, "allow_nan=False did not raise ValueError when serializing NaN"
        except ValueError as e:
            print(f"Verified: json.dumps rejects NaN with allow_nan=False: {e}")

        # 16. record_count remains correct after writer restart
        writer_restart_test = SteelEpisodeDatasetWriter(dataset_path=str(tmp_sort_path))
        assert writer_restart_test.record_count() == 2
        print("Verified: record_count remains correct after writer restart.")

    print("\nAll steel tracker and dataset integrity assertions passed.")

if __name__ == "__main__":
    main()
