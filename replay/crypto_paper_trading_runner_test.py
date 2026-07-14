"""
Offline regression test for CryptoPaperTradingRunner.

Injects a scripted fake connector (no network) that produces:
  poll 1: baseline prices
  poll 2: BTC jumps +0.60%, ETH flat        -> lag signal, gated entry on ETH
  poll 3: ETH rallies +0.55%                -> take-profit exit
Asserts the full pipeline: detection, gate approval, paper entry, exit,
PnL, and JSONL artifacts.
"""
import argparse
import json
import pathlib
import shutil

from live.run_live_crypto_paper_trading import CryptoPaperTradingRunner

print("=== CRYPTO PAPER TRADING RUNNER TEST (offline) ===")

OUTPUT_DIR = "storage/test_crypto_runner"
shutil.rmtree(OUTPUT_DIR, ignore_errors=True)


def std_quote(asset, price, ts):
    spread = price * 0.0001  # 1bp spread, deep liquid book
    return {
        "source": "crypto_com",
        "asset": asset,
        "bid": price - spread / 2,
        "ask": price + spread / 2,
        "last_price": price,
        "currency": "USDT",
        "timestamp": ts,
        "liquidity_score": 0.99
    }


class FakeConnector:
    """Returns one scripted poll result per call."""

    def __init__(self):
        self.polls = [
            # poll 1: baseline
            [std_quote("BTC_USDT", 62000.00, "2026-07-14T17:00:00+00:00"),
             std_quote("ETH_USDT", 1780.00, "2026-07-14T17:00:00+00:00")],
            # poll 2: BTC +0.60%, ETH unchanged-ish (+0.01%) -> ETH lags
            [std_quote("BTC_USDT", 62372.00, "2026-07-14T17:00:03+00:00"),
             std_quote("ETH_USDT", 1780.18, "2026-07-14T17:00:03+00:00")],
            # poll 3: ETH catches up +0.55% -> take profit (>0.5%)
            [std_quote("BTC_USDT", 62372.00, "2026-07-14T17:00:06+00:00"),
             std_quote("ETH_USDT", 1790.00, "2026-07-14T17:00:06+00:00")],
        ]
        self.calls = 0

    def get_standard_quotes(self, instruments):
        result = {"status": "success", "quotes": self.polls[self.calls], "errors": []}
        self.calls += 1
        return result


args = argparse.Namespace(
    duration=1,  # unused; we drive ticks manually
    poll_interval=0.0,
    instruments="BTC_USDT,ETH_USDT",
    output_dir=OUTPUT_DIR,
    starting_cash=100000.0,
    min_gap_percent=0.05,
    take_profit_pct=0.5,
    stop_loss_pct=0.25
)

runner = CryptoPaperTradingRunner(args, connector=FakeConnector())

from datetime import datetime, timezone

# Drive 3 ticks manually (deterministic, no sleeps)
for tick in range(3):
    observed_at = datetime.now(timezone.utc)
    events = runner.poll_quotes()
    assert events, f"poll {tick + 1} returned no events"
    runner.detect_and_trade(events, observed_at)
    runner.manage_exits(observed_at)

# 1. Lag was detected on poll 2 (BTC moved, ETH lagged)
assert runner.stats["lag_signals"] >= 1, runner.stats
print("lag detected:", runner.stats["lag_signals"], "signal(s)")

# 2. Gate approved and a paper entry filled on ETH
assert runner.stats["entries"] == 1, runner.stats
print("paper entry filled: OK")

# 3. Take-profit exit fired on poll 3 (ETH +0.55% > 0.5% target)
assert runner.stats["exits"] == 1, runner.stats
print("take-profit exit: OK")

# 4. PnL is positive and cash reflects the round trip
state = runner.paper_engine.account_state()
assert state["positions"] == {}, "position should be closed"
pnl = state["cash"] - args.starting_cash
print(f"round-trip PnL: {pnl:+.2f}")
assert pnl > 0, f"expected profit, got {pnl}"

# 5. JSONL artifacts exist and content matches: entry has gate breakdown
runner.report_final()
runner.close()
out = pathlib.Path(OUTPUT_DIR)
trades = [json.loads(line) for line in open(out / "paper_trades.jsonl")]
entry = next(t for t in trades if t["type"] == "entry")
assert entry["symbol"] == "ETH_USDT"
assert entry["lag_reference"] == "BTC_USDT"
assert "annualized_return_pct" in entry["gate_evaluation"]
assert entry["gate_evaluation"]["net_profit_pct"] > 0
exit_t = next(t for t in trades if t["type"] == "exit")
assert exit_t["symbol"] == "ETH_USDT"
summary = next(t for t in trades if t["type"] == "session_summary")
assert summary["stats"]["entries"] == 1
quotes = [json.loads(line) for line in open(out / "quotes.jsonl")]
assert len(quotes) == 3
# REGRESSION: quote log must carry data_source — the dashboard's
# REAL vs SIMULATED honesty tagging reads it.
for record in quotes:
    for q in record["quotes"].values():
        assert q.get("data_source") == "crypto_com_live", q
detections = [json.loads(line) for line in open(out / "detections.jsonl")]
assert any(d["type"] == "lag_signal" for d in detections)
print("JSONL artifacts verified: OK")

# 6. Poll errors are absorbed, not fatal — and REGRESSION (2026-07-14):
#    after 3 consecutive failed polls the runner resets the connector's
#    HTTP session to recover from wedged connections.
class BrokenConnector:
    def __init__(self):
        self.resets = 0

    def get_standard_quotes(self, instruments):
        raise __import__("connectors.crypto_connector", fromlist=["CryptoConnectorError"]).CryptoConnectorError("simulated outage")

    def reset_session(self):
        self.resets += 1


shutil.rmtree("storage/test_crypto_runner_err", ignore_errors=True)
args2 = argparse.Namespace(**{**vars(args), "output_dir": "storage/test_crypto_runner_err"})
broken = BrokenConnector()
runner2 = CryptoPaperTradingRunner(args2, connector=broken)
for _ in range(3):
    events = runner2.poll_quotes()
    assert events == {}
assert runner2.stats["poll_errors"] == 3
assert broken.resets == 1, "session must reset after 3 consecutive poll failures"
runner2.close()
print("poll error absorbed + session reset recovery: OK")

shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
shutil.rmtree("storage/test_crypto_runner_err", ignore_errors=True)
print("\nALL CRYPTO RUNNER TESTS PASSED")
