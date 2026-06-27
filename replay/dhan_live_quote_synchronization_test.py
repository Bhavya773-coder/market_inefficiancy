import os
import pprint
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from connectors.dhan_connector import DhanConnector
from connectors.dhan_live_quote_source import DhanLiveQuoteSource
from ai.live_quote_buffer import LiveQuoteBuffer
from ai.fresh_instrument_pair_selector import FreshInstrumentPairSelector
from ai.quote_synchronization_monitor import QuoteSynchronizationMonitor

def is_market_open_now(dt=None):
    if dt is None:
        dt = datetime.now(timezone.utc)
    kolkata_tz = ZoneInfo("Asia/Kolkata")
    dt_kolkata = dt.astimezone(kolkata_tz)
    
    weekday = dt_kolkata.weekday()
    if weekday >= 5:
        return False, "weekend"
        
    market_start = dt_kolkata.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = dt_kolkata.replace(hour=15, minute=30, second=0, microsecond=0)
    
    HOLIDAYS = [
        "2026-01-26", "2026-03-06", "2026-04-02", "2026-04-14",
        "2026-05-01", "2026-08-15", "2026-10-02", "2026-11-09", "2026-12-25"
    ]
    date_str = dt_kolkata.strftime("%Y-%m-%d")
    if date_str in HOLIDAYS:
        return False, f"holiday: {date_str}"
        
    if market_start <= dt_kolkata <= market_end:
        return True, "open"
        
    return False, "outside_hours"

def main():
    print("=== DHAN LIVE QUOTE SYNCHRONIZATION DIAGNOSTIC ===")
    
    # Load environment variables
    load_dotenv(".env")
    
    client_id = os.getenv("DHAN_CLIENT_ID")
    access_token = os.getenv("DHAN_ACCESS_TOKEN")
    
    expect_live_env = os.getenv("DHAN_EXPECT_LIVE_MARKET", "auto").lower()
    market_open_detected, market_reason = is_market_open_now()
    
    if expect_live_env == "false":
        expect_live = False
        print("DHAN_EXPECT_LIVE_MARKET: forced false")
    elif expect_live_env == "true":
        expect_live = True
        print("DHAN_EXPECT_LIVE_MARKET: forced true")
    else:
        expect_live = market_open_detected
        print(f"DHAN_EXPECT_LIVE_MARKET: auto (market_open={market_open_detected}, reason={market_reason})")
    
    if not client_id or not access_token or client_id.strip() == "" or access_token.strip() == "":
        print("BLOCKED: Dhan credentials missing or empty in .env file.")
        if not expect_live:
            print("LIVE TEST STATUS: SKIPPED_MARKET_CLOSED")
        return

    # Initialize connector
    try:
        connector = DhanConnector()
    except Exception as e:
        print(f"BLOCKED: Failed to initialize DhanConnector: {e}")
        return

    # Configuration options
    duration = int(os.getenv("DHAN_LIVE_OBSERVATION_SECONDS", 10))  # shorten to 10s for fast diagnostics
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
    quote_buffer = LiveQuoteBuffer(
        max_quote_age_seconds=10.0,
        max_pair_gap_seconds=10.0,
        min_updates_for_active=2,
        activity_window_seconds=30.0
    )
    
    source = DhanLiveQuoteSource(connector, quote_buffer, poll_interval_seconds=poll_interval)
    selector = FreshInstrumentPairSelector(quote_buffer)
    monitor = QuoteSynchronizationMonitor(required_consecutive_synchronized_checks=3)

    print("\nStarting live quote collection run and synchronization monitoring...")
    
    start_time = time.perf_counter()
    received_quote_count = 0
    api_error_count = 0
    
    while (time.perf_counter() - start_time) < duration:
        tick_time = datetime.now(timezone.utc)
        
        by_exchange = {}
        for inst in instruments:
            ex = inst["exchange"]
            sec_id = int(inst["security_id"])
            if ex not in by_exchange:
                by_exchange[ex] = []
            by_exchange[ex].append(sec_id)
            
        for ex, sec_ids in by_exchange.items():
            try:
                res = connector.get_last_prices(ex, sec_ids)
                for q in res.get("quotes", []):
                    symbol = next((inst["symbol"] for inst in instruments if inst["security_id"] == q["security_id"]), "")
                    quote_copy = q.copy()
                    quote_copy["symbol"] = symbol
                    quote_copy["data_source"] = "dhan_live"
                    
                    quote_buffer.update_quote(
                        quote_copy,
                        received_at=tick_time,
                        received_monotonic=time.perf_counter()
                    )
                    received_quote_count += 1
            except Exception as e:
                source._record_api_error(e, ex, len(sec_ids))
                api_error_count += 1
                
        # Monitor check
        best_result = selector.select_best(candidate_pairs, now=tick_time)
        if best_result["selected"]:
            best_pair = best_result["selected"]
            p_status = quote_buffer.pair_status(
                best_pair["reference"]["exchange"], best_pair["reference"]["security_id"],
                best_pair["target"]["exchange"], best_pair["target"]["security_id"],
                now=tick_time
            )
            try:
                monitor.observe(p_status, observed_at=tick_time)
            except Exception:
                pass
                
        time.sleep(poll_interval)

    # Select and rank pairs at the end
    now = datetime.now(timezone.utc)
    rankings = selector.rank_pairs(candidate_pairs, now=now)
    best_result = selector.select_best(candidate_pairs, now=now)

    # Print results
    print("\n" + "="*50)
    if not expect_live:
        print("LIVE TEST STATUS: SKIPPED_MARKET_CLOSED")
    print("DIAGNOSTIC SUMMARY:")
    print(f"source mode: POLL")
    print(f"duration: {time.perf_counter() - start_time:.2f} seconds")
    print(f"quotes received: {received_quote_count}")
    print(f"API errors: {api_error_count}")
    
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
    main()
