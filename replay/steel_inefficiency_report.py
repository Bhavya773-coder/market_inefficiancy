from connectors.mock_steel_connector import MockSteelConnector
from inefficiency.round_trip_cost_engine import RoundTripCostEngine
from inefficiency.inefficiency_opportunity_adapter import (
    InefficiencyOpportunityAdapter
)

connector = MockSteelConnector()
cost_engine = RoundTripCostEngine()
adapter = InefficiencyOpportunityAdapter()

print("=== STEEL INEFFICIENCY REPORT ===")
print("")

opportunities = []

for _ in range(20):

    quote = connector.get_quote()

    costs = cost_engine.calculate(
        buy_price=quote["price_a"],
        sell_price=quote["price_b"],
        quantity=1,
        buy_brokerage=50,
        sell_brokerage=50,
        exchange_charges=25,
        clearing_charges=10,
        buy_tax=100,
        sell_tax=100,
        slippage=50,
        funding_cost=100
    )

    opp = adapter.from_market_pair(
        asset=quote["asset"],
        market_a=quote["market_a"],
        market_b=quote["market_b"],
        market_a_price=quote["price_a"],
        market_b_price=quote["price_b"],
        fees=costs["total_round_trip_cost"]
    )

    d = opp.to_dict()
    d["round_trip"] = costs

    opportunities.append(d)

opportunities.sort(
    key=lambda x: x["metadata"]["net_spread"],
    reverse=True
)

for d in opportunities[:10]:

    meta = d["metadata"]
    rt = d["round_trip"]

    print(f"{d['asset']} | {meta['market_a']} -> {meta['market_b']}")
    print("Buy Price:", meta["market_a_price"])
    print("Sell Price:", meta["market_b_price"])
    print("Gross Spread:", round(meta["gross_spread"], 2))
    print("Round Trip Cost:", round(rt["total_round_trip_cost"], 2))
    print("Net Profit:", round(meta["net_spread"], 2))
    print("Profit %:", round(meta["profit_pct"], 4))
    print("Confidence:", round(d["confidence"], 4))
    print("Profitable:", meta["is_profitable"])
    print("-" * 50)
