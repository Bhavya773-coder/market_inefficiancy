from inefficiency.liquidity_engine import LiquidityEngine

engine = LiquidityEngine()

print("=== LIQUIDITY ENGINE TEST ===")

# 1. Fully liquid: small order against deep books, no spread
result = engine.calculate(
    desired_quantity=100,
    buy_side_available_quantity=100000,
    sell_side_available_quantity=100000
)
print("deep book:", result)
assert result["executable_quantity"] == 100
assert result["fill_ratio"] == 1.0
assert result["meets_fill_requirement"] is True
assert result["is_liquidity_viable"] is True
assert result["liquidity_score"] > 0.99

# 2. Thin sell side caps the trade
result = engine.calculate(
    desired_quantity=1000,
    buy_side_available_quantity=100000,
    sell_side_available_quantity=1000,
    max_participation_rate=0.25
)
print("thin sell side:", result)
assert result["executable_quantity"] == 250  # 25% of 1000
assert abs(result["fill_ratio"] - 0.25) < 1e-9
assert result["meets_fill_requirement"] is False  # default min_fill_ratio=1.0
assert result["is_liquidity_viable"] is False

# 3. Partial fill accepted when min_fill_ratio is relaxed
result = engine.calculate(
    desired_quantity=1000,
    buy_side_available_quantity=100000,
    sell_side_available_quantity=1000,
    max_participation_rate=0.25,
    min_fill_ratio=0.2
)
print("relaxed fill:", result)
assert result["meets_fill_requirement"] is True
assert result["is_liquidity_viable"] is True

# 4. Slippage scales linearly with used participation
# Executable = 250 of 1000 available -> sell participation 0.25 = full allowed
# -> sell slippage = full configured slippage.
result = engine.calculate(
    desired_quantity=1000,
    buy_side_available_quantity=1000000,
    sell_side_available_quantity=1000,
    max_participation_rate=0.25,
    slippage_pct_at_full_participation=0.5,
    min_fill_ratio=0.0
)
print("slippage:", result)
assert abs(result["sell_slippage_pct"] - 0.5) < 1e-9
assert result["buy_slippage_pct"] < 0.001  # tiny participation on deep buy side

# 5. Spreads included in round-trip liquidity cost
result = engine.calculate(
    desired_quantity=10,
    buy_side_available_quantity=100000,
    sell_side_available_quantity=100000,
    buy_spread_pct=0.10,
    sell_spread_pct=0.15
)
print("spread cost:", result)
assert result["total_liquidity_cost_pct"] >= 0.25
assert result["liquidity_score"] < 1.0

# 6. Zero available liquidity on one leg -> nothing executable
result = engine.calculate(
    desired_quantity=100,
    buy_side_available_quantity=0,
    sell_side_available_quantity=100000,
    min_fill_ratio=0.0
)
print("no buy liquidity:", result)
assert result["executable_quantity"] == 0
assert result["is_liquidity_viable"] is False

# 7. Higher cost -> lower score (monotonicity)
cheap = engine.calculate(
    desired_quantity=10,
    buy_side_available_quantity=100000,
    sell_side_available_quantity=100000,
    buy_spread_pct=0.05, sell_spread_pct=0.05
)
expensive = engine.calculate(
    desired_quantity=10,
    buy_side_available_quantity=100000,
    sell_side_available_quantity=100000,
    buy_spread_pct=1.0, sell_spread_pct=1.0
)
print("cheap score:", cheap["liquidity_score"], "expensive score:", expensive["liquidity_score"])
assert cheap["liquidity_score"] > expensive["liquidity_score"]

# 8. Input validation
for bad_kwargs in [
    {"desired_quantity": 0, "buy_side_available_quantity": 1, "sell_side_available_quantity": 1},
    {"desired_quantity": 1, "buy_side_available_quantity": -1, "sell_side_available_quantity": 1},
    {"desired_quantity": 1, "buy_side_available_quantity": 1, "sell_side_available_quantity": -1},
    {"desired_quantity": 1, "buy_side_available_quantity": 1, "sell_side_available_quantity": 1, "max_participation_rate": 0.0},
    {"desired_quantity": 1, "buy_side_available_quantity": 1, "sell_side_available_quantity": 1, "max_participation_rate": 1.5},
    {"desired_quantity": 1, "buy_side_available_quantity": 1, "sell_side_available_quantity": 1, "slippage_pct_at_full_participation": -1},
    {"desired_quantity": 1, "buy_side_available_quantity": 1, "sell_side_available_quantity": 1, "min_fill_ratio": 1.5},
    {"desired_quantity": 1, "buy_side_available_quantity": 1, "sell_side_available_quantity": 1, "buy_spread_pct": -0.1},
]:
    try:
        engine.calculate(**bad_kwargs)
        raise AssertionError(f"expected ValueError for {bad_kwargs}")
    except ValueError:
        pass
print("input validation: OK")

print("\nALL LIQUIDITY ENGINE TESTS PASSED")
