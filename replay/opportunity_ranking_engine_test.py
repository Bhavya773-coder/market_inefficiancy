from inefficiency.opportunity_ranking_engine import OpportunityRankingEngine

engine = OpportunityRankingEngine()

print("=== OPPORTUNITY RANKING ENGINE TEST ===")


def make_candidate(**overrides):
    base = {
        "opportunity_id": "opp_base",
        "opportunity_type": "arbitrage",
        "asset": "STEEL_HRC",
        "buy_market": "India Physical",
        "sell_market": "Dubai Physical",
        "buy_price": 50000.0,
        "sell_price": 51000.0,
        "quantity": 10,
        "buy_settlement_days": 2,
        "sell_settlement_days": 2,
        "buy_side_available_quantity": 10000,
        "sell_side_available_quantity": 10000,
        "holding_period_days": 5,
        "annual_financing_rate_pct": 10.0
    }
    base.update(overrides)
    return base


# 1. Single profitable arbitrage is executable and fully explained
result = engine.evaluate(make_candidate(), available_capital=1000000)
print("single eval: net_profit =", result["net_profit"],
      "annualized =", round(result["annualized_return_pct"], 2))
assert result["is_executable"] is True
assert result["rejection_reasons"] == []
assert result["executable_quantity"] == 10
assert result["capital_required"] == 500000.0
assert result["net_profit"] > 0
# All four engine sub-results present
for key in ["cost_result", "settlement_result", "capital_result", "liquidity_result"]:
    assert isinstance(result[key], dict), key

# 2. Costs eat the spread -> rejected with explicit reason
result = engine.evaluate(make_candidate(
    opportunity_id="opp_costly",
    freight=8000.0, buy_tax=2000.0, sell_tax=2000.0
))
print("costly:", result["net_profit"], result["rejection_reasons"])
assert result["is_executable"] is False
assert "not_profitable_after_round_trip_costs" in result["rejection_reasons"]

# 3. Insufficient capital -> rejected
result = engine.evaluate(make_candidate(opportunity_id="opp_big"), available_capital=1000)
print("underfunded:", result["rejection_reasons"])
assert "insufficient_capital" in result["rejection_reasons"]

# 4. Thin market -> liquidity rejection (default min_fill_ratio=1.0)
result = engine.evaluate(make_candidate(
    opportunity_id="opp_thin",
    sell_side_available_quantity=4  # 25% participation -> 1 unit executable of 10
))
print("thin:", result["executable_quantity"], result["rejection_reasons"])
assert result["executable_quantity"] == 1.0
assert "liquidity_not_viable" in result["rejection_reasons"]

# 5. Settlement lock-up limit -> rejected
result = engine.evaluate(make_candidate(
    opportunity_id="opp_slow",
    sell_settlement_days=30,
    max_acceptable_lockup_days=14
))
print("slow settlement:", result["rejection_reasons"])
assert "settlement_not_viable" in result["rejection_reasons"]

# 6. Priority tiers: relative_value never outranks executable arbitrage,
#    even with a higher return
arb = make_candidate(opportunity_id="opp_arb", sell_price=50500.0)
rv = make_candidate(
    opportunity_id="opp_rv",
    opportunity_type="relative_value",
    sell_price=53000.0
)
ranking = engine.rank([rv, arb], available_capital=10000000)
print("tier ranking:", [e["opportunity_id"] for e in ranking["ranked"]])
assert ranking["evaluated_count"] == 2
assert len(ranking["ranked"]) == 2
assert ranking["ranked"][0]["opportunity_id"] == "opp_arb"
assert ranking["ranked"][0]["rank_score"] < ranking["ranked"][1]["rank_score"]  # tier won despite lower score

# 7. Within a tier, higher liquidity-adjusted annualized return ranks first
fast = make_candidate(opportunity_id="opp_fast", holding_period_days=1)
slow = make_candidate(opportunity_id="opp_slow_hold", holding_period_days=60)
ranking = engine.rank([slow, fast], available_capital=10000000)
print("within-tier ranking:", [e["opportunity_id"] for e in ranking["ranked"]])
assert ranking["ranked"][0]["opportunity_id"] == "opp_fast"

# 8. Rejected candidates are separated, never silently dropped
ranking = engine.rank([
    make_candidate(opportunity_id="opp_good"),
    make_candidate(opportunity_id="opp_bad", sell_price=49000.0)
], available_capital=10000000)
print("split:", len(ranking["ranked"]), "ranked,", len(ranking["rejected"]), "rejected")
assert len(ranking["ranked"]) == 1
assert len(ranking["rejected"]) == 1
assert ranking["rejected"][0]["opportunity_id"] == "opp_bad"
assert ranking["rejected"][0]["rejection_reasons"] != []

# 9. Unknown opportunity type is an explicit error
try:
    engine.evaluate(make_candidate(opportunity_type="momentum"))
    raise AssertionError("expected ValueError for unknown opportunity_type")
except ValueError:
    print("unknown type rejected: OK")

# 10. Missing required key is an explicit error
try:
    engine.evaluate({"opportunity_id": "x"})
    raise AssertionError("expected ValueError for missing keys")
except ValueError:
    print("missing keys rejected: OK")

print("\nALL OPPORTUNITY RANKING ENGINE TESTS PASSED")
