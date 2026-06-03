import sys
import os
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from connectors.dhan_connector import DhanConnector
from ai.market_event import MarketEvent
from ai.market_event_store import MarketEventStore
from ai.price_change_detector import PriceChangeDetector
from ai.reaction_event import ReactionEvent

def get_niftybees_event(connector):
    response = connector.get_quote("NSE_EQ", 10576)
    if response.get("status") != "success":
        raise Exception(f"Failed to fetch NIFTYBEES quote: {response}")
        
    q_data = response["data"]["data"]["NSE_EQ"]["10576"]
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
    return MarketEvent.from_quote(parsed_quote)

def main():
    print("Initializing DhanConnector and MarketEventStore...")
    connector = DhanConnector()
    store = MarketEventStore()
    detector = PriceChangeDetector()
    
    # 1. Fetch NIFTYBEES live quote using DhanConnector
    print("Fetching first quote...")
    event_1 = get_niftybees_event(connector)
    print(f"First Quote Price: {event_1.price} at {event_1.timestamp}")
    
    # 3. Store it in MarketEventStore
    store.add(event_1)
    
    # 4. Wait 5 seconds
    print("Waiting 5 seconds...")
    time.sleep(5)
    
    # 5. Fetch NIFTYBEES live quote again
    print("Fetching second quote...")
    event_2 = get_niftybees_event(connector)
    print(f"Second Quote Price: {event_2.price} at {event_2.timestamp}")
    
    # 6. Convert second quote into MarketEvent & add to store
    store.add(event_2)
    
    # 7. Compare first and second MarketEvent using PriceChangeDetector
    print("Comparing events...")
    change = detector.detect(event_2, event_1)
    
    if change:
        # 8. Convert price change into ReactionEvent
        reaction = ReactionEvent.from_price_change(change)
        
        # 9. Print ReactionEvent.to_dict()
        print("\nReactionEvent Dictionary:")
        import pprint
        pprint.pprint(reaction.to_dict())
    else:
        print("No change detected or comparison failed.")

if __name__ == "__main__":
    main()
