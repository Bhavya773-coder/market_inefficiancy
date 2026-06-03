import sys
import os
import time
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from connectors.dhan_connector import DhanConnector
from inefficiency.round_trip_cost_engine import RoundTripCostEngine

def monitor():
    print("==========================================================")
    print("   LIVE NIFTY 50 ETF STATISTICAL INEFFICIENCY MONITOR   ")
    print("==========================================================")
    print("Monitoring started. Polling every 5 seconds... Press Ctrl+C to stop.\n")

    connector = DhanConnector()
    cost_engine = RoundTripCostEngine()

    etfs = [
        {"id": 10576, "symbol": "NIFTYBEES"},
        {"id": 11591, "symbol": "HDFCNIFTY"},
        {"id": 21252, "symbol": "AXISNIFTY"},
        {"id": 6353, "symbol": "NIFTYETF"},
    ]

    securities = {
        "NSE_EQ": [etf["id"] for etf in etfs]
    }

    try:
        while True:
            response = connector.dhan.quote_data(securities)
            if response.get("status") == "success":
                data = response["data"]["data"]["NSE_EQ"]
                
                quotes = {}
                for etf in etfs:
                    q_id = str(etf["id"])
                    if q_id in data:
                        q_data = data[q_id]
                        buy_depth = q_data.get("depth", {}).get("buy", [])
                        sell_depth = q_data.get("depth", {}).get("sell", [])
                        
                        quotes[etf["symbol"]] = {
                            "symbol": etf["symbol"],
                            "last_price": q_data.get("last_price", 0.0),
                            "avg_price": q_data.get("average_price", 0.0),
                            "bid": buy_depth[0].get("price", 0.0) if buy_depth else q_data.get("last_price", 0.0),
                            "ask": sell_depth[0].get("price", 0.0) if sell_depth else q_data.get("last_price", 0.0),
                        }
                
                ref_symbol = "NIFTYBEES"
                if ref_symbol in quotes and quotes[ref_symbol]["last_price"] > 0:
                    ref = quotes[ref_symbol]
                    timestamp = time.strftime('%H:%M:%S')
                    
                    max_dev_symbol = None
                    max_dev_pct = 0.0
                    
                    for symbol, q in quotes.items():
                        if symbol == ref_symbol or q["last_price"] == 0 or q["avg_price"] == 0 or ref["avg_price"] == 0:
                            continue
                        
                        base_ratio = q["avg_price"] / ref["avg_price"]
                        curr_ratio = q["last_price"] / ref["last_price"]
                        deviation_pct = ((curr_ratio - base_ratio) / base_ratio) * 100
                        
                        if abs(deviation_pct) > abs(max_dev_pct):
                            max_dev_pct = deviation_pct
                            max_dev_symbol = symbol
                    
                    print(f"[{timestamp}] Ref: {ref['last_price']:.2f} | Max Dev: {max_dev_symbol} ({max_dev_pct:+.4f}%)")
                    
                    # If max deviation exceeds 0.10%, print detailed alert
                    if abs(max_dev_pct) >= 0.10:
                        q = quotes[max_dev_symbol]
                        print(f"  --> ALERT: Significant deviation on {max_dev_symbol}!")
                        print(f"      Bid: {q['bid']:.2f} | Ask: {q['ask']:.2f}")
            else:
                print("Failed to fetch live quotes:", response)
                
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
    except Exception as e:
        print("\nAn error occurred during monitoring:", e)

if __name__ == "__main__":
    monitor()
