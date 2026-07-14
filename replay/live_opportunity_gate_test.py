"""
Wiring-proof test for LiveOpportunityGate + PaperTradingEngine.

Asserts that the OpportunityRankingEngine's verdict — not the legacy
RoundTripFeasibilityChecker — is what decides live paper entries:
a candidate the OLD gate would allow gets blocked when the ranking
engine says no, and vice-versa evidence is captured in the decision
metadata.
"""
from ai.live_opportunity_gate import LiveOpportunityGate
from ai.paper_trading_engine import PaperTradingEngine
from ai.paper_trade_candidate import PaperTradeCandidate
from ai.candidate_feasibility_adapter import CandidateFeasibilityAdapter

print("=== LIVE OPPORTUNITY GATE TEST ===")

gate = LiveOpportunityGate()


def make_detection(residual_gap, status="DIVERGENCE"):
    return {
        "target": "STEEL_FUTURE",
        "status": status,
        "is_inefficient": True,
        "residual_gap": residual_gap,
        "absolute_gap": residual_gap,
        "expected_change": residual_gap,
        "actual_change": 0.0,
        "coverage_ratio": 1.0,
        "recommended_direction": "BUY",
        "inefficiency_score": abs(residual_gap),
        "contributors": []
    }


def make_quote(price=100.0, volume=500000):
    return {
        "exchange": "NSE_EQ",
        "security_id": 3499,
        "symbol": "STEEL_FUTURE",
        "last_price": price,
        "volume": volume,
        "timestamp": "2026-07-14 16:40:00"
    }


# 1. KNOWN-GOOD: 2% unpriced gap, deep liquidity -> allowed with full detail
good = gate.evaluate_target(
    "STEEL_FUTURE", make_detection(2.0), "KEEP_SIGNAL", make_quote(),
    available_capital=100000
)
print("good: allowed =", good["allowed"], "qty =", good["quantity"],
      "annualized =", round(good["evaluation"]["annualized_return_pct"], 1))
assert good["allowed"] is True
assert good["quantity"] == 10
assert good["rejection_reasons"] == []
assert good["evaluation"]["is_executable"] is True
assert good["candidate"]["opportunity_type"] == "relative_value"

# 2. KNOWN-BAD: 0.2% gap — the LEGACY checker (flat 0.13% cost) would ALLOW
#    this, but the ranking engine must reject it (costs + spread + slippage
#    + minimum annualized return).
legacy_view = CandidateFeasibilityAdapter().from_candidate(
    PaperTradeCandidate(
        asset="STEEL_FUTURE", source="test", opportunity_type="commodity_inefficiency",
        entry_reason="test_candidate", score=0.15, confidence=1.0
    )
)
print("legacy verdict on 0.15% edge:", legacy_view["is_feasible"],
      "(net", round(legacy_view["net_edge_pct"], 3), "%)")
assert legacy_view["is_feasible"] is True  # old logic says yes

bad = gate.evaluate_target(
    "STEEL_FUTURE", make_detection(0.15), "KEEP_SIGNAL", make_quote(),
    available_capital=100000
)
print("ranking verdict on 0.15% edge:", bad["allowed"], bad["rejection_reasons"])
assert bad["allowed"] is False  # new gate says no — THE DECIDING VERDICT DIFFERS
assert len(bad["rejection_reasons"]) > 0

# 3. The gate verdict — not the legacy one — decides the paper trade outcome
engine = PaperTradingEngine()
candidate = PaperTradeCandidate(
    asset="STEEL_FUTURE", source="test", opportunity_type="commodity_inefficiency",
    entry_reason="test_candidate", score=0.15, confidence=1.0
)

blocked_report = engine.process_gated_candidate(candidate, bad, price=100.0)
print("blocked execution:", blocked_report["execution"]["status"],
      "| reason:", blocked_report["decision"]["reason"][:60])
assert blocked_report["execution"]["status"] == "rejected"
assert blocked_report["decision"]["action"] == "REJECTED"
assert blocked_report["decision"]["reason"].startswith("ranking_engine_rejected:")
assert blocked_report["account"]["cash"] == 100000  # nothing bought

allowed_report = engine.process_gated_candidate(candidate, good, price=100.0)
print("allowed execution:", allowed_report["execution"]["status"],
      "| qty:", allowed_report["decision"]["quantity"])
assert allowed_report["execution"]["status"] == "filled"
assert allowed_report["decision"]["action"] == "BUY_ALLOWED"
assert allowed_report["decision"]["reason"] == "ranking_engine_approved"
assert allowed_report["decision"]["metadata"]["gate"] == "opportunity_ranking_engine"
assert allowed_report["account"]["cash"] == 100000 - 10 * 100.0

# 4. REDUCE_PRIORITY halves the believed edge
full = gate.build_candidate("X", make_detection(2.0), "KEEP_SIGNAL", make_quote())[0]
half = gate.build_candidate("X", make_detection(2.0), "REDUCE_PRIORITY", make_quote())[0]
implied_full = (full["sell_price"] / full["buy_price"] - 1) * 100
implied_half = (half["sell_price"] / half["buy_price"] - 1) * 100
print("edge: KEEP =", round(implied_full, 3), "% REDUCE =", round(implied_half, 3), "%")
assert abs(implied_full - 2.0) < 1e-9
assert abs(implied_half - 1.0) < 1e-9

# 5. Insufficient capital blocks even a strong edge
poor = gate.evaluate_target(
    "STEEL_FUTURE", make_detection(2.0), "KEEP_SIGNAL", make_quote(price=100.0),
    available_capital=50.0
)
print("underfunded:", poor["allowed"], poor["rejection_reasons"])
assert poor["allowed"] is False
assert "insufficient_capital" in poor["rejection_reasons"]

# 6. Thin volume caps quantity through the liquidity engine
thin = gate.evaluate_target(
    "STEEL_FUTURE", make_detection(2.0), "KEEP_SIGNAL",
    make_quote(volume=24),  # 25% participation -> 6 executable of 10 desired
    available_capital=100000
)
print("thin volume: allowed =", thin["allowed"], "qty =", thin["quantity"])
assert thin["allowed"] is True   # min_fill_ratio 0.5 -> 0.6 fill OK
assert thin["quantity"] == 6     # ranking engine's executable quantity decides size

# 7. Degenerate inputs never crash, always explain
for det, quote, expected_reason in [
    (make_detection(2.0), None, "missing_quote"),
    (make_detection(2.0), {"last_price": -5, "volume": 1}, "invalid_quote_price"),
    ({"target": "X", "residual_gap": None, "absolute_gap": None}, make_quote(), "no_measurable_edge"),
    (make_detection(0.0), make_quote(), "zero_edge"),
]:
    res = gate.evaluate_target("X", det, "KEEP_SIGNAL", quote)
    assert res["allowed"] is False and expected_reason in res["rejection_reasons"], (det, quote, res)
print("degenerate inputs handled: OK")

# 8. Unknown config keys rejected explicitly
try:
    LiveOpportunityGate(config={"tpyo_key": 1})
    raise AssertionError("expected ValueError for unknown config key")
except ValueError:
    print("config validation: OK")

print("\nALL LIVE OPPORTUNITY GATE TESTS PASSED")
