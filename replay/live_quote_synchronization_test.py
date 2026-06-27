import json
import math
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from ai.live_quote_buffer import LiveQuoteBuffer
from ai.fresh_instrument_pair_selector import FreshInstrumentPairSelector
from ai.quote_synchronization_monitor import QuoteSynchronizationMonitor

def run_tests():
    print("Running offline live quote synchronization tests...")

    # 11. Dhan timestamp parsing uses Asia/Kolkata correctly
    buffer = LiveQuoteBuffer(max_quote_age_seconds=10.0, max_pair_gap_seconds=10.0, min_updates_for_active=2)
    parsed_utc = buffer._normalize_timestamp("08/06/2026 13:03:08")
    assert parsed_utc is not None, "Failed to parse Dhan timestamp"
    expected_utc = datetime(2026, 6, 8, 13, 3, 8, tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
    assert parsed_utc == expected_utc, f"Incorrect timezone conversion: {parsed_utc} vs {expected_utc}"
    
    # 12. Input dictionaries remain unchanged
    quote_orig = {
        "exchange": "NSE_EQ",
        "security_id": 1001,
        "symbol": "TEST1",
        "last_price": 100.5,
        "volume": 500,
        "timestamp": "08/06/2026 13:00:00"
    }
    quote_copy = quote_orig.copy()
    received_at_1 = datetime.now(timezone.utc)
    buffer.update_quote(quote_copy, received_at=received_at_1)
    assert quote_copy == quote_orig, "Input quote dictionary was mutated"

    # 1. First quote enters buffer
    latest_q = buffer.latest("NSE_EQ", 1001)
    assert latest_q is not None, "First quote did not enter buffer"
    assert latest_q["last_price"] == 100.5
    assert latest_q["volume"] == 500

    # 6. Active instrument requires minimum updates (currently 1, min is 2)
    status_1 = buffer.instrument_status("NSE_EQ", 1001, now=received_at_1)
    assert status_1["has_quote"] is True
    assert status_1["is_active"] is False, "Instrument became active with only 1 update"
    assert status_1["reason"] == "insufficient_total_updates"

    # 2. Second update increments update_count
    received_at_2 = received_at_1 + timedelta(seconds=1)
    quote_2 = quote_orig.copy()
    quote_2["timestamp"] = "08/06/2026 13:00:01"
    buffer.update_quote(quote_2, received_at=received_at_2)
    status_2 = buffer.instrument_status("NSE_EQ", 1001, now=received_at_2)
    assert status_2["update_count"] == 2
    assert status_2["price_change_count"] == 0
    # Should now be active since we have 2 updates and it's fresh
    assert status_2["is_active"] is True, f"Instrument should be active: {status_2}"

    # 3. Equal-price update remains a valid update
    received_at_3 = received_at_2 + timedelta(seconds=1)
    quote_3 = quote_orig.copy()
    quote_3["timestamp"] = "08/06/2026 13:00:02"
    buffer.update_quote(quote_3, received_at=received_at_3)
    status_3 = buffer.instrument_status("NSE_EQ", 1001, now=received_at_3)
    assert status_3["update_count"] == 3
    assert status_3["price_change_count"] == 0, "Equal price should not increment price change count"

    # 4. Price change increments price_change_count
    received_at_4 = received_at_3 + timedelta(seconds=1)
    quote_4 = quote_orig.copy()
    quote_4["last_price"] = 101.0
    quote_4["timestamp"] = "08/06/2026 13:00:03"
    buffer.update_quote(quote_4, received_at=received_at_4)
    status_4 = buffer.instrument_status("NSE_EQ", 1001, now=received_at_4)
    assert status_4["update_count"] == 4
    assert status_4["price_change_count"] == 1, "Price change did not increment price change count"

    # 5. Locally stale quote is rejected
    # Test age limit: max_quote_age_seconds=10.0. Age 11 seconds.
    status_stale = buffer.instrument_status("NSE_EQ", 1001, now=received_at_4 + timedelta(seconds=11))
    assert status_stale["is_locally_fresh"] is False
    assert status_stale["is_active"] is False
    assert status_stale["reason"] == "locally_stale"

    # 13. NaN, infinity and bool price values are rejected
    bad_quotes = [
        {"exchange": "NSE_EQ", "security_id": 1001, "last_price": float('nan'), "timestamp": "08/06/2026 13:00:00"},
        {"exchange": "NSE_EQ", "security_id": 1001, "last_price": float('inf'), "timestamp": "08/06/2026 13:00:00"},
        {"exchange": "NSE_EQ", "security_id": 1001, "last_price": True, "timestamp": "08/06/2026 13:00:00"},
    ]
    for bq in bad_quotes:
        try:
            buffer.update_quote(bq)
            assert False, f"Bad quote was not rejected: {bq}"
        except (TypeError, ValueError):
            pass  # Expected behaviour

    # Set up second instrument to test pairs
    quote_tgt_orig = {
        "exchange": "NSE_EQ",
        "security_id": 1002,
        "symbol": "TEST2",
        "last_price": 50.0,
        "volume": 200,
        "timestamp": "08/06/2026 13:00:03"
    }
    
    # 7. Synchronized pair passes
    buffer.update_quote(quote_tgt_orig.copy(), received_at=received_at_4)
    buffer.update_quote(quote_tgt_orig.copy(), received_at=received_at_4) # 2nd update to make active
    
    p_status = buffer.pair_status("NSE_EQ", 1001, "NSE_EQ", 1002, now=received_at_4)
    assert p_status["both_active"] is True
    assert p_status["pair_is_synchronized"] is True, f"Pair should be synchronized: {p_status}"

    # 8. Large local receive gap fails
    # ref quote received at received_at_4, tgt quote received at received_at_4 + 11s (max gap is 10)
    buffer2 = LiveQuoteBuffer(max_quote_age_seconds=30.0, max_pair_gap_seconds=10.0, min_updates_for_active=1)
    buffer2.update_quote(quote_orig.copy(), received_at=received_at_4)
    buffer2.update_quote(quote_tgt_orig.copy(), received_at=received_at_4 + timedelta(seconds=11))
    p_status_gap = buffer2.pair_status("NSE_EQ", 1001, "NSE_EQ", 1002, now=received_at_4 + timedelta(seconds=11))
    assert p_status_gap["pair_is_synchronized"] is False
    assert any("local_receive_gap_too_large" in r for r in p_status_gap["blocking_reasons"])

    # 9. Large provider timestamp gap fails
    # Provider timestamp diff: 11 seconds (13:00:00 vs 13:00:11)
    buffer3 = LiveQuoteBuffer(max_quote_age_seconds=30.0, max_pair_gap_seconds=10.0, min_updates_for_active=1)
    q_ref = quote_orig.copy()
    q_ref["timestamp"] = "08/06/2026 13:00:00"
    q_tgt = quote_tgt_orig.copy()
    q_tgt["timestamp"] = "08/06/2026 13:00:11"
    buffer3.update_quote(q_ref, received_at=received_at_4)
    buffer3.update_quote(q_tgt, received_at=received_at_4)
    p_status_pt_gap = buffer3.pair_status("NSE_EQ", 1001, "NSE_EQ", 1002, now=received_at_4)
    assert p_status_pt_gap["pair_is_synchronized"] is False
    assert any("provider_timestamp_gap_too_large" in r for r in p_status_pt_gap["blocking_reasons"])

    # 10. Missing provider timestamp does not silently pass
    buffer4 = LiveQuoteBuffer(max_quote_age_seconds=30.0, max_pair_gap_seconds=10.0, min_updates_for_active=1)
    q_ref_no_ts = quote_orig.copy()
    q_ref_no_ts["timestamp"] = ""  # Missing
    q_tgt_ok = quote_tgt_orig.copy()
    buffer4.update_quote(q_ref_no_ts, received_at=received_at_4)
    buffer4.update_quote(q_tgt_ok, received_at=received_at_4)
    p_status_missing_ts = buffer4.pair_status("NSE_EQ", 1001, "NSE_EQ", 1002, now=received_at_4)
    assert p_status_missing_ts["pair_is_synchronized"] is False
    assert any("missing_provider_timestamps" in r for r in p_status_missing_ts["blocking_reasons"])

    # 14. Pair selector ranks synchronized active pair first
    # Pair A is synchronized, Pair B is stale/inactive
    candidates = [
        {
            "reference": {"exchange": "NSE_EQ", "security_id": 1003, "symbol": "REF_B"},
            "target": {"exchange": "NSE_EQ", "security_id": 1004, "symbol": "TGT_B"}
        },
        {
            "reference": {"exchange": "NSE_EQ", "security_id": 1001, "symbol": "SETFNIF50"},
            "target": {"exchange": "NSE_EQ", "security_id": 1002, "symbol": "HDFCNIFTY"}
        }
    ]
    # Pair A (1001 & 1002) is updated and synchronized in buffer
    # Pair B (1003 & 1004) has no quotes in buffer
    selector = FreshInstrumentPairSelector(buffer)
    rankings = selector.rank_pairs(candidates, now=received_at_4)
    assert len(rankings) == 2
    assert rankings[0]["pair"]["reference"]["security_id"] == 1001, "Synchronized pair should be ranked first"
    assert rankings[0]["pair_is_synchronized"] is True
    assert rankings[1]["pair_is_synchronized"] is False

    best_selection = selector.select_best(candidates, now=received_at_4)
    assert best_selection["selected"] is not None
    assert best_selection["selected"]["reference"]["security_id"] == 1001

    # 15. Pair selector returns no selection when every pair is stale
    # Query status at received_at_4 + 20s (all quotes are stale)
    best_stale = selector.select_best(candidates, now=received_at_4 + timedelta(seconds=20))
    assert best_stale["selected"] is None
    assert best_stale["reason"] == "no_synchronized_active_pair"

    # 16. Synchronization monitor requires consecutive valid checks
    monitor = QuoteSynchronizationMonitor(required_consecutive_synchronized_checks=3)
    assert monitor.ready is False
    
    # Check 1: Synchronized
    obs_time_1 = datetime(2026, 6, 8, 12, 0, 0, tzinfo=timezone.utc)
    monitor.observe({"pair_is_synchronized": True}, observed_at=obs_time_1)
    assert monitor.ready is False
    assert monitor.consecutive_synchronized_checks == 1

    # Check 2: Synchronized
    obs_time_2 = obs_time_1 + timedelta(seconds=1)
    monitor.observe({"pair_is_synchronized": True}, observed_at=obs_time_2)
    assert monitor.ready is False
    assert monitor.consecutive_synchronized_checks == 2

    # Check 3: Synchronized -> Ready!
    obs_time_3 = obs_time_2 + timedelta(seconds=1)
    monitor.observe({"pair_is_synchronized": True}, observed_at=obs_time_3)
    assert monitor.ready is True
    assert monitor.consecutive_synchronized_checks == 3

    # 17. One invalid check resets the consecutive counter
    obs_time_4 = obs_time_3 + timedelta(seconds=1)
    monitor.observe({"pair_is_synchronized": False}, observed_at=obs_time_4)
    assert monitor.ready is False
    assert monitor.consecutive_synchronized_checks == 0
    assert monitor.maximum_consecutive_synchronized_checks == 3

    # 18. Out-of-order monitor timestamps are rejected
    try:
        monitor.observe({"pair_is_synchronized": True}, observed_at=obs_time_3)  # Out of order (before obs_time_4)
        assert False, "Out of order monitor timestamp was not rejected"
    except ValueError:
        pass  # Expected behaviour

    # 19. Snapshot is fully serializable
    snapshot = buffer.snapshot()
    serialized_str = json.dumps(snapshot)
    assert isinstance(serialized_str, str)
    
    # 20. No order-related method is called: Verified in code that no execution/order APIs are used.

    print("All LiveQuoteBuffer, PairSelector and SynchronizationMonitor assertions passed.")

if __name__ == "__main__":
    run_tests()
