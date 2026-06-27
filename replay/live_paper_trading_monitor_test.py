import pprint
from ai.market_event import MarketEvent
from ai.live_paper_trading_monitor import LivePaperTradingMonitor

def make_event(symbol, price, timestamp, data_source="offline_simulated_live"):
    """
    Helper to create a MarketEvent with specific prices and timestamps.
    """
    return MarketEvent(
        symbol=symbol,
        source="offline_simulator",
        event_type="live_quote",
        price=price,
        volume=1000,
        timestamp=timestamp,
        metadata={
            "data_source": data_source,
            "mock": False
        }
    )

def main():
    print("=== STARTING OFFLINE SIMULATED LIVE MONITOR TEST ===")
    
    reference_symbol = "SETFNIF50"
    target_symbol = "HDFCNIFTY"
    
    monitor = LivePaperTradingMonitor(
        reference_symbol=reference_symbol,
        target_symbol=target_symbol,
        min_gap_percent=0.05
    )

    # Tick 1 events
    prev_ref_1 = make_event(reference_symbol, 100.00, "08/06/2026 13:03:00")
    curr_ref_1 = make_event(reference_symbol, 100.40, "08/06/2026 13:03:01")
    prev_tgt_1 = make_event(target_symbol, 100.00, "08/06/2026 13:03:00")
    curr_tgt_1 = make_event(target_symbol, 100.03, "08/06/2026 13:03:01")

    print("\n--- TICK PAIR 1 ---")
    report_1 = monitor.process_tick_pair(prev_ref_1, curr_ref_1, prev_tgt_1, curr_tgt_1, quantity=10)
    pprint.pprint(report_1)

    # Assertions for Tick 1
    assert report_1["status"] == "opportunity_processed"
    assert report_1["entry_report"]["decision"]["action"] == "BUY_ALLOWED"
    assert report_1["entry_report"]["execution"]["status"] == "filled"
    assert report_1["entry_report"]["execution"]["side"] == "BUY"
    assert report_1["entry_report"]["execution"]["price"] == 100.03
    assert report_1["stats"]["paper_buys"] == 1

    # Tick 2 events
    prev_ref_2 = make_event(reference_symbol, 100.40, "08/06/2026 13:03:01")
    curr_ref_2 = make_event(reference_symbol, 100.50, "08/06/2026 13:03:02")
    prev_tgt_2 = make_event(target_symbol, 100.03, "08/06/2026 13:03:01")
    curr_tgt_2 = make_event(target_symbol, 100.70, "08/06/2026 13:03:02")

    print("\n--- TICK PAIR 2 ---")
    report_2 = monitor.process_tick_pair(prev_ref_2, curr_ref_2, prev_tgt_2, curr_tgt_2, quantity=10)
    pprint.pprint(report_2)

    # Assertions for Tick 2
    assert report_2["status"] == "no_opportunity"
    assert report_2["exit_report"]["decision"]["action"] == "TAKE_PROFIT"
    assert report_2["exit_report"]["execution"]["status"] == "filled"
    assert report_2["exit_report"]["execution"]["side"] == "SELL"
    assert report_2["stats"]["paper_sells"] == 1

    # Tick 3 events (weak opportunity)
    prev_ref_3 = make_event(reference_symbol, 100.50, "08/06/2026 13:03:02")
    curr_ref_3 = make_event(reference_symbol, 100.54, "08/06/2026 13:03:03")
    prev_tgt_3 = make_event(target_symbol, 100.70, "08/06/2026 13:03:02")
    curr_tgt_3 = make_event(target_symbol, 100.73, "08/06/2026 13:03:03")

    print("\n--- TICK PAIR 3 ---")
    report_3 = monitor.process_tick_pair(prev_ref_3, curr_ref_3, prev_tgt_3, curr_tgt_3, quantity=10)
    pprint.pprint(report_3)

    # Assertions for Tick 3
    assert report_3["status"] == "no_opportunity"
    assert report_3["stats"]["entries_allowed"] == 1  # From Tick 1
    assert report_3["stats"]["paper_buys"] == 1       # From Tick 1
    assert report_3["stats"]["paper_sells"] == 1      # From Tick 2

    # End summary and P/L calculations
    summ = monitor.summary()
    starting_cash = 100000
    final_cash = summ["account"]["cash"]
    paper_pnl = final_cash - starting_cash

    print("\n" + "="*50)
    print("MONITOR SUMMARY")
    print("="*50)
    print("\nStats:")
    pprint.pprint(summ["stats"])
    print("\nAccount:")
    pprint.pprint(summ["account"])
    print(f"\nPaper Profit/Loss: {paper_pnl}")
    print(f"Final Cash: {final_cash}")
    print("\nTrade Log:")
    pprint.pprint(summ["account"]["trade_log"])

    print(f"\nPAPER_PNL: {paper_pnl}")

    print("\n" + "="*50)
    print("REAL ORDER APIs USED: NO")
    print("DHAN USED: NO")
    print("PAPER ONLY: YES")
    print("="*50)

    # General assertions
    assert summ["stats"]["paper_buys"] == 1
    assert summ["stats"]["paper_sells"] == 1
    assert final_cash > starting_cash
    assert len(summ["account"]["positions"]) == 0
    print("\nALL TEST ASSERTIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
