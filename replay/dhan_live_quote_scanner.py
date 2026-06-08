from connectors.dhan_connector import DhanConnector
import pprint

def main():
    print("=== DHAN LIVE QUOTE RELIABILITY SCANNER ===")
    
    watchlist = [
        {"symbol": "NIFTYBEES", "exchange": "NSE_EQ", "security_id": 10576},
        {"symbol": "HDFCNIFTY", "exchange": "NSE_EQ", "security_id": 11591},
        {"symbol": "BANKBEES", "exchange": "NSE_EQ", "security_id": 11439},
        {"symbol": "JUNIORBEES", "exchange": "NSE_EQ", "security_id": 10939},
        {"symbol": "LIQUIDBEES", "exchange": "NSE_EQ", "security_id": 11006}
    ]

    connector = DhanConnector()
    working = []
    failed = []

    for item in watchlist:
        symbol = item["symbol"]
        exchange = item["exchange"]
        security_id = item["security_id"]
        
        print(f"\nScanning {symbol} (Security ID: {security_id})...")
        try:
            quote = connector.get_last_price(exchange, security_id)
            quote["symbol"] = symbol
            print("RESULT: SUCCESS")
            print("Quote data:")
            pprint.pprint(quote)
            working.append(item)
        except Exception as e:
            print("RESULT: FAIL")
            print(f"Error: {e}")
            failed.append(item)

    print("\n" + "="*50)
    print("WORKING_INSTRUMENTS:")
    pprint.pprint([w["symbol"] for w in working])
    
    print("\nFAILED_INSTRUMENTS:")
    pprint.pprint([f["symbol"] for f in failed])

    print("\n" + "="*50)
    if len(working) >= 2:
        print("READY_FOR_PAIR_TEST: YES")
        print(f"First working pair: {working[0]['symbol']} ({working[0]['security_id']}) and {working[1]['symbol']} ({working[1]['security_id']})")
    else:
        print("READY_FOR_PAIR_TEST: NO")
        print("Need at least two live-working instruments.")
    print("="*50)

if __name__ == "__main__":
    main()
