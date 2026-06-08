import pprint
from connectors.dhan_connector import DhanConnector
from ai.market_event import MarketEvent
from ai.quote_freshness_validator import QuoteFreshnessValidator

def main():
    print("=== DHAN BATCH QUOTE TEST ===")
    
    # Test 1: Fetch batch quotes
    exchange = "NSE_EQ"
    security_ids = [10176, 11591]
    
    connector = DhanConnector()
    print(f"\nFetching batch quotes for {security_ids}...")
    try:
        result = connector.get_last_prices(exchange, security_ids)
    except Exception as e:
        print(f"Batch quote fetch failed with exception: {e}")
        return
        
    print("\nFull Result:")
    pprint.pprint(result)
    
    quotes = result.get("quotes", [])
    errors = result.get("errors", [])
    
    print(f"\nNumber of quotes returned: {len(quotes)}")
    print(f"Errors: {errors}")
    
    # Test 2: If at least 2 quotes returned, validate freshness
    if len(quotes) >= 2:
        print("\nConverting to MarketEvents and validating timestamps...")
        
        # Standardize symbols mapping
        symbol_map = {
            10176: "SETFNIF50",
            11591: "HDFCNIFTY"
        }
        
        event_ref = None
        event_tgt = None
        
        for q in quotes:
            sec_id = q["security_id"]
            symbol = symbol_map.get(sec_id, f"UNKNOWN_{sec_id}")
            
            quote_data = q.copy()
            quote_data["symbol"] = symbol
            quote_data["mock"] = False
            quote_data["data_source"] = "dhan_live"
            
            event = MarketEvent.from_quote(quote_data)
            print(f"Created MarketEvent for {symbol}: {event.to_dict()}")
            
            if sec_id == 10176:
                event_ref = event
            elif sec_id == 11591:
                event_tgt = event
                
        if event_ref and event_tgt:
            validator = QuoteFreshnessValidator()
            is_close = validator.timestamps_close(
                event_ref.timestamp,
                event_tgt.timestamp,
                max_gap_seconds=10
            )
            print(f"\nTimestamps close (max_gap_seconds=10): {is_close}")
        else:
            print("Failed to find both reference and target events in response.")
    else:
        print("\nFewer than 2 quotes returned. Skipping Test 2.")

if __name__ == "__main__":
    main()
