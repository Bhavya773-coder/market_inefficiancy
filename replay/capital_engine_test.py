from inefficiency.capital_engine import CapitalEngine

engine = CapitalEngine()

print("=== CAPITAL ENGINE TEST ===")

# 1. Basic return on capital and annualization
# 1000 profit on 100000 over 7 days -> 1% RoC -> 1% * 365/7 = 52.142...% annualized
result = engine.calculate(
    capital_required=100000,
    net_profit=1000,
    capital_lockup_days=7,
    available_capital=500000
)
print("basic:", result)
assert abs(result["return_on_capital_pct"] - 1.0) < 1e-9
assert abs(result["annualized_return_pct"] - (1.0 * 365.0 / 7.0)) < 1e-9
assert result["can_fund"] is True
assert abs(result["capital_utilization_pct"] - 20.0) < 1e-9
assert result["is_capital_viable"] is True

# 2. Fast small spread beats slow big spread on annualized basis
fast = engine.calculate(capital_required=100000, net_profit=400, capital_lockup_days=1)
slow = engine.calculate(capital_required=100000, net_profit=3000, capital_lockup_days=30)
print("fast:", fast["annualized_return_pct"], "slow:", slow["annualized_return_pct"])
assert fast["annualized_return_pct"] > slow["annualized_return_pct"]

# 3. Cannot fund when capital short
result = engine.calculate(
    capital_required=100000,
    net_profit=1000,
    capital_lockup_days=7,
    available_capital=50000
)
print("underfunded:", result)
assert result["can_fund"] is False
assert result["is_capital_viable"] is False

# 4. Zero lockup treated as one day (no divide-by-zero, no infinite return)
result = engine.calculate(capital_required=100000, net_profit=100, capital_lockup_days=0)
print("zero lockup:", result)
assert result["effective_lockup_days"] == 1.0
assert abs(result["annualized_return_pct"] - (0.1 * 365.0)) < 1e-9

# 5. Negative profit stays negative and fails threshold
result = engine.calculate(
    capital_required=100000,
    net_profit=-500,
    capital_lockup_days=7,
    min_annualized_return_pct=0.0
)
print("loss:", result)
assert result["return_on_capital_pct"] < 0
assert result["meets_return_threshold"] is False
assert result["is_capital_viable"] is False

# 6. Return threshold enforcement
result = engine.calculate(
    capital_required=100000,
    net_profit=100,
    capital_lockup_days=30,
    min_annualized_return_pct=10.0
)
print("below threshold:", result)
assert result["meets_return_threshold"] is False

# 7. Zero capital required
result = engine.calculate(capital_required=0, net_profit=0, capital_lockup_days=5)
print("zero capital:", result)
assert result["return_on_capital_pct"] == 0.0
assert result["annualized_return_pct"] == 0.0

# 8. Input validation
for bad_kwargs in [
    {"capital_required": -1, "net_profit": 0, "capital_lockup_days": 0},
    {"capital_required": 0, "net_profit": 0, "capital_lockup_days": -1},
    {"capital_required": 0, "net_profit": 0, "capital_lockup_days": 0, "available_capital": -1},
]:
    try:
        engine.calculate(**bad_kwargs)
        raise AssertionError(f"expected ValueError for {bad_kwargs}")
    except ValueError:
        pass
print("input validation: OK")

print("\nALL CAPITAL ENGINE TESTS PASSED")
