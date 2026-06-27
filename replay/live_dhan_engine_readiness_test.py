import sys
import time
import os
import pprint
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from connectors.dhan_connector import DhanConnector
from connectors.dhan_live_quote_source import DhanLiveQuoteSource
from ai.live_quote_buffer import LiveQuoteBuffer
from ai.fresh_instrument_pair_selector import FreshInstrumentPairSelector
from ai.quote_synchronization_monitor import QuoteSynchronizationMonitor
from ai.market_event import MarketEvent
from ai.quote_freshness_validator import QuoteFreshnessValidator
from ai.price_change_detector import PriceChangeDetector
from ai.reaction_event import ReactionEvent
from ai.lag_detector import LagDetector
from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
from ai.candidate_feasibility_adapter import CandidateFeasibilityAdapter
from ai.paper_entry_decision import PaperEntryDecision
from ai.paper_trade_simulator import PaperTradeSimulator

# Candidate Instruments list
CANDIDATES = [
    {"symbol": "SETFNIF50", "exchange": "NSE_EQ", "security_id": 10176},
    {"symbol": "HDFCNEXT50", "exchange": "NSE_EQ", "security_id": 10619},
    {"symbol": "MOVALUE", "exchange": "NSE_EQ", "security_id": 10825},
    {"symbol": "HDFCVALUE", "exchange": "NSE_EQ", "security_id": 11260},
    {"symbol": "HDFCNIFTY", "exchange": "NSE_EQ", "security_id": 11591},
    {"symbol": "NIFTYBEES", "exchange": "NSE_EQ", "security_id": 10576}
]

def is_market_open_now(dt=None):
    """
    Checks if India equity market is open.
    Regular equity weekday hours: Mon-Fri 9:15 AM to 3:30 PM (Asia/Kolkata).
    """
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
        "2026-01-26", # Republic Day
        "2026-03-06", # Holi
        "2026-04-02", # Good Friday
        "2026-04-14", # Dr. Ambedkar Jayanti
        "2026-05-01", # Maharashtra Day
        "2026-08-15", # Independence Day
        "2026-10-02", # Mahatma Gandhi Jayanti
        "2026-11-09", # Diwali Balipratipada
        "2026-12-25"  # Christmas
    ]
    date_str = dt_kolkata.strftime("%Y-%m-%d")
    if date_str in HOLIDAYS:
        return False, f"holiday: {date_str}"
        
    if market_start <= dt_kolkata <= market_end:
        return True, "open"
        
    return False, "outside_hours"

def score_readiness(report, expect_live=True):
    """
    Computes a readiness score based on separate criteria, ensuring
    quote retrieval and quote synchronization are scored separately.
    """
    score = 0
    blocking_issues = []
    warnings = []

    # Category 1: Live credentials and API connectivity (10 pts)
    if report.get("credentials_valid") is True:
        score += 10
    else:
        blocking_issues.append("Dhan API credentials missing or invalid")

    # Category 2: Batch/stream quote retrieval (10 pts)
    if report.get("quote_retrieval_success") is True:
        score += 10
    elif expect_live:
        blocking_issues.append("Dhan batch/stream quote retrieval failed")
    else:
        warnings.append("Dhan quote retrieval failed (expected closed market)")

    # Category 3: Both instruments active (15 pts)
    if report.get("both_active") is True:
        score += 15
    elif expect_live:
        blocking_issues.append("One or both instruments are inactive/stale")
    else:
        warnings.append("One or both instruments inactive (expected closed market)")

    # Category 4: Pair synchronized (20 pts)
    if report.get("pair_synchronized") is True:
        score += 20
    elif expect_live:
        blocking_issues.append("Selected pair is not synchronized")
    else:
        warnings.append("Selected pair not synchronized (expected closed market)")

    # Category 5: Freshness validator passes (15 pts)
    if report.get("freshness_passed") is True:
        score += 15
    elif expect_live:
        blocking_issues.append("Freshness validation failed (gaps exceed limits)")
    else:
        warnings.append("Freshness validation failed (expected closed market)")

    # Category 6: Price movement/change detection (10 pts)
    if report.get("price_movement_detected") is True:
        score += 10
    else:
        warnings.append("No price movement detected in reference/target instruments")

    # Category 7: Lag/opportunity pipeline (10 pts)
    if report.get("lag_opportunity_pipeline_passed") is True:
        score += 10
    else:
        warnings.append("No valid lag opportunity detected in pipeline")

    # Category 8: Feasibility and paper candidate (5 pts)
    if report.get("feasibility_candidate_passed") is True:
        score += 5
    else:
        blocking_issues.append("Feasibility checks or paper trade candidate creation failed")

    # Category 9: Entry decision available (5 pts)
    if report.get("entry_decision_available") is True:
        score += 5
    else:
        warnings.append("Entry decision is not BUY_ALLOWED")

    # Safety constraints to determine grade
    is_ready = (
        report.get("pair_synchronized") is True and
        report.get("freshness_passed") is True and
        report.get("mock_data_used") is False and
        report.get("order_apis_called") is False and
        report.get("lag_opportunity_pipeline_passed") is True and
        len(blocking_issues) == 0
    )

    if is_ready:
        if score >= 90:
            grade = "LIVE_DIAGNOSTIC_STRONG"
        elif score >= 70:
            grade = "LIVE_DIAGNOSTIC_WORKING_BUT_INCOMPLETE"
        elif score >= 50:
            grade = "LIVE_DIAGNOSTIC_WEAK"
        else:
            grade = "NOT_READY"
    else:
        grade = "NOT_READY"

    return {
        "score": score,
        "grade": grade,
        "blocking_issues": blocking_issues,
        "warnings": warnings
    }

def main():
    print("=== LIVE DHAN ENGINE READINESS DIAGNOSTIC ===")
    
    # Load credentials
    load_dotenv(".env")
    client_id = os.getenv("DHAN_CLIENT_ID")
    access_token = os.getenv("DHAN_ACCESS_TOKEN")
    
    # Check live market expectation
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

    report = {
        "credentials_valid": False,
        "quote_retrieval_success": False,
        "both_active": False,
        "pair_synchronized": False,
        "freshness_passed": False,
        "price_movement_detected": False,
        "lag_opportunity_pipeline_passed": False,
        "feasibility_candidate_passed": False,
        "entry_decision_available": False,
        "mock_data_used": False,
        "order_apis_called": False
    }

    if not client_id or not access_token or client_id.strip() == "" or access_token.strip() == "":
        print("BLOCKED: Dhan credentials missing or empty in .env.")
        res = score_readiness(report, expect_live=expect_live)
        print("\n" + "="*50)
        if not expect_live:
            print("LIVE TEST STATUS: SKIPPED_MARKET_CLOSED")
        print("LIVE ENGINE READINESS SCORE:")
        print(f"{res['score']}/100")
        print("GRADE:")
        print(res["grade"])
        if res["blocking_issues"]:
            print("BLOCKING ISSUES:")
            for issue in res["blocking_issues"]:
                print(f" - {issue}")
        print("\nREAL ORDER APIs USED: NO")
        print("MOCK DATA USED: NO")
        print("="*50)
        return

    report["credentials_valid"] = True

    # Initialize connector
    try:
        connector = DhanConnector()
    except Exception as e:
        print(f"Error initializing DhanConnector: {e}")
        report["credentials_valid"] = False
        res = score_readiness(report, expect_live=expect_live)
        print("\n" + "="*50)
        if not expect_live:
            print("LIVE TEST STATUS: SKIPPED_MARKET_CLOSED")
        print("LIVE ENGINE READINESS SCORE:")
        print(f"{res['score']}/100")
        print("GRADE:")
        print(res["grade"])
        if res["blocking_issues"]:
            print("BLOCKING ISSUES:")
            for issue in res["blocking_issues"]:
                print(f" - {issue}")
        print("="*50)
        return

    # Generate candidate pairs
    candidate_pairs = []
    for i in range(len(CANDIDATES)):
        for j in range(len(CANDIDATES)):
            if i != j:
                candidate_pairs.append({
                    "reference": CANDIDATES[i],
                    "target": CANDIDATES[j]
                })

    # Initialize buffers and sources
    # max_quote_age=10s, max_pair_gap=10s, min_updates=2
    quote_buffer = LiveQuoteBuffer(
        max_quote_age_seconds=10.0,
        max_pair_gap_seconds=10.0,
        min_updates_for_active=2,
        activity_window_seconds=30.0
    )
    
    selector = FreshInstrumentPairSelector(quote_buffer)
    monitor = QuoteSynchronizationMonitor(required_consecutive_synchronized_checks=3)

    # Poll multiple ticks to evaluate actual updates sequential synchronization
    print("\nStarting QuoteSynchronizationMonitor checks (4 ticks)...")
    REFERENCE = None
    TARGET = None
    
    for tick in range(4):
        print(f" Polling tick {tick+1}/4...")
        received_at = datetime.now(timezone.utc)
        received_monotonic = time.perf_counter()
        
        try:
            sec_ids = [c["security_id"] for c in CANDIDATES]
            batch_result = connector.get_last_prices("NSE_EQ", sec_ids)
            
            for q in batch_result.get("quotes", []):
                symbol = next((c["symbol"] for c in CANDIDATES if c["security_id"] == q["security_id"]), "")
                quote_copy = q.copy()
                quote_copy["symbol"] = symbol
                quote_copy["data_source"] = "dhan_live"
                
                quote_buffer.update_quote(
                    quote_copy,
                    received_at=received_at,
                    received_monotonic=received_monotonic
                )
                report["quote_retrieval_success"] = True
                
        except Exception as e:
            print(f"  Error polling batch quotes: {e}")
            
        now_tick = datetime.now(timezone.utc)
        best_result = selector.select_best(candidate_pairs, now=now_tick)
        
        if best_result["selected"]:
            REFERENCE = best_result["selected"]["reference"]
            TARGET = best_result["selected"]["target"]
            
            p_status = quote_buffer.pair_status(
                REFERENCE["exchange"], REFERENCE["security_id"],
                TARGET["exchange"], TARGET["security_id"],
                now=now_tick
            )
            
            try:
                monitor.observe(p_status, observed_at=now_tick)
                print(f"  Selected: {REFERENCE['symbol']} <-> {TARGET['symbol']} | "
                      f"Sync: {p_status['pair_is_synchronized']} | "
                      f"Snapshot ID: {p_status['snapshot_identity']} | "
                      f"Consecutive Sync Checks: {monitor.consecutive_synchronized_checks}")
            except Exception as e:
                print(f"  Monitor observation error: {e}")
        else:
            print("  No synchronized active pair selected.")
            
        time.sleep(2.0)

    # Evaluate final selected pair from the run
    now = datetime.now(timezone.utc)
    best_result = selector.select_best(candidate_pairs, now=now)

    if not best_result["selected"]:
        print("\nSTATUS: FAIL")
        print("Reason: no_synchronized_active_pair_selected_from_buffer")
        
        # When market is closed, we don't treat this as script failure.
        res = score_readiness(report, expect_live=expect_live)
        print("\n" + "="*50)
        if not expect_live:
            print("LIVE TEST STATUS: SKIPPED_MARKET_CLOSED")
        print("LIVE ENGINE READINESS SCORE:")
        print(f"{res['score']}/100")
        print("GRADE:")
        print(res["grade"])
        if res["blocking_issues"]:
            print("BLOCKING ISSUES:")
            for issue in res["blocking_issues"]:
                print(f" - {issue}")
        if res["warnings"]:
            print("WARNINGS:")
            for warning in res["warnings"]:
                print(f" - {warning}")
        print("\nREAL ORDER APIs USED: NO")
        print("MOCK DATA USED: NO")
        print("="*50)
        return

    REFERENCE = best_result["selected"]["reference"]
    TARGET = best_result["selected"]["target"]

    print("\nSELECTED SYNCED PAIR:")
    print("REFERENCE:")
    pprint.pprint(REFERENCE)
    print("TARGET:")
    pprint.pprint(TARGET)
    print("\nLIVE DATA SOURCE: dhan_live\n")

    p_status = quote_buffer.pair_status(
        REFERENCE["exchange"], REFERENCE["security_id"],
        TARGET["exchange"], TARGET["security_id"],
        now=now
    )
    report["both_active"] = p_status["both_active"]
    report["pair_synchronized"] = p_status["pair_is_synchronized"]

    print(f"QuoteSynchronizationMonitor Ready: {monitor.ready}")

    # Use first quotes from the buffer
    print("\n1. Using first quotes from pair selector...")
    quote_ref_1 = quote_buffer.latest(REFERENCE["exchange"], REFERENCE["security_id"])
    quote_tgt_1 = quote_buffer.latest(TARGET["exchange"], TARGET["security_id"])

    print(f"quote_ref_1: {quote_ref_1}")
    print(f"quote_tgt_1: {quote_tgt_1}")

    event_ref_1 = None
    event_tgt_1 = None
    if quote_ref_1 and quote_tgt_1:
        event_ref_1 = MarketEvent.from_quote(quote_ref_1)
        event_tgt_1 = MarketEvent.from_quote(quote_tgt_1)

    print("\nWaiting 3 seconds before next poll...")
    time.sleep(3)

    # Fetch second quotes (batch fetch)
    print("\n2. Fetching second quotes (batch)...")
    quote_ref_2 = None
    quote_tgt_2 = None
    
    try:
        batch_result = connector.get_last_prices(
            "NSE_EQ",
            [REFERENCE["security_id"], TARGET["security_id"]]
        )
        
        for q in batch_result.get("quotes", []):
            sec_id = q["security_id"]
            if sec_id == REFERENCE["security_id"]:
                quote_ref_2 = q.copy()
                quote_ref_2["symbol"] = REFERENCE["symbol"]
                quote_ref_2["mock"] = False
                quote_ref_2["data_source"] = "dhan_live"
            elif sec_id == TARGET["security_id"]:
                quote_tgt_2 = q.copy()
                quote_tgt_2["symbol"] = TARGET["symbol"]
                quote_tgt_2["mock"] = False
                quote_tgt_2["data_source"] = "dhan_live"
        
        if not quote_ref_2 or not quote_tgt_2:
            raise ValueError(f"One or both instruments missing from batch result: {batch_result}")
    except Exception as e:
        print(f"Error during second quote fetch: {e}")

    print(f"quote_ref_2: {quote_ref_2}")
    print(f"quote_tgt_2: {quote_tgt_2}")

    event_ref_2 = None
    event_tgt_2 = None
    if quote_ref_2 and quote_tgt_2:
        event_ref_2 = MarketEvent.from_quote(quote_ref_2)
        event_tgt_2 = MarketEvent.from_quote(quote_tgt_2)

    # Pipeline components
    validator = QuoteFreshnessValidator()
    change_detector = PriceChangeDetector()
    lag_detector = LagDetector()
    opportunity_adapter = OpportunityAdapter()
    opportunity_validator = OpportunityValidator()
    candidate_factory = PaperTradeCandidateFactory()
    feasibility_adapter = CandidateFeasibilityAdapter()
    simulator = PaperTradeSimulator()

    # Check freshness of second quote timestamps
    timestamps_close = False
    if event_ref_2 and event_tgt_2:
        timestamps_close = validator.timestamps_close(
            event_ref_2.timestamp,
            event_tgt_2.timestamp,
            max_gap_seconds=10
        )
        ref_fresh = validator.is_fresh(event_ref_2.timestamp, max_age_seconds=10)
        tgt_fresh = validator.is_fresh(event_tgt_2.timestamp, max_age_seconds=10)
        
        report["freshness_passed"] = timestamps_close and ref_fresh and tgt_fresh
    else:
        report["freshness_passed"] = False

    print(f"\ntimestamps_close: {timestamps_close}")
    if not report["freshness_passed"]:
        print("STATUS: FAIL")
        print("Reason: quote_timestamps_not_close_or_stale")

    # Continue execution only if second quotes are fresh/close
    ref_change = None
    tgt_change = None
    ref_reaction = None
    tgt_reaction = None
    lag_result = None
    opportunity = None
    validation_result = None
    candidate = None
    feasibility_result = None
    entry_decision = None

    if report["freshness_passed"] and event_ref_1 and event_tgt_1 and event_ref_2 and event_tgt_2:
        ref_change = change_detector.detect(event_ref_2, event_ref_1)
        tgt_change = change_detector.detect(event_tgt_2, event_tgt_1)
        print(f"reference_change: {ref_change}")
        print(f"target_change: {tgt_change}")

        if ref_change and tgt_change:
            if ref_change.get("direction") != "UNCHANGED" or tgt_change.get("direction") != "UNCHANGED":
                report["price_movement_detected"] = True
        
        ref_reaction = ReactionEvent.from_price_change(ref_change) if ref_change else None
        tgt_reaction = ReactionEvent.from_price_change(tgt_change) if tgt_change else None

        lag_result = lag_detector.detect(ref_reaction, tgt_reaction, min_gap_percent=0.05)
        print(f"lag_result: {lag_result}")
        
        if lag_result is not None:
            lag_result["mock"] = False
            lag_result["data_source"] = "dhan_live"

            opportunity = opportunity_adapter.from_lag_result(lag_result)
            print(f"opportunity: {opportunity.to_dict() if opportunity else None}")
            
            if opportunity is not None:
                validation_result = opportunity_validator.validate(opportunity)
                print(f"validation_result: {validation_result}")
                
                if validation_result.get("is_valid", False):
                    report["lag_opportunity_pipeline_passed"] = True
                    
                    candidate = candidate_factory.from_validated_opportunity(validation_result)
                    print(f"candidate: {candidate.to_dict() if candidate else None}")
                    
                    if candidate is not None:
                        feasibility_result = feasibility_adapter.from_candidate(candidate)
                        print(f"feasibility_result: {feasibility_result}")
                        
                        if feasibility_result.get("is_feasible", False):
                            report["feasibility_candidate_passed"] = True
                        
                            entry_decision = simulator.create_entry_decision(
                                candidate,
                                quantity=10,
                                price=quote_tgt_2.get("last_price")
                            )
                            print(f"entry_decision: {entry_decision.to_dict() if entry_decision else None}")
                            
                            if entry_decision is not None and entry_decision.action == "BUY_ALLOWED":
                                report["entry_decision_available"] = True

    # Calculate final readiness score
    res = score_readiness(report, expect_live=expect_live)

    print("\n" + "="*50)
    if not expect_live:
        print("LIVE TEST STATUS: SKIPPED_MARKET_CLOSED")
    print("LIVE ENGINE READINESS SCORE:")
    print(f"{res['score']}/100")
    print("GRADE:")
    print(res["grade"])
    if res["blocking_issues"]:
        print("BLOCKING ISSUES:")
        for issue in res["blocking_issues"]:
            print(f" - {issue}")
    if res["warnings"]:
        print("WARNINGS:")
        for warning in res["warnings"]:
            print(f" - {warning}")
    print("\nREAL ORDER APIs USED: NO")
    print("MOCK DATA USED: NO")
    print("="*50)

if __name__ == "__main__":
    main()
