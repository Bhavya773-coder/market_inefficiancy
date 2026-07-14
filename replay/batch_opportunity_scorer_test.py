"""
Parity + benchmark test for BatchOpportunityScorer.

Parity: 600 seeded randomized candidates spanning every rejection corner
must produce IDENTICAL verdicts (executability, reasons) and matching
numbers vs the scalar OpportunityRankingEngine.

Benchmark: real timings for scalar loop vs numpy batch (and cupy/GPU
batch when a CUDA device is actually usable — skipped honestly if not).
"""
import random
import time

from inefficiency.opportunity_ranking_engine import OpportunityRankingEngine
from inefficiency.batch_opportunity_scorer import BatchOpportunityScorer, gpu_available

print("=== BATCH OPPORTUNITY SCORER TEST ===")

rng = random.Random(42)


def random_candidate(i):
    buy = rng.uniform(10, 70000)
    # Mix of clearly-good, marginal and clearly-bad edges
    edge_pct = rng.choice([-0.5, 0.05, 0.15, 0.5, 2.0, 5.0]) + rng.uniform(-0.02, 0.02)
    qty = rng.choice([1, 5, 10, 100])
    avail = rng.choice([3, 30, 1000, 1e6])  # thin to deep
    return {
        "opportunity_id": f"c{i}",
        "opportunity_type": "relative_value",
        "asset": f"A{i}",
        "buy_market": "X", "sell_market": "Y",
        "buy_price": buy,
        "sell_price": buy * (1 + edge_pct / 100.0),
        "quantity": qty,
        "buy_settlement_days": rng.choice([0, 1, 2, 14]),
        "sell_settlement_days": rng.choice([0, 1, 2, 30]),
        "holding_period_days": rng.choice([0.0, 1.0, 30.0]),
        "annual_financing_rate_pct": rng.choice([0.0, 6.0, 12.0]),
        "max_acceptable_lockup_days": rng.choice([None, 3, 21]),
        "buy_side_available_quantity": avail,
        "sell_side_available_quantity": rng.choice([avail, 1e6]),
        "buy_spread_pct": rng.uniform(0, 0.2),
        "sell_spread_pct": rng.uniform(0, 0.2),
        "min_fill_ratio": rng.choice([0.5, 1.0]),
        "min_annualized_return_pct": rng.choice([0.0, 5.0, 50.0]),
        "buy_brokerage": buy * qty * 0.0002,
        "sell_brokerage": buy * qty * 0.0002,
        "buy_tax": buy * qty * 0.0001,
        "sell_tax": buy * qty * 0.0001
    }


candidates = [random_candidate(i) for i in range(600)]
engine = OpportunityRankingEngine()
scorer = BatchOpportunityScorer(backend="numpy")

AVAILABLE_CAPITAL = 500000.0
scalar_results = [engine.evaluate(c, available_capital=AVAILABLE_CAPITAL) for c in candidates]
batch_results = scorer.score(candidates, available_capital=AVAILABLE_CAPITAL)

mismatches = 0
for s, b in zip(scalar_results, batch_results):
    ok = (
        s["is_executable"] == b["is_executable"]
        and set(s["rejection_reasons"]) == set(b["rejection_reasons"])
        and abs(s["rank_score"] - b["rank_score"]) <= 1e-9 * max(1.0, abs(s["rank_score"]))
        and abs(s["net_profit"] - b["net_profit"]) <= 1e-9 * max(1.0, abs(s["net_profit"]))
        and abs(s["executable_quantity"] - b["executable_quantity"]) <= 1e-12
        and abs(s["annualized_return_pct"] - b["annualized_return_pct"]) <= 1e-9 * max(1.0, abs(s["annualized_return_pct"]))
    )
    if not ok:
        mismatches += 1
        if mismatches <= 3:
            print("MISMATCH", s["opportunity_id"], s["rejection_reasons"], b["rejection_reasons"],
                  s["rank_score"], b["rank_score"])

executable_count = sum(1 for s in scalar_results if s["is_executable"])
print(f"candidates: {len(candidates)} | executable: {executable_count} | mismatches: {mismatches}")
assert mismatches == 0, f"{mismatches} scalar/batch verdict mismatches"
assert 0 < executable_count < len(candidates), "test set must span both verdicts"
print("PARITY: numpy batch == scalar engine on all 600 candidates")

# ---------------------------------------------------------------------
# Benchmark (real timings, printed)
# ---------------------------------------------------------------------
bench = [random_candidate(i) for i in range(20000)]

t0 = time.perf_counter()
for c in bench:
    engine.evaluate(c, available_capital=AVAILABLE_CAPITAL)
scalar_s = time.perf_counter() - t0

t0 = time.perf_counter()
scorer.score(bench, available_capital=AVAILABLE_CAPITAL)
numpy_s = time.perf_counter() - t0

print(f"\nBENCHMARK 20000 candidates:")
print(f"  scalar loop : {scalar_s:.3f}s  ({20000 / scalar_s:,.0f}/s)")
print(f"  numpy batch : {numpy_s:.3f}s  ({20000 / numpy_s:,.0f}/s)  speedup x{scalar_s / numpy_s:.1f}")

if gpu_available():
    gpu_scorer = BatchOpportunityScorer(backend="cupy")
    gpu_scorer.score(bench[:100], available_capital=AVAILABLE_CAPITAL)  # warm-up/JIT
    t0 = time.perf_counter()
    gpu_results = gpu_scorer.score(bench, available_capital=AVAILABLE_CAPITAL)
    gpu_s = time.perf_counter() - t0
    print(f"  cupy  batch : {gpu_s:.3f}s  ({20000 / gpu_s:,.0f}/s)  speedup x{scalar_s / gpu_s:.1f}")

    # GPU parity spot check vs scalar on first 200
    for s, b in zip(scalar_results[:200], gpu_scorer.score(candidates[:200], available_capital=AVAILABLE_CAPITAL)):
        assert s["is_executable"] == b["is_executable"]
        assert set(s["rejection_reasons"]) == set(b["rejection_reasons"])
        assert abs(s["rank_score"] - b["rank_score"]) <= 1e-6 * max(1.0, abs(s["rank_score"]))
    print("PARITY: cupy batch == scalar engine (200-candidate spot check)")
else:
    print("  cupy  batch : SKIPPED — no usable CUDA device in this environment")

# ---------------------------------------------------------------------
# Columnar benchmark: the array-native path where batch execution is
# actually meant to pay (inputs already columnar, no dict handling).
# ---------------------------------------------------------------------
import numpy as np

N = 1_000_000
rng_np = np.random.default_rng(42)
buy = rng_np.uniform(10, 70000, N)
cols_np = {
    "buy_price": buy,
    "sell_price": buy * (1 + rng_np.uniform(-0.005, 0.05, N)),
    "quantity": rng_np.choice([1.0, 5.0, 10.0, 100.0], N),
    "buy_settlement_days": rng_np.choice([0.0, 1.0, 2.0], N),
    "sell_settlement_days": rng_np.choice([0.0, 1.0, 2.0, 30.0], N),
    "buy_side_available_quantity": rng_np.choice([3.0, 1000.0, 1e6], N),
    "sell_side_available_quantity": rng_np.choice([30.0, 1e6], N),
    "holding_period_days": rng_np.choice([0.0, 1.0, 30.0], N),
    "annual_financing_rate_pct": np.full(N, 6.0),
    "buy_spread_pct": rng_np.uniform(0, 0.2, N),
    "sell_spread_pct": rng_np.uniform(0, 0.2, N),
    "max_participation_rate": np.full(N, 0.25),
    "slippage_pct_at_full_participation": np.full(N, 0.5),
    "min_fill_ratio": np.full(N, 0.5),
    "min_annualized_return_pct": np.full(N, 5.0),
    "max_acceptable_lockup_days": np.full(N, np.inf),
    **{k: np.zeros(N) for k in (
        "buy_brokerage", "sell_brokerage", "exchange_charges", "clearing_charges",
        "buy_tax", "sell_tax", "gst_or_vat", "stamp_duty", "fx_spread",
        "freight", "warehouse_cost", "handling_cost", "hedging_cost")}
}

t0 = time.perf_counter()
res_np = scorer.score_columns(cols_np, available_capital=1e9)
numpy_col_s = time.perf_counter() - t0
print(f"\nCOLUMNAR BENCHMARK {N:,} candidates:")
print(f"  numpy columns: {numpy_col_s:.3f}s  ({N / numpy_col_s:,.0f}/s)")

if gpu_available():
    gpu_scorer = BatchOpportunityScorer(backend="cupy")
    import cupy
    cols_gpu = {k: cupy.asarray(v) for k, v in cols_np.items()}
    gpu_scorer.score_columns({k: v[:1000] for k, v in cols_gpu.items()}, available_capital=1e9)  # warm-up
    cupy.cuda.Stream.null.synchronize()
    t0 = time.perf_counter()
    res_gpu = gpu_scorer.score_columns(cols_gpu, available_capital=1e9)
    cupy.cuda.Stream.null.synchronize()
    gpu_col_s = time.perf_counter() - t0
    print(f"  cupy  columns: {gpu_col_s:.3f}s  ({N / gpu_col_s:,.0f}/s)  speedup x{numpy_col_s / gpu_col_s:.1f} vs numpy")
    # Columnar parity: numpy vs gpu results
    assert np.array_equal(res_np["is_executable"], res_gpu["is_executable"])
    assert np.allclose(res_np["rank_score"], res_gpu["rank_score"], rtol=1e-9, atol=1e-9)
    print("PARITY: columnar numpy == columnar cupy on 1M candidates")

print("\nALL BATCH SCORER TESTS PASSED")
