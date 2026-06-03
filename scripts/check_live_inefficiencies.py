import sys
import os
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from connectors.dhan_connector import DhanConnector
from inefficiency.round_trip_cost_engine import RoundTripCostEngine

def main():
    print("==========================================================")
    print("   LIVE NIFTY 50 ETF STATISTICAL INEFFICIENCY DETECTOR   ")
    print("==========================================================")

    # Initialize connector and cost engine
    connector = DhanConnector()
    cost_engine = RoundTripCostEngine()

    # Nifty 50 ETFs (excluding the 1/1000th scale BSLNIFTY for cleaner ratio mapping)
    etfs = [
        {"id": 10576, "symbol": "NIFTYBEES", "role": "Reference"},
        {"id": 11591, "symbol": "HDFCNIFTY", "role": "Target"},
        {"id": 21252, "symbol": "AXISNIFTY", "role": "Target"},
        {"id": 6353, "symbol": "NIFTYETF", "role": "Target"},
    ]

    securities = {
        "NSE_EQ": [etf["id"] for etf in etfs]
    }

    try:
        response = connector.dhan.quote_data(securities)
        if response.get("status") == "success":
            data = response["data"]["data"]["NSE_EQ"]
            
            # Extract quote data
            quotes = {}
            for etf in etfs:
                q_id = str(etf["id"])
                if q_id in data:
                    q_data = data[q_id]
                    buy_depth = q_data.get("depth", {}).get("buy", [])
                    sell_depth = q_data.get("depth", {}).get("sell", [])
                    
                    quotes[etf["symbol"]] = {
                        "symbol": etf["symbol"],
                        "id": etf["id"],
                        "last_price": q_data.get("last_price", 0.0),
                        "avg_price": q_data.get("average_price", 0.0),
                        "volume": q_data.get("volume", 0),
                        "bid": buy_depth[0].get("price", 0.0) if buy_depth else q_data.get("last_price", 0.0),
                        "ask": sell_depth[0].get("price", 0.0) if sell_depth else q_data.get("last_price", 0.0),
                        "last_trade_time": q_data.get("last_trade_time", "N/A")
                    }
            
            ref_symbol = "NIFTYBEES"
            if ref_symbol not in quotes or quotes[ref_symbol]["last_price"] == 0:
                print("Reference asset NIFTYBEES quote is not available.")
                return

            ref = quotes[ref_symbol]
            print(f"\nReference Asset: {ref_symbol} | Last: {ref['last_price']:.2f} | Avg (VWAP): {ref['avg_price']:.2f}\n")
            
            print("-" * 110)
            print(f"{'Symbol':<12} | {'Last Price':<10} | {'Bid':<10} | {'Ask':<10} | {'VWAP':<10} | {'Base Ratio':<10} | {'Curr Ratio':<10} | {'Deviation %':<12} | {'Volume':<10}")
            print("-" * 110)

            deviations = []

            for symbol, q in quotes.items():
                if symbol == ref_symbol:
                    # Self comparison
                    print(f"{symbol:<12} | {q['last_price']:<10.2f} | {q['bid']:<10.2f} | {q['ask']:<10.2f} | {q['avg_price']:<10.2f} | {1.0:<10.4f} | {1.0:<10.4f} | {0.0:<12.4f} | {q['volume']:<10}")
                    continue

                if q["last_price"] == 0 or q["avg_price"] == 0 or ref["avg_price"] == 0:
                    continue

                # Base Ratio = daily average price ratio
                base_ratio = q["avg_price"] / ref["avg_price"]
                # Current Ratio = last price ratio
                curr_ratio = q["last_price"] / ref["last_price"]
                # Deviation percentage
                deviation_pct = ((curr_ratio - base_ratio) / base_ratio) * 100
                
                print(f"{symbol:<12} | {q['last_price']:<10.2f} | {q['bid']:<10.2f} | {q['ask']:<10.2f} | {q['avg_price']:<10.2f} | {base_ratio:<10.4f} | {curr_ratio:<10.4f} | {deviation_pct:<+12.4f} | {q['volume']:<10}")
                
                deviations.append({
                    "symbol": symbol,
                    "quote": q,
                    "base_ratio": base_ratio,
                    "curr_ratio": curr_ratio,
                    "deviation_pct": deviation_pct
                })
            print("-" * 110)

            # Analyze opportunities
            print("\n>>> INEFFICIENCY ANALYSIS <<<")
            opportunities_found = 0

            for dev in deviations:
                symbol = dev["symbol"]
                q = dev["quote"]
                dev_pct = dev["deviation_pct"]

                # If deviation is positive, the target ETF is overvalued relative to NIFTYBEES (Sell Target, Buy NIFTYBEES)
                # If deviation is negative, the target ETF is undervalued relative to NIFTYBEES (Buy Target, Sell NIFTYBEES)
                threshold = 0.10 # 0.10% threshold for alert
                
                if abs(dev_pct) >= threshold:
                    opportunities_found += 1
                    direction = "OVERVALUED (Short Target / Long Reference)" if dev_pct > 0 else "UNDERVALUED (Long Target / Short Reference)"
                    print(f"\n[!] ALERT: Significant deviation detected in {symbol} ({dev_pct:+.3f}%)")
                    print(f"    Direction: {direction}")
                    
                    # Calculate simulated spread execution
                    if dev_pct > 0:
                        # Short target (at bid), Long reference (at ask)
                        # We adjust for the price scale ratio
                        target_sell_price = q["bid"]
                        ref_buy_price = ref["ask"]
                        scaled_ref_buy_price = ref_buy_price * dev["base_ratio"]
                        gross_spread = target_sell_price - scaled_ref_buy_price
                    else:
                        # Long target (at ask), Short reference (at bid)
                        target_buy_price = q["ask"]
                        ref_sell_price = ref["bid"]
                        scaled_ref_sell_price = ref_sell_price * dev["base_ratio"]
                        gross_spread = scaled_ref_sell_price - target_buy_price

                    gross_spread_pct = (gross_spread / q["last_price"]) * 100
                    
                    print(f"    Estimated Gross Spread per unit: {gross_spread:+.4f} ({gross_spread_pct:+.3f}%)")
                    
                    # Run round trip cost engine
                    # Let's say we trade a volume of 1,000 units
                    qty = 1000
                    buy_p = q["ask"] if dev_pct < 0 else ref["ask"] * dev["base_ratio"]
                    sell_p = ref["bid"] * dev["base_ratio"] if dev_pct < 0 else q["bid"]
                    
                    costs = cost_engine.calculate(
                        buy_price=buy_p,
                        sell_price=sell_p,
                        quantity=qty,
                        buy_brokerage=20.0,
                        sell_brokerage=20.0,
                        exchange_charges=(buy_p + sell_p) * qty * 0.000345,
                        buy_tax=buy_p * qty * 0.001,
                        sell_tax=sell_p * qty * 0.001,
                        slippage=0.02 * qty
                    )
                    
                    print(f"    Simulated Spread Trade (size: {qty} units):")
                    print(f"      Gross Profit:             Rs. {costs['gross_spread']:.2f}")
                    print(f"      Est. Round-Trip Costs:    Rs. {costs['total_round_trip_cost']:.2f}")
                    print(f"      Net Arbitrage Profit:     Rs. {costs['net_profit']:.2f}")
                    print(f"      Net Return on Trade:      {costs['net_profit_pct']:.4f}%")
                    print(f"      Profitable after fees:    {costs['is_profitable_after_round_trip']}")
            
            if opportunities_found == 0:
                print("\nNo significant inefficiencies found above the 0.10% threshold. Spreads are currently aligned with daily averages.")

        else:
            print("Failed to fetch live quotes:", response)
    except Exception as e:
        print("An error occurred during calculation:", e)

if __name__ == "__main__":
    main()
