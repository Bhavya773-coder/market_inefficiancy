import pprint
from ai.live_dhan_pair_selector import LiveDhanPairSelector

def main():
    print("=== LIVE DHAN PAIR SELECTOR TEST ===")
    
    candidates = [
        {"symbol": "SETFNIF50", "exchange": "NSE_EQ", "security_id": 10176},
        {"symbol": "HDFCNEXT50", "exchange": "NSE_EQ", "security_id": 10619},
        {"symbol": "MOVALUE", "exchange": "NSE_EQ", "security_id": 10825},
        {"symbol": "HDFCVALUE", "exchange": "NSE_EQ", "security_id": 11260},
        {"symbol": "HDFCNIFTY", "exchange": "NSE_EQ", "security_id": 11591},
        {"symbol": "NIFTYBEES", "exchange": "NSE_EQ", "security_id": 10576}
    ]
    
    selector = LiveDhanPairSelector()
    result = selector.select_pair(candidates)
    
    print("\nPAIR SELECTOR RESULT:")
    print(f"ready: {result['ready']}")
    
    working_symbols = [item["config"]["symbol"] for item in result["working"]]
    print(f"working symbols: {working_symbols}")
    
    failed_symbols = [item["config"]["symbol"] for item in result["failed"]]
    print(f"failed symbols: {failed_symbols}")
    
    print("\nselected reference:")
    pprint.pprint(result["reference"])
    
    print("\nselected target:")
    pprint.pprint(result["target"])

if __name__ == "__main__":
    main()
