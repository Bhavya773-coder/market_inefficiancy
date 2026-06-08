import sys
import time
from datetime import datetime
from connectors.dhan_connector import DhanConnector
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
import pprint

REFERENCE = {
    "symbol": "SETFNIF50",
    "exchange": "NSE_EQ",
    "security_id": 10176
}

TARGET = {
    "symbol": "HDFCNEXT50",
    "exchange": "NSE_EQ",
    "security_id": 10619
}

def score_readiness(report):
    score = 100
    blocking_issues = []
    warnings = []

    if report.get("quote_fetch_failed") is True:
        score -= 25
        blocking_issues.append("Dhan quote fetch failed")
    
    if report.get("timestamps_not_close") is True:
        score -= 20
        blocking_issues.append("Quote timestamps are not close (limit 10s)")

    if report.get("no_price_movement") is True:
        score -= 15
        warnings.append("No price movement detected in both reference and target instruments")

    if report.get("lag_result_none") is True:
        score -= 15
        warnings.append("Lag result is None (no lag detected or insufficient gap)")

    if report.get("opportunity_none") is True:
        score -= 15
        warnings.append("Opportunity is None")

    if report.get("validation_invalid") is True:
        score -= 10
        blocking_issues.append("Opportunity validation failed")

    if report.get("candidate_none") is True:
        score -= 10
        blocking_issues.append("Paper trade candidate is None")

    if report.get("not_feasible") is True:
        score -= 10
        warnings.append("Candidate is not feasible after round-trip costs")

    if report.get("entry_decision_not_buy_allowed") is True:
        score -= 10
        warnings.append("Entry decision is not BUY_ALLOWED")

    # Cap score at 0
    score = max(0, score)

    # Determine grade
    if score >= 90:
        grade = "LIVE_DIAGNOSTIC_STRONG"
    elif score >= 70:
        grade = "LIVE_DIAGNOSTIC_WORKING_BUT_INCOMPLETE"
    elif score >= 50:
        grade = "LIVE_DIAGNOSTIC_WEAK"
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
    print("REFERENCE CONFIG:")
    pprint.pprint(REFERENCE)
    print("TARGET CONFIG:")
    pprint.pprint(TARGET)
    print("\nLIVE DATA SOURCE:")
    print("dhan_live\n")
    
    # Initialize report
    report = {
        "quote_fetch_failed": False,
        "timestamps_not_close": False,
        "no_price_movement": False,
        "lag_result_none": False,
        "opportunity_none": False,
        "validation_invalid": False,
        "candidate_none": False,
        "not_feasible": False,
        "entry_decision_not_buy_allowed": False
    }

    connector = DhanConnector()
    validator = QuoteFreshnessValidator()
    change_detector = PriceChangeDetector()
    lag_detector = LagDetector()
    opportunity_adapter = OpportunityAdapter()
    opportunity_validator = OpportunityValidator()
    candidate_factory = PaperTradeCandidateFactory()
    feasibility_adapter = CandidateFeasibilityAdapter()
    simulator = PaperTradeSimulator()

    # Step 1 & 2: Fetch first quote
    print("\n1. Fetching first quotes...")
    quote_ref_1 = None
    quote_tgt_1 = None
    try:
        quote_ref_1 = connector.get_last_price(REFERENCE["exchange"], REFERENCE["security_id"])
        quote_ref_1["symbol"] = REFERENCE["symbol"]
        quote_ref_1["mock"] = False
        quote_ref_1["data_source"] = "dhan_live"

        quote_tgt_1 = connector.get_last_price(TARGET["exchange"], TARGET["security_id"])
        quote_tgt_1["symbol"] = TARGET["symbol"]
        quote_tgt_1["mock"] = False
        quote_tgt_1["data_source"] = "dhan_live"
    except Exception as e:
        print(f"Error during first quote fetch: {e}")
        report["quote_fetch_failed"] = True

    print(f"quote_ref_1: {quote_ref_1}")
    print(f"quote_tgt_1: {quote_tgt_1}")

    event_ref_1 = None
    event_tgt_1 = None
    if quote_ref_1 and quote_tgt_1:
        event_ref_1 = MarketEvent.from_quote(quote_ref_1)
        event_tgt_1 = MarketEvent.from_quote(quote_tgt_1)

    # Step 6: Wait 5 seconds
    print("\nWaiting 5 seconds...")
    time.sleep(5)

    # Step 7 & 8: Fetch second quotes
    print("\n2. Fetching second quotes...")
    quote_ref_2 = None
    quote_tgt_2 = None
    if not report["quote_fetch_failed"]:
        try:
            quote_ref_2 = connector.get_last_price(REFERENCE["exchange"], REFERENCE["security_id"])
            quote_ref_2["symbol"] = REFERENCE["symbol"]
            quote_ref_2["mock"] = False
            quote_ref_2["data_source"] = "dhan_live"

            quote_tgt_2 = connector.get_last_price(TARGET["exchange"], TARGET["security_id"])
            quote_tgt_2["symbol"] = TARGET["symbol"]
            quote_tgt_2["mock"] = False
            quote_tgt_2["data_source"] = "dhan_live"
        except Exception as e:
            print(f"Error during second quote fetch: {e}")
            report["quote_fetch_failed"] = True

    print(f"quote_ref_2: {quote_ref_2}")
    print(f"quote_tgt_2: {quote_tgt_2}")

    event_ref_2 = None
    event_tgt_2 = None
    if quote_ref_2 and quote_tgt_2:
        event_ref_2 = MarketEvent.from_quote(quote_ref_2)
        event_tgt_2 = MarketEvent.from_quote(quote_tgt_2)

    # Check timestamps closeness
    timestamps_close = False
    if event_ref_2 and event_tgt_2:
        timestamps_close = validator.timestamps_close(
            event_ref_2.timestamp,
            event_tgt_2.timestamp,
            max_gap_seconds=10
        )
    else:
        report["timestamps_not_close"] = True

    print(f"\ntimestamps_close: {timestamps_close}")
    if not timestamps_close:
        report["timestamps_not_close"] = True
        print("STATUS: FAIL")
        print("Reason: quote_timestamps_not_close")

    # Continue lag detection if timestamps are close
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

    if not report["quote_fetch_failed"] and not report["timestamps_not_close"]:
        # Calculate changes
        ref_change = change_detector.detect(event_ref_2, event_ref_1)
        tgt_change = change_detector.detect(event_tgt_2, event_tgt_1)
        print(f"reference_change: {ref_change}")
        print(f"target_change: {tgt_change}")

        # Check for price movement
        if ref_change and tgt_change:
            if ref_change.get("direction") == "UNCHANGED" and tgt_change.get("direction") == "UNCHANGED":
                report["no_price_movement"] = True
        else:
            report["no_price_movement"] = True

        ref_reaction = ReactionEvent.from_price_change(ref_change) if ref_change else None
        tgt_reaction = ReactionEvent.from_price_change(tgt_change) if tgt_change else None

        # Lag Detector
        lag_result = lag_detector.detect(ref_reaction, tgt_reaction, min_gap_percent=0.05)
        print(f"lag_result: {lag_result}")
        if lag_result is None:
            report["lag_result_none"] = True
            report["opportunity_none"] = True
            report["validation_invalid"] = True
            report["candidate_none"] = True
            report["not_feasible"] = True
            report["entry_decision_not_buy_allowed"] = True
        else:
            # We must set correct live source tags
            lag_result["mock"] = False
            lag_result["data_source"] = "dhan_live"

            # Opportunity Adapter
            opportunity = opportunity_adapter.from_lag_result(lag_result)
            print(f"opportunity: {opportunity.to_dict() if opportunity else None}")
            if opportunity is None:
                report["opportunity_none"] = True
                report["validation_invalid"] = True
                report["candidate_none"] = True
                report["not_feasible"] = True
                report["entry_decision_not_buy_allowed"] = True
            else:
                # Validate Opportunity
                validation_result = opportunity_validator.validate(opportunity)
                print(f"validation_result: {validation_result}")
                if not validation_result.get("is_valid", False):
                    report["validation_invalid"] = True
                    report["candidate_none"] = True
                    report["not_feasible"] = True
                    report["entry_decision_not_buy_allowed"] = True
                else:
                    # Factory PaperTradeCandidate
                    candidate = candidate_factory.from_validated_opportunity(validation_result)
                    print(f"candidate: {candidate.to_dict() if candidate else None}")
                    if candidate is None:
                        report["candidate_none"] = True
                        report["not_feasible"] = True
                        report["entry_decision_not_buy_allowed"] = True
                    else:
                        # Feasibility result
                        feasibility_result = feasibility_adapter.from_candidate(candidate)
                        print(f"feasibility_result: {feasibility_result}")
                        if not feasibility_result.get("is_feasible", False):
                            report["not_feasible"] = True
                            report["entry_decision_not_buy_allowed"] = True
                        
                        # Entry decision
                        entry_decision = simulator.create_entry_decision(
                            candidate,
                            quantity=10,
                            price=quote_tgt_2.get("last_price")
                        )
                        print(f"entry_decision: {entry_decision.to_dict() if entry_decision else None}")
                        if entry_decision is None or entry_decision.action != "BUY_ALLOWED":
                            report["entry_decision_not_buy_allowed"] = True
    else:
        # Cascade Nones/failures
        report["no_price_movement"] = True
        report["lag_result_none"] = True
        report["opportunity_none"] = True
        report["validation_invalid"] = True
        report["candidate_none"] = True
        report["not_feasible"] = True
        report["entry_decision_not_buy_allowed"] = True

    # Calculate final readiness score
    res = score_readiness(report)

    print("\n" + "="*50)
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
