from inefficiency.settlement_engine import SettlementEngine

engine = SettlementEngine()

print("=== SETTLEMENT ENGINE TEST ===")

# 1. Basic lock-up and financing cost
# Hold 5 days, sell settles T+2 -> capital locked 7 days.
# 100000 at 12% annual = 100000 * (0.12/365) * 7 = 230.136...
result = engine.calculate(
    buy_settlement_days=1,
    sell_settlement_days=2,
    capital_required=100000,
    holding_period_days=5,
    annual_financing_rate_pct=12.0
)
print("basic:", result)
assert result["capital_lockup_days"] == 7
assert result["settlement_mismatch_days"] == 1
assert abs(result["financing_cost"] - (100000 * (0.12 / 365.0) * 7)) < 1e-9
assert result["is_settlement_viable"] is True

# 2. Zero financing rate -> zero cost
result = engine.calculate(
    buy_settlement_days=0,
    sell_settlement_days=0,
    capital_required=50000,
    holding_period_days=10,
    annual_financing_rate_pct=0.0
)
print("zero rate:", result)
assert result["financing_cost"] == 0.0
assert result["capital_lockup_days"] == 10

# 3. Lock-up limit enforcement
result = engine.calculate(
    buy_settlement_days=2,
    sell_settlement_days=14,
    capital_required=100000,
    holding_period_days=30,
    annual_financing_rate_pct=10.0,
    max_acceptable_lockup_days=21
)
print("lockup limit:", result)
assert result["capital_lockup_days"] == 44
assert result["within_lockup_limit"] is False
assert result["is_settlement_viable"] is False

# 4. Sale proceeds arrive before buy leg pays (negative mismatch)
result = engine.calculate(
    buy_settlement_days=14,
    sell_settlement_days=3,
    capital_required=100000
)
print("negative mismatch:", result)
assert result["settlement_mismatch_days"] == -11
assert result["capital_lockup_days"] == 3

# 5. Input validation
for bad_kwargs in [
    {"buy_settlement_days": -1, "sell_settlement_days": 0, "capital_required": 0},
    {"buy_settlement_days": 0, "sell_settlement_days": -1, "capital_required": 0},
    {"buy_settlement_days": 0, "sell_settlement_days": 0, "capital_required": -5},
    {"buy_settlement_days": 0, "sell_settlement_days": 0, "capital_required": 0, "holding_period_days": -1},
    {"buy_settlement_days": 0, "sell_settlement_days": 0, "capital_required": 0, "annual_financing_rate_pct": -1},
]:
    try:
        engine.calculate(**bad_kwargs)
        raise AssertionError(f"expected ValueError for {bad_kwargs}")
    except ValueError:
        pass
print("input validation: OK")

print("\nALL SETTLEMENT ENGINE TESTS PASSED")
