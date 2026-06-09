import sys
import pprint
from connectors.dhan_connector import DhanConnector
from ai.market_event import MarketEvent
from ai.quote_freshness_validator import QuoteFreshnessValidator

# Candidate instruments
CANDIDATES = [
    {"symbol": "SETFNIF50", "exchange": "NSE_EQ", "security_id": 10176},
    {"symbol": "HDFCNEXT50", "exchange": "NSE_EQ", "security_id": 10619},
    {"symbol": "MOVALUE", "exchange": "NSE_EQ", "security_id": 10825},
    {"symbol": "HDFCVALUE", "exchange": "NSE_EQ", "security_id": 11260},
    {"symbol": "HDFCNIFTY", "exchange": "NSE_EQ", "security_id": 11591},
    {"symbol": "NIFTYBEES", "exchange": "NSE_EQ", "security_id": 10576}
]

def timestamp_gap_seconds(timestamp_a, timestamp_b):
    """
    Local helper to calculate absolute seconds gap between two timestamps.
    Uses QuoteFreshnessValidator.parse_timestamp() internally.
    Returns absolute seconds gap, or None if invalid.
    """
    validator = QuoteFreshnessValidator()
    dt_a = validator.parse_timestamp(timestamp_a)
    dt_b = validator.parse_timestamp(timestamp_b)
    if dt_a is None or dt_b is None:
        return None
    return abs((dt_a - dt_b).total_seconds())

def main():
    print("=== BATCH TIMESTAMP ALIGNED PAIR SCANNER ===")
    
    # 1. Use DhanConnector.get_last_prices("NSE_EQ", security_ids)
    exchange = "NSE_EQ"
    security_ids = [c["security_id"] for c in CANDIDATES]
    
    connector = DhanConnector()
    print(f"\nFetching batch quotes for security IDs: {security_ids}")
    
    quotes = []
    errors = []
    
    try:
        result = connector.get_last_prices(exchange, security_ids)
        quotes = result.get("quotes", [])
        errors = result.get("errors", [])
        print("Batch quote fetch call completed successfully.")
    except Exception as e:
        print(f"Batch quote fetch failed with exception: {e}")
        # Proceed with empty lists to avoid crash
        quotes = []
        errors = []

    # 2. Map returned quotes back to their symbols.
    # 3. Convert each returned quote into MarketEvent.
    candidate_map = {c["security_id"]: c for c in CANDIDATES}
    events = []
    
    for q in quotes:
        sec_id = q.get("security_id")
        cand = candidate_map.get(sec_id)
        if not cand:
            continue
        symbol = cand["symbol"]
        
        # Make a copy and enrich it
        quote_data = q.copy()
        quote_data["symbol"] = symbol
        quote_data["mock"] = False
        quote_data["data_source"] = "dhan_live"
        
        event = MarketEvent.from_quote(quote_data)
        events.append((cand, event))
        
    print(f"\nConverted {len(events)} returned quotes into MarketEvents.")
    if errors:
        print(f"Errors returned from connector: {errors}")

    # 4. Compare every possible pair using QuoteFreshnessValidator.timestamps_close
    validator = QuoteFreshnessValidator()
    aligned_pairs = []
    
    print("\n=== All Checked Pairs ===")
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            cand_a, event_a = events[i]
            cand_b, event_b = events[j]
            
            is_close = validator.timestamps_close(
                event_a.timestamp,
                event_b.timestamp,
                max_gap_seconds=10
            )
            
            gap = timestamp_gap_seconds(event_a.timestamp, event_b.timestamp)
            
            # Print each checked pair
            print(f"Pair: {cand_a['symbol']} vs {cand_b['symbol']}")
            print(f"  timestamp_a: {event_a.timestamp}")
            print(f"  timestamp_b: {event_b.timestamp}")
            print(f"  timestamps_close: {is_close}")
            print(f"  timestamp_gap_seconds: {gap}")
            print("-" * 40)
            
            if is_close:
                aligned_pairs.append({
                    "reference": {
                        "symbol": cand_a["symbol"],
                        "exchange": cand_a["exchange"],
                        "security_id": cand_a["security_id"],
                        "price": event_a.price,
                        "volume": event_a.volume,
                        "timestamp": event_a.timestamp
                    },
                    "target": {
                        "symbol": cand_b["symbol"],
                        "exchange": cand_b["exchange"],
                        "security_id": cand_b["security_id"],
                        "price": event_b.price,
                        "volume": event_b.volume,
                        "timestamp": event_b.timestamp
                    },
                    "timestamp_gap_seconds": gap
                })

    # Print summary lists as requested
    print("\n" + "="*50)
    print("BATCH_QUOTES_RETURNED:")
    pprint.pprint(quotes)
    
    print("\nALIGNED_PAIRS:")
    pprint.pprint(aligned_pairs)
    
    print("\nREADY_FOR_LIVE_READINESS_TEST:")
    if len(aligned_pairs) > 0:
        print("READY_FOR_LIVE_READINESS_TEST: YES")
        first_pair = aligned_pairs[0]
        print(f"Recommended pair = {first_pair['reference']['symbol']} - {first_pair['target']['symbol']}")
    else:
        print("READY_FOR_LIVE_READINESS_TEST: NO")
    print("="*50)

if __name__ == "__main__":
    main()
