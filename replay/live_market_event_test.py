import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from connectors.dhan_connector import DhanConnector
from ai.market_event import MarketEvent

def main():
    connector = DhanConnector()
    
    # 1. Fetch NIFTYBEES live quote using DhanConnector
    response = connector.get_quote("NSE_EQ", 10576)
    
    if response.get("status") == "success":
        q_data = response["data"]["data"]["NSE_EQ"]["10576"]
        
        # 2. Convert quote into the parsed quote format used by monitor_live_inefficiencies.py
        buy_depth = q_data.get("depth", {}).get("buy", [])
        sell_depth = q_data.get("depth", {}).get("sell", [])
        
        parsed_quote = {
            "symbol": "NIFTYBEES",
            "last_price": q_data.get("last_price", 0.0),
            "volume": q_data.get("volume", 0),
            "last_trade_time": q_data.get("last_trade_time", ""),
            "id": 10576,
            "exchange": "NSE_EQ",
            "bid": buy_depth[0].get("price", 0.0) if buy_depth else q_data.get("last_price", 0.0),
            "ask": sell_depth[0].get("price", 0.0) if sell_depth else q_data.get("last_price", 0.0),
            "avg_price": q_data.get("average_price", 0.0)
        }
        
        # 3. Convert parsed quote into MarketEvent
        event = MarketEvent.from_quote(parsed_quote)
        
        # 4. Print event.to_dict()
        print("MarketEvent Dictionary:")
        import pprint
        pprint.pprint(event.to_dict())
    else:
        print("Failed to retrieve quote:", response)

if __name__ == "__main__":
    main()
