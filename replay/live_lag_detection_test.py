import sys
import os
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from connectors.dhan_connector import DhanConnector
from ai.market_event import MarketEvent
from ai.price_change_detector import PriceChangeDetector
from ai.reaction_event import ReactionEvent
from ai.lag_detector import LagDetector

def get_market_event(connector, symbol, security_id):
    response = connector.get_quote("NSE_EQ", security_id)
    if response.get("status") != "success":
        raise Exception(f"Failed to fetch {symbol} quote: {response}")
        
    q_data = response["data"]["data"]["NSE_EQ"][str(security_id)]
    buy_depth = q_data.get("depth", {}).get("buy", [])
    sell_depth = q_data.get("depth", {}).get("sell", [])
    
    parsed_quote = {
        "symbol": symbol,
        "last_price": q_data.get("last_price", 0.0),
        "volume": q_data.get("volume", 0),
        "last_trade_time": q_data.get("last_trade_time", ""),
        "id": security_id,
        "exchange": "NSE_EQ",
        "bid": buy_depth[0].get("price", 0.0) if buy_depth else q_data.get("last_price", 0.0),
        "ask": sell_depth[0].get("price", 0.0) if sell_depth else q_data.get("last_price", 0.0),
        "avg_price": q_data.get("average_price", 0.0)
    }
    return MarketEvent.from_quote(parsed_quote)

def main():
    print("Initializing DhanConnector...")
    connector = DhanConnector()
    change_detector = PriceChangeDetector()
    lag_detector = LagDetector()
    
    # 1 & 2. Fetch first quotes
    print("Fetching first quotes for NIFTYBEES and HDFCNIFTY...")
    ref_event_1 = get_market_event(connector, "NIFTYBEES", 10576)
    target_event_1 = get_market_event(connector, "HDFCNIFTY", 11591)
    
    print(f"  NIFTYBEES T1: {ref_event_1.price}")
    print(f"  HDFCNIFTY T1: {target_event_1.price}")
    
    # 4. Wait 5 seconds
    print("Waiting 5 seconds...")
    time.sleep(5)
    
    # 5 & 6. Fetch second quotes
    print("Fetching second quotes for NIFTYBEES and HDFCNIFTY...")
    ref_event_2 = get_market_event(connector, "NIFTYBEES", 10576)
    target_event_2 = get_market_event(connector, "HDFCNIFTY", 11591)
    
    print(f"  NIFTYBEES T2: {ref_event_2.price}")
    print(f"  HDFCNIFTY T2: {target_event_2.price}")
    
    # 8. Use PriceChangeDetector to calculate both reactions
    print("Calculating price changes...")
    ref_change = change_detector.detect(ref_event_2, ref_event_1)
    target_change = change_detector.detect(target_event_2, target_event_1)
    
    # 9. Convert both changes into ReactionEvent
    ref_reaction = ReactionEvent.from_price_change(ref_change)
    target_reaction = ReactionEvent.from_price_change(target_change)
    
    # 10. Use LagDetector to compare NIFTYBEES vs HDFCNIFTY
    # We will use a low gap threshold (e.g. 0.005%) to catch tiny live differences
    print("Running lag detection...")
    lag_result = lag_detector.detect(ref_reaction, target_reaction, min_gap_percent=0.005)
    
    # 11. Print results
    print("\nReference Reaction Event:")
    import pprint
    pprint.pprint(ref_reaction.to_dict())
    
    print("\nTarget Reaction Event:")
    pprint.pprint(target_reaction.to_dict())
    
    print("\nLag Result (min_gap_percent=0.005):")
    pprint.pprint(lag_result)

if __name__ == "__main__":
    main()
