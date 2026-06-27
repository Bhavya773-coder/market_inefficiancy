import json
import math
import copy
from datetime import datetime, timezone, timedelta
from ai.steel_inefficiency_detector import SteelInefficiencyDetector
from ai.steel_inefficiency_episode import SteelInefficiencyEpisode
from ai.steel_inefficiency_episode_tracker import SteelInefficiencyEpisodeTracker

def main():
    print("Starting comprehensive offline tests for SteelInefficiencyEpisode and Tracker...")

    # Base positive/negative drivers
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
    tracker = SteelInefficiencyEpisodeTracker()

    # -------------------------------------------------------------------------
    # SCENARIO 1 — Open bullish episode
    # -------------------------------------------------------------------------
    print("\nScenario 1: Open bullish episode")
    changes_s1 = dict(base_positive_drivers)
    changes_s1["STEEL_FUTURE"] = 0.50
    changes_s1["STEEL_PHYSICAL_PLATE"] = 0.50
    
    t1 = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    res_s1 = detector.detect(changes_s1)
    
    proc_res1 = tracker.process(res_s1, t1)
    assert len(proc_res1["opened"]) == 2, f"Expected 2 episodes opened (STEEL_FUTURE & STEEL_PHYSICAL_PLATE), got {len(proc_res1['opened'])}"
    
    active_future = tracker.active_for("STEEL_FUTURE")
    assert active_future is not None, "STEEL_FUTURE episode was not opened"
    assert active_future.target == "STEEL_FUTURE"
    assert active_future.recommended_direction == "LONG_TARGET"
    assert active_future.outcome == "OPEN"
    assert active_future.is_open is True
    assert active_future.update_count == 1
    assert tracker.snapshot()["summary"]["active_count"] >= 1

    # -------------------------------------------------------------------------
    # SCENARIO 2 — Favourable long update
    # -------------------------------------------------------------------------
    print("\nScenario 2: Favourable long update")
    changes_s2 = dict(base_positive_drivers)
    changes_s2["STEEL_FUTURE"] = 1.20
    changes_s2["STEEL_PHYSICAL_PLATE"] = 0.50
    
    t2 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    res_s2 = detector.detect(changes_s2)
    
    proc_res2 = tracker.process(res_s2, t2)
    assert len(proc_res2["opened"]) == 0
    assert len(proc_res2["updated"]) == 2
    
    active_future = tracker.active_for("STEEL_FUTURE")
    assert active_future.update_count == 2
    assert active_future.max_favorable_excursion > 0
    assert active_future.max_adverse_excursion == 0.0

    # -------------------------------------------------------------------------
    # SCENARIO 3 — Adverse long update
    # -------------------------------------------------------------------------
    print("\nScenario 3: Adverse long update")
    changes_s3 = dict(base_positive_drivers)
    changes_s3["STEEL_FUTURE"] = 0.10
    changes_s3["STEEL_PHYSICAL_PLATE"] = 0.50
    
    t3 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    res_s3 = detector.detect(changes_s3)
    
    # Store previous fav excursion to verify it is retained
    prev_fav = active_future.max_favorable_excursion
    
    proc_res3 = tracker.process(res_s3, t3)
    assert active_future.is_open is True
    assert active_future.max_adverse_excursion > 0
    assert active_future.max_favorable_excursion == prev_fav
    assert active_future.update_count == 3

    # -------------------------------------------------------------------------
    # SCENARIO 4 — Convergence
    # -------------------------------------------------------------------------
    print("\nScenario 4: Convergence")
    # Derive the expected change
    expected_future = res_s3["targets"]["STEEL_FUTURE"]["expected_change"]
    expected_plate = res_s3["targets"]["STEEL_PHYSICAL_PLATE"]["expected_change"]
    
    changes_s4 = dict(base_positive_drivers)
    changes_s4["STEEL_FUTURE"] = expected_future
    changes_s4["STEEL_PHYSICAL_PLATE"] = expected_plate
    
    t4 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    res_s4 = detector.detect(changes_s4)
    
    proc_res4 = tracker.process(res_s4, t4)
    assert len(proc_res4["closed"]) >= 1
    
    # Check that it is no longer active and outcome is CONVERGED
    closed_future = next((ep for ep in tracker.closed_episodes() if ep.target == "STEEL_FUTURE"), None)
    assert closed_future is not None, "STEEL_FUTURE was not closed"
    assert tracker.active_for("STEEL_FUTURE") is None
    assert closed_future.outcome == "CONVERGED"
    assert closed_future.is_open is False
    assert closed_future.convergence_time_seconds == 10800.0, f"Expected 10800.0, got {closed_future.convergence_time_seconds}"

    # -------------------------------------------------------------------------
    # SCENARIO 5 — Short episode
    # -------------------------------------------------------------------------
    print("\nScenario 5: Short episode")
    changes_s5_open = dict(base_negative_drivers)
    changes_s5_open["STEEL_FUTURE"] = -0.50
    changes_s5_open["STEEL_PHYSICAL_PLATE"] = -0.50
    
    t5_open = datetime(2026, 1, 2, 9, 0, 0, tzinfo=timezone.utc)
    res_s5_open = detector.detect(changes_s5_open)
    
    tracker_s5 = SteelInefficiencyEpisodeTracker()
    proc_s5_open = tracker_s5.process(res_s5_open, t5_open)
    
    active_short = tracker_s5.active_for("STEEL_FUTURE")
    assert active_short is not None
    assert active_short.recommended_direction == "SHORT_TARGET"
    
    # Favourable update
    changes_s5_fav = dict(base_negative_drivers)
    changes_s5_fav["STEEL_FUTURE"] = -1.20
    changes_s5_fav["STEEL_PHYSICAL_PLATE"] = -0.50
    t5_fav = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    res_s5_fav = detector.detect(changes_s5_fav)
    tracker_s5.process(res_s5_fav, t5_fav)
    assert active_short.max_favorable_excursion > 0
    assert active_short.max_adverse_excursion == 0.0
    
    # Adverse update
    changes_s5_adv = dict(base_negative_drivers)
    changes_s5_adv["STEEL_FUTURE"] = -0.10
    changes_s5_adv["STEEL_PHYSICAL_PLATE"] = -0.50
    t5_adv = datetime(2026, 1, 2, 11, 0, 0, tzinfo=timezone.utc)
    res_s5_adv = detector.detect(changes_s5_adv)
    tracker_s5.process(res_s5_adv, t5_adv)
    assert active_short.max_adverse_excursion > 0

    # -------------------------------------------------------------------------
    # SCENARIO 6 — Direction reversal
    # -------------------------------------------------------------------------
    print("\nScenario 6: Direction reversal")
    tracker_s6 = SteelInefficiencyEpisodeTracker()
    
    # 1. Open LONG episode
    changes_s6_long = dict(base_positive_drivers)
    changes_s6_long["STEEL_FUTURE"] = 0.50
    changes_s6_long["STEEL_PHYSICAL_PLATE"] = 0.50
    t6_long = datetime(2026, 1, 3, 9, 0, 0, tzinfo=timezone.utc)
    res_s6_long = detector.detect(changes_s6_long)
    tracker_s6.process(res_s6_long, t6_long)
    
    ep_long = tracker_s6.active_for("STEEL_FUTURE")
    assert ep_long is not None
    assert ep_long.recommended_direction == "LONG_TARGET"
    
    # 2. Provide negative drivers triggering SHORT
    changes_s6_short = dict(base_negative_drivers)
    changes_s6_short["STEEL_FUTURE"] = -0.50
    changes_s6_short["STEEL_PHYSICAL_PLATE"] = -0.50
    t6_short = datetime(2026, 1, 3, 10, 0, 0, tzinfo=timezone.utc)
    res_s6_short = detector.detect(changes_s6_short)
    
    proc_s6_rev = tracker_s6.process(res_s6_short, t6_short)
    
    # Verify old is closed with DIRECTION_REVERSED and new is active
    assert len(proc_s6_rev["closed"]) >= 1
    assert len(proc_s6_rev["opened"]) >= 1
    
    closed_ep = next((ep for ep in tracker_s6.closed_episodes() if ep.target == "STEEL_FUTURE"), None)
    assert closed_ep is not None, "STEEL_FUTURE was not closed"
    assert closed_ep.outcome == "DIRECTION_REVERSED"
    
    active_ep = tracker_s6.active_for("STEEL_FUTURE")
    assert active_ep is not None
    assert active_ep.recommended_direction == "SHORT_TARGET"
    assert active_ep.episode_id != closed_ep.episode_id

    # -------------------------------------------------------------------------
    # SCENARIO 7 — Low coverage does not close
    # -------------------------------------------------------------------------
    print("\nScenario 7: Low coverage does not close")
    tracker_s7 = SteelInefficiencyEpisodeTracker(convergence_gap_threshold=0.35)
    
    # Open episode
    changes_s7_open = dict(base_positive_drivers)
    changes_s7_open["STEEL_FUTURE"] = 0.50
    changes_s7_open["STEEL_PHYSICAL_PLATE"] = 0.50
    t7_open = datetime(2026, 1, 4, 9, 0, 0, tzinfo=timezone.utc)
    res_s7_open = detector.detect(changes_s7_open)
    tracker_s7.process(res_s7_open, t7_open)
    
    active_ep_s7 = tracker_s7.active_for("STEEL_FUTURE")
    assert active_ep_s7 is not None
    
    # Low coverage update (only IRON_ORE and target)
    changes_s7_low_cov = {
        "IRON_ORE": 5.0,
        "STEEL_FUTURE": 0.50,
        "STEEL_PHYSICAL_PLATE": 0.50
    }
    t7_low = datetime(2026, 1, 4, 10, 0, 0, tzinfo=timezone.utc)
    
    # To trigger low coverage on STEEL_FUTURE (possible weight 0.65, observed 0.20 -> 0.307 coverage ratio)
    custom_detector = SteelInefficiencyDetector(min_coverage_ratio=0.80)
    res_s7_low = custom_detector.detect(changes_s7_low_cov)
    
    tracker_s7.process(res_s7_low, t7_low)
    
    # Verify it is still active and uncertain_update_count incremented
    assert tracker_s7.active_for("STEEL_FUTURE") is not None
    assert active_ep_s7.is_open is True
    assert active_ep_s7.uncertain_update_count == 1

    # -------------------------------------------------------------------------
    # SCENARIO 8 — Signal decay
    # -------------------------------------------------------------------------
    print("\nScenario 8: Signal decay")
    tracker_s8 = SteelInefficiencyEpisodeTracker()
    
    # Open episode
    changes_s8_open = dict(base_positive_drivers)
    changes_s8_open["STEEL_FUTURE"] = 0.50
    changes_s8_open["STEEL_PHYSICAL_PLATE"] = 0.50
    t8_open = datetime(2026, 1, 5, 9, 0, 0, tzinfo=timezone.utc)
    res_s8_open = detector.detect(changes_s8_open)
    tracker_s8.process(res_s8_open, t8_open)
    
    active_ep_s8 = tracker_s8.active_for("STEEL_FUTURE")
    assert active_ep_s8 is not None
    
    # Small driver changes so detector returns LOW_PRESSURE
    # Expected change must be < min_expected_move (0.50)
    changes_s8_decay = {
        "IRON_ORE": 0.1,
        "COKING_COAL": 0.1,
        "SCRAP_STEEL": 0.1,
        "BALTIC_DRY": 0.1,
        "CRUDE_OIL": 0.1,
        "USDINR": 0.1,
        "NIFTY_METAL": 0.1,
        "TATASTEEL": 0.1,
        "JSWSTEEL": 0.1,
        "STEEL_FUTURE": 1.0,
        "STEEL_PHYSICAL_PLATE": 1.0
    }
    t8_decay = datetime(2026, 1, 5, 10, 0, 0, tzinfo=timezone.utc)
    res_s8_decay = detector.detect(changes_s8_decay)
    tracker_s8.process(res_s8_decay, t8_decay)
    
    assert tracker_s8.active_for("STEEL_FUTURE") is None
    closed_ep_s8 = next((ep for ep in tracker_s8.closed_episodes() if ep.target == "STEEL_FUTURE"), None)
    assert closed_ep_s8 is not None, "STEEL_FUTURE was not closed"
    assert closed_ep_s8.outcome == "SIGNAL_DECAYED"

    # -------------------------------------------------------------------------
    # SCENARIO 9 — Expiry
    # -------------------------------------------------------------------------
    print("\nScenario 9: Expiry")
    tracker_s9 = SteelInefficiencyEpisodeTracker(max_episode_age_seconds=7200)
    
    changes_s9 = dict(base_positive_drivers)
    changes_s9["STEEL_FUTURE"] = 0.50
    changes_s9["STEEL_PHYSICAL_PLATE"] = 0.50
    t9_open = datetime(2026, 1, 6, 9, 0, 0, tzinfo=timezone.utc)
    res_s9_open = detector.detect(changes_s9)
    tracker_s9.process(res_s9_open, t9_open)
    
    active_ep_s9 = tracker_s9.active_for("STEEL_FUTURE")
    assert active_ep_s9 is not None
    
    # Update at 11:00 UTC (duration 7200 seconds)
    t9_expire = datetime(2026, 1, 6, 11, 0, 0, tzinfo=timezone.utc)
    tracker_s9.process(res_s9_open, t9_expire)
    
    assert tracker_s9.active_for("STEEL_FUTURE") is None
    closed_ep_s9 = next((ep for ep in tracker_s9.closed_episodes() if ep.target == "STEEL_FUTURE"), None)
    assert closed_ep_s9 is not None, "STEEL_FUTURE was not closed"
    assert closed_ep_s9.outcome == "EXPIRED"
    assert closed_ep_s9.is_open is False

    # -------------------------------------------------------------------------
    # SCENARIO 10 — Manual close
    # -------------------------------------------------------------------------
    print("\nScenario 10: Manual close")
    tracker_s10 = SteelInefficiencyEpisodeTracker()
    t10_open = datetime(2026, 1, 7, 9, 0, 0, tzinfo=timezone.utc)
    tracker_s10.process(res_s1, t10_open)
    
    assert tracker_s10.active_for("STEEL_FUTURE") is not None
    t10_close = datetime(2026, 1, 7, 10, 0, 0, tzinfo=timezone.utc)
    tracker_s10.manually_close("STEEL_FUTURE", t10_close)
    
    assert tracker_s10.active_for("STEEL_FUTURE") is None
    closed_ep_s10 = next((ep for ep in tracker_s10.closed_episodes() if ep.target == "STEEL_FUTURE"), None)
    assert closed_ep_s10 is not None
    assert closed_ep_s10.outcome == "MANUALLY_CLOSED"

    # -------------------------------------------------------------------------
    # SCENARIO 11 — Serialization
    # -------------------------------------------------------------------------
    print("\nScenario 11: Serialization")
    episode = SteelInefficiencyEpisode.from_detection(
        res_s1["targets"]["STEEL_FUTURE"], t1
    )
    serialized = episode.to_dict()
    
    assert isinstance(serialized["opened_at"], str)
    assert isinstance(serialized["observations"], list)
    assert isinstance(serialized["opening_expected_change"], float)
    
    # Check that no datetime objects are inside the dict (neither keys nor values)
    # Check observations
    for obs in serialized["observations"]:
        assert isinstance(obs["observed_at"], str)
        for k, v in obs.items():
            assert not isinstance(v, datetime)
            
    for k, v in serialized.items():
        assert not isinstance(v, datetime)
    print("Serialization successfully verified without datetime objects.")

    # -------------------------------------------------------------------------
    # SCENARIO 12 — Input immutability
    # -------------------------------------------------------------------------
    print("\nScenario 12: Input immutability")
    target_res_copy_s1 = copy.deepcopy(res_s1["targets"]["STEEL_FUTURE"])
    test_ep = SteelInefficiencyEpisode.from_detection(res_s1["targets"]["STEEL_FUTURE"], t1)
    assert res_s1["targets"]["STEEL_FUTURE"] == target_res_copy_s1, "from_detection() mutated target_result"
    
    target_res_copy_s2 = copy.deepcopy(res_s2["targets"]["STEEL_FUTURE"])
    test_ep.update(res_s2["targets"]["STEEL_FUTURE"], t2)
    assert res_s2["targets"]["STEEL_FUTURE"] == target_res_copy_s2, "update() mutated target_result"
    
    det_res_copy = copy.deepcopy(res_s1)
    test_tracker = SteelInefficiencyEpisodeTracker()
    test_tracker.process(res_s1, t1)
    assert res_s1 == det_res_copy, "process() mutated detection_result"
    print("Inputs verified as fully immutable.")

    # -------------------------------------------------------------------------
    # SCENARIO 13 — Validation
    # -------------------------------------------------------------------------
    print("\nScenario 13: Validation")
    
    # non-dictionary detection result
    try:
        tracker.process("bad_input", t1)
        assert False, "Non-dictionary was not rejected"
    except TypeError:
        pass
        
    # missing targets key
    try:
        tracker.process({}, t1)
        assert False, "Missing targets key was not rejected"
    except KeyError:
        pass
        
    # naive datetime without timezone
    try:
        naive_dt = datetime(2026, 1, 1, 9, 0, 0)
        tracker.process(res_s1, naive_dt)
        assert False, "Naive datetime was not rejected"
    except ValueError:
        pass
        
    # update earlier than episode opened_at
    try:
        ep_val = SteelInefficiencyEpisode.from_detection(res_s1["targets"]["STEEL_FUTURE"], t1)
        ep_val.update(res_s2["targets"]["STEEL_FUTURE"], t1 - timedelta(hours=1))
        assert False, "Earlier update was not rejected"
    except ValueError:
        pass
        
    # closing already closed episode
    try:
        ep_val = SteelInefficiencyEpisode.from_detection(res_s1["targets"]["STEEL_FUTURE"], t1)
        ep_val.close("CONVERGED", t1 + timedelta(hours=1))
        ep_val.close("EXPIRED", t1 + timedelta(hours=2))
        assert False, "Double close was not rejected"
    except ValueError:
        pass
        
    # creating episode from non-inefficient target
    try:
        # Create a non-inefficient target result (is_inefficient=False)
        changes_efficient = dict(base_positive_drivers)
        changes_efficient["STEEL_FUTURE"] = expected_future
        changes_efficient["STEEL_PHYSICAL_PLATE"] = expected_plate
        res_eff = detector.detect(changes_efficient)
        
        SteelInefficiencyEpisode.from_detection(res_eff["targets"]["STEEL_FUTURE"], t1)
        assert False, "Non-inefficient target did not raise ValueError"
    except ValueError:
        pass
        
    # creating episode with NO_TRADE direction
    try:
        bad_target_res = dict(res_s1["targets"]["STEEL_FUTURE"])
        bad_target_res["recommended_direction"] = "NO_TRADE"
        SteelInefficiencyEpisode.from_detection(bad_target_res, t1)
        assert False, "NO_TRADE direction did not raise ValueError"
    except ValueError:
        pass
        
    # NaN numeric field
    try:
        bad_target_res = dict(res_s1["targets"]["STEEL_FUTURE"])
        bad_target_res["expected_change"] = float("nan")
        SteelInefficiencyEpisode.from_detection(bad_target_res, t1)
        assert False, "NaN did not raise ValueError"
    except ValueError:
        pass
        
    # infinite numeric field
    try:
        bad_target_res = dict(res_s1["targets"]["STEEL_FUTURE"])
        bad_target_res["expected_change"] = float("inf")
        SteelInefficiencyEpisode.from_detection(bad_target_res, t1)
        assert False, "Infinity did not raise ValueError"
    except ValueError:
        pass
        
    # bool numeric field
    try:
        bad_target_res = dict(res_s1["targets"]["STEEL_FUTURE"])
        bad_target_res["expected_change"] = True
        SteelInefficiencyEpisode.from_detection(bad_target_res, t1)
        assert False, "Boolean did not raise TypeError"
    except TypeError:
        pass
        
    print("All validation errors correctly handled.")

    # -------------------------------------------------------------------------
    # SCENARIO 14 — Snapshot summary
    # -------------------------------------------------------------------------
    print("\nScenario 14: Snapshot summary")
    tracker_snap = SteelInefficiencyEpisodeTracker(max_episode_age_seconds=1800)
    
    # Helpers to filter results to just STEEL_FUTURE
    def filter_future(res):
        c = copy.deepcopy(res)
        c["targets"] = {"STEEL_FUTURE": res["targets"]["STEEL_FUTURE"]}
        return c

    res_s1_f = filter_future(res_s1)
    res_s6_short_f = filter_future(res_s6_short)
    res_s4_f = filter_future(res_s4)
    res_s8_decay_f = filter_future(res_s8_decay)

    # 1. Open active STEEL_FUTURE (LONG) at 09:00 UTC
    t_snap_1 = datetime(2026, 1, 8, 9, 0, 0, tzinfo=timezone.utc)
    tracker_snap.process(res_s1_f, t_snap_1)
    
    # 2. Reverse to SHORT at 09:15 UTC (closes LONG with DIRECTION_REVERSED, opens SHORT)
    t_snap_2 = datetime(2026, 1, 8, 9, 15, 0, tzinfo=timezone.utc)
    tracker_snap.process(res_s6_short_f, t_snap_2)
    
    # 3. Expire at 09:45 UTC (closes SHORT with EXPIRED)
    t_snap_3 = datetime(2026, 1, 8, 9, 45, 0, tzinfo=timezone.utc)
    tracker_snap.process(res_s6_short_f, t_snap_3)
    
    # 4. Open LONG at 10:00 UTC
    t_snap_4 = datetime(2026, 1, 8, 10, 0, 0, tzinfo=timezone.utc)
    tracker_snap.process(res_s1_f, t_snap_4)
    
    # 5. Converge at 10:15 UTC (closes LONG with CONVERGED)
    t_snap_5 = datetime(2026, 1, 8, 10, 15, 0, tzinfo=timezone.utc)
    tracker_snap.process(res_s4_f, t_snap_5)
    
    # 6. Open LONG at 11:00 UTC
    t_snap_6 = datetime(2026, 1, 8, 11, 0, 0, tzinfo=timezone.utc)
    tracker_snap.process(res_s1_f, t_snap_6)
    
    # 7. Decay at 11:15 UTC (closes LONG with SIGNAL_DECAYED)
    t_snap_7 = datetime(2026, 1, 8, 11, 15, 0, tzinfo=timezone.utc)
    tracker_snap.process(res_s8_decay_f, t_snap_7)
    
    snap = tracker_snap.snapshot()
    print("Snapshot summary:")
    print(json.dumps(snap["summary"], indent=2))
    
    summary = snap["summary"]
    assert summary["reversed_count"] == 1
    assert summary["expired_count"] == 1
    assert summary["converged_count"] == 1
    assert summary["decayed_count"] == 1
    assert summary["active_count"] == 0
    assert summary["closed_count"] == 4

    # -------------------------------------------------------------------------
    # SCENARIO 15 — Uncertain status and chronology tests
    # -------------------------------------------------------------------------
    print("\nScenario 15: Uncertain status and chronology tests")
    
    t_start = datetime(2026, 1, 9, 9, 0, 0, tzinfo=timezone.utc)
    t_update1 = t_start + timedelta(minutes=5)
    
    tracker_test1 = SteelInefficiencyEpisodeTracker(convergence_gap_threshold=0.35)
    res_open = {
        "targets": {
            "STEEL_FUTURE": {
                "target": "STEEL_FUTURE",
                "recommended_direction": "LONG_TARGET",
                "is_inefficient": True,
                "status": "UNDERREACTION",
                "expected_change": 2.0,
                "actual_change": 0.5,
                "residual_gap": 1.5,
                "absolute_gap": 1.5,
                "inefficiency_score": 1.5,
                "coverage_ratio": 1.0
            }
        },
        "summary": {}
    }
    tracker_test1.process(res_open, t_start)
    active_ep = tracker_test1.active_for("STEEL_FUTURE")
    assert active_ep is not None
    assert active_ep.is_open is True
    
    # 1. LOW_COVERAGE with small absolute gap does not converge, increments uncertain_update_count
    res_low_cov = {
        "targets": {
            "STEEL_FUTURE": {
                "target": "STEEL_FUTURE",
                "recommended_direction": "LONG_TARGET",
                "is_inefficient": True,
                "status": "LOW_COVERAGE",
                "expected_change": 2.0,
                "actual_change": 1.9,
                "residual_gap": 0.1,
                "absolute_gap": 0.1,
                "inefficiency_score": 0.1,
                "coverage_ratio": 0.2
            }
        },
        "summary": {}
    }
    tracker_test1.process(res_low_cov, t_update1)
    
    active_ep2 = tracker_test1.active_for("STEEL_FUTURE")
    assert active_ep2 is not None
    assert active_ep2.is_open is True
    assert active_ep2.uncertain_update_count == 1
    assert len(tracker_test1.closed_episodes()) == 0
    print("LOW_COVERAGE with small absolute gap verified (episode remains open).")
    
    # 2. INSUFFICIENT_DATA does not close
    t_update2 = t_update1 + timedelta(minutes=5)
    res_insuf = {
        "targets": {
            "STEEL_FUTURE": {
                "target": "STEEL_FUTURE",
                "recommended_direction": "LONG_TARGET",
                "is_inefficient": True,
                "status": "INSUFFICIENT_DATA",
                "expected_change": 2.0,
                "actual_change": 1.9,
                "residual_gap": 0.1,
                "absolute_gap": 0.1,
                "inefficiency_score": 0.1,
                "coverage_ratio": 0.0
            }
        },
        "summary": {}
    }
    tracker_test1.process(res_insuf, t_update2)
    
    active_ep3 = tracker_test1.active_for("STEEL_FUTURE")
    assert active_ep3 is not None
    assert active_ep3.is_open is True
    assert active_ep3.uncertain_update_count == 2
    assert len(tracker_test1.closed_episodes()) == 0
    print("INSUFFICIENT_DATA verified (episode remains open).")
    
    # 3. Expiry can still close an episode during uncertain data
    tracker_expire = SteelInefficiencyEpisodeTracker(max_episode_age_seconds=600)
    tracker_expire.process(res_open, t_start)
    t_expire = t_start + timedelta(minutes=12)
    tracker_expire.process(res_low_cov, t_expire)
    
    assert tracker_expire.active_for("STEEL_FUTURE") is None
    closed_list = tracker_expire.closed_episodes()
    assert len(closed_list) == 1
    assert closed_list[0].outcome == "EXPIRED"
    print("Expiry during uncertain data verified.")

    # 4. Manual close updates tracker.last_updated_at
    tracker_manual = SteelInefficiencyEpisodeTracker()
    tracker_manual.process(res_open, t_start)
    assert tracker_manual.last_updated_at == t_start
    
    t_manual_close = t_start + timedelta(minutes=10)
    tracker_manual.manually_close("STEEL_FUTURE", t_manual_close)
    assert tracker_manual.last_updated_at == t_manual_close
    print("Manual close updates tracker.last_updated_at verified.")
    
    # 5. Out-of-order processing after manual close is rejected
    t_out_of_order = t_manual_close - timedelta(minutes=2)
    try:
        tracker_manual.process(res_open, t_out_of_order)
        assert False, "Out-of-order process after manual close was not rejected"
    except ValueError:
        pass
    print("Out-of-order process after manual close rejected verified.")
    
    print("\nAll SteelInefficiencyEpisode and Tracker assertions passed.")

if __name__ == "__main__":
    main()
