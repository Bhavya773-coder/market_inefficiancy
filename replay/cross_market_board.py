from itertools import permutations

from inefficiency.market_universe import MARKETS
from inefficiency.round_trip_cost_engine import RoundTripCostEngine

cost_engine = RoundTripCostEngine()

print()
print("=== EXECUTABLE CROSS MARKET INEFFICIENCY BOARD ===")
print()

opportunities = []

for buy, sell in permutations(MARKETS, 2):

    executable_qty = min(
        buy["available_qty"],
        sell["available_qty"]
    )

    settlement_days = max(
        buy["settlement_days"],
        sell["settlement_days"]
    )

    costs = cost_engine.calculate(
        buy_price=buy["price"],
        sell_price=sell["price"],
        quantity=1,
        buy_brokerage=50,
        sell_brokerage=50,
        exchange_charges=25,
        clearing_charges=10,
        buy_tax=100,
        sell_tax=100,
        stamp_duty=25,
        fx_spread=100,
        slippage=75,
        funding_cost=150,
        freight=800,
        warehouse_cost=100,
        handling_cost=100,
        hedging_cost=150
    )

    net_profit_per_unit = costs["net_profit"]
    total_net_profit = net_profit_per_unit * executable_qty
    capital_required = buy["price"] * executable_qty

    if capital_required > 0:
        return_on_capital_pct = (
            total_net_profit / capital_required
        ) * 100
    else:
        return_on_capital_pct = 0.0

    if settlement_days > 0:
        annualized_return_pct = (
            return_on_capital_pct
            * 365
            / settlement_days
        )
    else:
        annualized_return_pct = 0.0

    opportunities.append({
        "asset": buy["asset"],
        "buy_market": buy["market"],
        "sell_market": sell["market"],
        "buy_price": buy["price"],
        "sell_price": sell["price"],
        "executable_qty": executable_qty,
        "settlement_days": settlement_days,
        "net_profit_per_unit": net_profit_per_unit,
        "total_net_profit": total_net_profit,
        "capital_required": capital_required,
        "return_on_capital_pct": return_on_capital_pct,
        "annualized_return_pct": annualized_return_pct,
        "profitable": costs["is_profitable_after_round_trip"]
    })

opportunities.sort(
    key=lambda x: x["total_net_profit"],
    reverse=True
)

for o in opportunities:

    print(
        o["asset"],
        "| BUY:",
        o["buy_market"],
        "| SELL:",
        o["sell_market"]
    )

    print("Buy Price:", o["buy_price"])
    print("Sell Price:", o["sell_price"])
    print("Executable Qty:", o["executable_qty"])
    print("Settlement Days:", o["settlement_days"])
    print("Net Profit / Unit:", round(o["net_profit_per_unit"], 2))
    print("Total Net Profit:", round(o["total_net_profit"], 2))
    print("Capital Required:", round(o["capital_required"], 2))
    print("Return on Capital %:", round(o["return_on_capital_pct"], 4))
    print("Annualized Return %:", round(o["annualized_return_pct"], 4))
    print("Profitable:", o["profitable"])
    print("-" * 60)
