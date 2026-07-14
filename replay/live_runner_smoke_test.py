"""
Smoke test for live/run_live_paper_trading.py.

Last session this runner carried three fatal bugs (init crash, missing
import, wrong writer method) that no test caught because nothing imported
it. This test constructs the runner for real, drives execute_pipeline
with synthetic quotes, and asserts the Phase 2 opportunity gate is what
gates entries.
"""
import argparse
import pathlib
import shutil
import time
from datetime import datetime, timezone

from live.run_live_paper_trading import LivePaperTradingRunner, is_market_open_now

print("=== LIVE RUNNER SMOKE TEST ===")

OUTPUT_DIR = "storage/test_runner_smoke"
shutil.rmtree(OUTPUT_DIR, ignore_errors=True)


def make_args(**overrides):
    base = {
        "poll_interval": 0.1,
        "duration": 1,
        "dry_run": False,
        "output_dir": OUTPUT_DIR,
        "dhan_map_path": None,
        "bypass_market_hours": True,
        "max_quote_age_seconds": 10.0,
        "max_pair_gap_seconds": 10.0
    }
    base.update(overrides)
    return argparse.Namespace(**base)


# 1. Construction succeeds (would have caught last session's init crash)
runner = LivePaperTradingRunner(make_args())
print("runner constructed: OK")

# 2. Phase 2 gate is wired in
from ai.live_opportunity_gate import LiveOpportunityGate
assert isinstance(runner.opportunity_gate, LiveOpportunityGate), \
    "runner must gate entries through LiveOpportunityGate"
print("opportunity gate wired: OK")

# 3. execute_pipeline runs on an empty buffer without crashing
now = datetime.now(timezone.utc)
runner.execute_pipeline(now, tick_count=1)
print("empty-buffer pipeline: OK")

# 4. execute_pipeline runs with synthetic quotes present for every mapped
#    instrument (exercises detection, episode tracking, regime, gating)
for sym, cfg in runner.dhan_map.items():
    quote = {
        "exchange": cfg["exchange"],
        "security_id": cfg["security_id"],
        "symbol": sym,
        "last_price": 100.0,
        "volume": 100000,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "data_source": "smoke_test"
    }
    runner.quote_buffer.update_quote(
        quote, received_at=now, received_monotonic=time.perf_counter()
    )
runner.execute_pipeline(now, tick_count=2)
print("full-buffer pipeline: OK")

# 5. The gate — not the legacy feasibility path — is the entry decider:
#    monkeypatch the gate to always block and verify no entry can happen
#    even when everything upstream looks perfect.
class AlwaysBlockGate:
    def evaluate_target(self, *args, **kwargs):
        return {
            "allowed": False,
            "quantity": 0,
            "rejection_reasons": ["forced_block_by_smoke_test"],
            "candidate": None,
            "evaluation": None
        }


runner.opportunity_gate = AlwaysBlockGate()
cash_before = runner.paper_engine.account_state()["cash"]
runner.execute_pipeline(datetime.now(timezone.utc), tick_count=3)
cash_after = runner.paper_engine.account_state()["cash"]
assert cash_before == cash_after, "blocked gate must prevent all entries"
print("gate verdict decides entries: OK")

# 6. Clean shutdown flushes logs
runner.close()
out = pathlib.Path(OUTPUT_DIR)
assert (out / "quote_ingestions.jsonl").exists()
assert (out / "detections.jsonl").exists()
print("clean shutdown + artifacts: OK")

# 7. Market-hours helper still behaves (regression guard)
is_open, reason = is_market_open_now(datetime(2026, 7, 12, 6, 0, tzinfo=timezone.utc))  # Sunday
assert is_open is False and reason == "weekend"
is_open, reason = is_market_open_now(datetime(2026, 7, 14, 6, 0, tzinfo=timezone.utc))  # Tue 11:30 IST
assert is_open is True
print("market hours helper: OK")

shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
print("\nALL LIVE RUNNER SMOKE TESTS PASSED")
