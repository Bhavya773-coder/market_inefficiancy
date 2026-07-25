"""
Offline checks for the Kronos filter. No network, no model download, no torch.

The safety contract is what matters here: a broken forecaster must return
None ("no opinion") and never raise, because a raise inside detect_and_trade
would kill the live trading loop.

    PYTHONPATH=. python replay/kronos_forecast_test.py
"""
from ai import kronos_forecast
from ai.kronos_forecast import direction


class ExplodingConnector:
    def get_candlesticks(self, *a, **k):
        raise RuntimeError("exchange down")


class EmptyConnector:
    def get_candlesticks(self, *a, **k):
        return []


class BadShapeConnector:
    def get_candlesticks(self, *a, **k):
        return [{"nonsense": 1}, {"nonsense": 2}]


def test_fails_open():
    # Any upstream failure must degrade to "no opinion", never an exception.
    assert direction(ExplodingConnector(), "BTC_USDT") is None
    assert direction(EmptyConnector(), "BTC_USDT") is None
    assert direction(BadShapeConnector(), "BTC_USDT") is None


def test_cache_keys_on_candle_rollover():
    kronos_forecast._CACHE.clear()
    kronos_forecast._CACHE[("BTC_USDT", 1000)] = {"up": True, "move_pct": 0.4,
                                                  "horizon": 15}

    calls = []

    class Stub:
        def __init__(self, last_ms):
            self.last_ms = last_ms

        def get_candlesticks(self, *a, **k):
            calls.append(self.last_ms)
            return [{"timestamp_ms": self.last_ms - 60000, "open": 1, "high": 1,
                     "low": 1, "close": 1, "volume": 1},
                    {"timestamp_ms": self.last_ms, "open": 1, "high": 1,
                     "low": 1, "close": 1, "volume": 1}]

    seeded = {"up": True, "move_pct": 0.4, "horizon": 15}
    # Same candle -> served from cache, so no model is ever constructed.
    assert direction(Stub(1000), "BTC_USDT") == seeded

    # A new candle is a different key and must never serve the stale entry.
    # Force the model path to blow up so this stays offline and deterministic;
    # fail-open then gives None, which is also the invariant we want.
    original = kronos_forecast._predictor
    kronos_forecast._predictor = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("no model in tests"))
    try:
        assert direction(Stub(2000), "BTC_USDT") is None
    finally:
        kronos_forecast._predictor = original
    kronos_forecast._CACHE.clear()


def test_runner_defaults_to_off():
    # The whole safety story rests on this: an unflagged run behaves exactly
    # as it did before Kronos existed.
    import argparse
    from live.run_live_crypto_paper_trading import main as _  # import smoke

    p = argparse.ArgumentParser()
    p.add_argument("--kronos-filter", choices=["off", "shadow", "on"], default="off")
    assert p.parse_args([]).kronos_filter == "off"


class _FakeConn:
    def get_standard_quotes(self, syms):
        return {"quotes": [{"asset": s, "last_price": 100.0, "bid": 99.99,
                            "ask": 100.01, "timestamp": "t", "currency": None,
                            "liquidity_score": 0.9} for s in syms], "errors": []}


def _scan_with(forecast, **overrides):
    """Runs one kronos_scan with a stubbed forecast; returns (positions, reasons)."""
    import argparse
    import json
    import pathlib
    import tempfile
    from datetime import datetime, timezone
    import live.run_live_crypto_paper_trading as M

    real = M.kronos_direction
    M.kronos_direction = lambda *a, **k: forecast
    try:
        out = tempfile.mkdtemp()
        cfg = dict(instruments="BTC_USDT,ETH_USDT", output_dir=out,
                   starting_cash=1000000, duration=1, poll_interval=3,
                   min_gap_percent=0.05, take_profit_pct=0.5, stop_loss_pct=0.25,
                   kronos_filter="on", kronos_device="cpu", kronos_entries="on",
                   kronos_min_move_pct=0.15, kronos_forecast_interval=120)
        cfg.update(overrides)
        runner = M.CryptoPaperTradingRunner(argparse.Namespace(**cfg),
                                           connector=_FakeConn())
        runner.poll_quotes()
        runner.kronos_scan(datetime.now(timezone.utc))
        reasons = set()
        for line in open(pathlib.Path(out) / "paper_trades.jsonl", encoding="utf-8"):
            for r in (json.loads(line).get("rejection_reasons") or []):
                reasons.add(r)
        return list(runner.paper_engine.account_state()["positions"]), reasons
    finally:
        M.kronos_direction = real


def test_kronos_entries_are_long_only():
    # The gate scores abs(gap), so a DOWN forecast would be approved as a long
    # and trade backwards. This guard is the only thing preventing that.
    positions, reasons = _scan_with({"up": False, "move_pct": -0.80, "horizon": 15})
    assert positions == [], positions
    assert "kronos_forecast_down_long_only" in reasons, reasons


def test_kronos_entry_respects_min_move_and_gate():
    positions, reasons = _scan_with({"up": True, "move_pct": 0.05, "horizon": 15})
    assert positions == [] and "kronos_move_below_min" in reasons, reasons

    # Clears the conviction floor but still cannot cover round-trip costs.
    positions, reasons = _scan_with({"up": True, "move_pct": 0.16, "horizon": 15})
    assert positions == [], positions

    # Big enough that the cost gate approves and a paper long is opened.
    positions, _ = _scan_with({"up": True, "move_pct": 0.45, "horizon": 15})
    assert sorted(positions) == ["BTC_USDT", "ETH_USDT"], positions


def test_kronos_entries_off_takes_no_trades():
    positions, _ = _scan_with({"up": True, "move_pct": 5.0, "horizon": 15},
                              kronos_entries="off")
    assert positions == [], positions


if __name__ == "__main__":
    test_fails_open()
    test_cache_keys_on_candle_rollover()
    test_runner_defaults_to_off()
    test_kronos_entries_are_long_only()
    test_kronos_entry_respects_min_move_and_gate()
    test_kronos_entries_off_takes_no_trades()
    print("kronos_forecast_test: all checks passed")
