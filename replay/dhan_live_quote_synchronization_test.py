import os
import pprint
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

from connectors.dhan_connector import DhanConnector
from connectors.dhan_live_quote_source import DhanLiveQuoteSource
from ai.live_quote_buffer import LiveQuoteBuffer
from ai.fresh_instrument_pair_selector import FreshInstrumentPairSelector
from ai.quote_synchronization_monitor import QuoteSynchronizationMonitor

def main():
    print("=== DHAN LIVE QUOTE SYNCHRONIZATION DIAGNOSTIC ===")
    
    # Load environment variables
    load_dotenv(".env")
    
    client_id = os.getenv("DHAN_CLIENT_ID")
    access_token = os.getenv("DHAN_ACCESS_TOKEN")
    
    if not client_id or not access_token or client_id.strip() == "" or access_token.strip() == "":
        print("BLOCKED: Dhan credentials missing or empty in .env file.")
        print("SKIPPED: Live observation test cannot run without credentials.")
        return

    # Initialize connector
    try:
        connector = DhanConnector()
    except Exception as e:
        print(f"BLOCKED: Failed to initialize DhanConnector: {e}")
        return

    # Configuration options
    duration = int(os.getenv("DHAN_LIVE_OBSERVATION_SECONDS", 30))
    poll_interval = float(os.getenv("DHAN_LIVE_POLL_INTERVAL_SECONDS", 1.0))
    
    print(f"Observation Duration: {duration} seconds")
    print(f"Polling Interval: {poll_interval} seconds")

    # Define candidate instruments
    instruments = [
        {"symbol": "SETFNIF50", "exchange": "NSE_EQ", "security_id": 10176},
        {"symbol": "HDFCNEXT50", "exchange": "NSE_EQ", "security_id": 10619},
        {"symbol": "MOVALUE", "exchange": "NSE_EQ", "security_id": 10825},
        {"symbol": "HDFCVALUE", "exchange": "NSE_EQ", "security_id": 11260},
        {"symbol": "HDFCNIFTY", "exchange": "NSE_EQ", "security_id": 11591},
        {"symbol": "NIFTYBEES", "exchange": "NSE_EQ", "security_id": 10576}
    ]

    # Generate candidate pairs
    candidate_pairs = []
    for i in range(len(instruments)):
        for j in range(len(instruments)):
            if i != j:
                candidate_pairs.append({
                    "reference": instruments[i],
                    "target": instruments[j]
                })

    # Initialize synchronization components
    # max_quote_age=10s, max_pair_gap=10s, min_updates=2
    quote_buffer = LiveQuoteBuffer(
        max_quote_age_seconds=10.0,
        max_pair_gap_seconds=10.0,
        min_updates_for_active=2,
        activity_window_seconds=30.0
    )
    
    source = DhanLiveQuoteSource(connector, quote_buffer, poll_interval_seconds=poll_interval)
    source.subscribe(instruments)

    print("\nStarting live quote collection run...")
    diag = source.run_for(duration)
    print("Quote collection complete.")

    # Select and rank pairs
    selector = FreshInstrumentPairSelector(quote_buffer)
    now = datetime.now(timezone.utc)
    rankings = selector.rank_pairs(candidate_pairs, now=now)
    best_result = selector.select_best(candidate_pairs, now=now)

    # Synchronization monitor check
    # Check current status for best pair
    monitor = QuoteSynchronizationMonitor(required_consecutive_synchronized_checks=3)
    if best_result["selected"]:
        best_pair = best_result["selected"]
        p_status = quote_buffer.pair_status(
            best_pair["reference"]["exchange"], best_pair["reference"]["security_id"],
            best_pair["target"]["exchange"], best_pair["target"]["security_id"],
            now=now
        )
        # Simulate consecutive observations (we observe the current snapshot 3 times in a row for diagnostics)
        for i in range(3):
            obs_time = now + timedelta(seconds=i)
            monitor.observe(p_status, observed_at=obs_time)

    # Print results
    print("\n" + "="*50)
    print("DIAGNOSTIC SUMMARY:")
    print(f"source mode: {diag['mode']}")
    print(f"duration: {diag['duration_seconds']:.2f} seconds")
    print(f"quotes received: {diag['received_quote_count']}")
    print(f"API errors: {diag['api_error_count']}")
    print(f"partial errors: {diag['partial_error_count']}")
    
    print("\nPAIR RANKINGS:")
    print(f"{'Rank':<5} | {'Reference':<12} | {'Target':<12} | {'Score':<6} | {'Synchronized':<12} | {'Active':<6}")
    print("-" * 65)
    for idx, r in enumerate(rankings[:10]):  # Show top 10
        ref_sym = r["pair"]["reference"]["symbol"]
        tgt_sym = r["pair"]["target"]["symbol"]
        print(f"{idx+1:<5} | {ref_sym:<12} | {tgt_sym:<12} | {r['score']:<6.1f} | {str(r['pair_is_synchronized']):<12} | {str(r['both_active']):<6}")

    print("\nSELECTED PAIR:")
    if best_result["selected"]:
        pprint.pprint(best_result["selected"])
    else:
        print("None")

    print(f"\nsynchronization readiness: {monitor.ready}")
    
    print("\nBLOCKING REASONS FOR ALL PAIRS:")
    printed_reasons = set()
    for r in rankings:
        for reason in r["blocking_reasons"]:
            ref_sym = r["pair"]["reference"]["symbol"]
            tgt_sym = r["pair"]["target"]["symbol"]
            desc = f"{ref_sym} <-> {tgt_sym}: {reason}"
            if desc not in printed_reasons:
                print(f" - {desc}")
                printed_reasons.add(desc)

    print("="*50)

if __name__ == "__main__":
    from datetime import timedelta
    main()
