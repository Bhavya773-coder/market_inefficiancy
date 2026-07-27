"""
Offline checks for the Kronos forecaster. No network, no model download.

The safety contract is what matters here: a broken forecaster must return
None ("no opinion") and never raise, because a raise inside a caller's
decision path would kill the trading loop.

Scope note (2026-07-27): the crypto runner's Kronos entry tests
(long-only guard, conviction floor, entries-off default) were removed
together with the crypto module. Reinstate equivalents against whatever
strategy consumes the forecaster next — the long-only guard especially,
since the opportunity gate scores abs(gap) and would happily approve a
DOWN forecast as a long.

    PYTHONPATH=. python replay/kronos_forecast_test.py
"""
from ai import kronos_forecast
from ai.kronos_forecast import compact, direction


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
    assert direction(ExplodingConnector(), "ANY") is None
    assert direction(EmptyConnector(), "ANY") is None
    assert direction(BadShapeConnector(), "ANY") is None


def test_cache_keys_on_candle_rollover():
    kronos_forecast._CACHE.clear()
    seeded = {"up": True, "move_pct": 0.4, "horizon": 15}
    kronos_forecast._CACHE[("ANY", 1000)] = seeded

    class Stub:
        def __init__(self, last_ms):
            self.last_ms = last_ms

        def get_candlesticks(self, *a, **k):
            return [{"timestamp_ms": self.last_ms - 60000, "open": 1, "high": 1,
                     "low": 1, "close": 1, "volume": 1},
                    {"timestamp_ms": self.last_ms, "open": 1, "high": 1,
                     "low": 1, "close": 1, "volume": 1}]

    # Same candle -> served from cache, so no model is ever constructed.
    assert direction(Stub(1000), "ANY") == seeded

    # A new candle is a different key and must never serve the stale entry.
    # Force the model path to blow up so this stays offline and deterministic;
    # fail-open then gives None, which is also the invariant we want.
    original = kronos_forecast._predictor
    kronos_forecast._predictor = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("no model in tests"))
    try:
        assert direction(Stub(2000), "ANY") is None
    finally:
        kronos_forecast._predictor = original
    kronos_forecast._CACHE.clear()


def test_compact_drops_chart_series():
    # compact() keeps trade logs and the Excel export free of the ~75-float
    # path/context series used only for charting.
    full = {"up": True, "move_pct": 0.3, "horizon": 15,
            "path": [1.0] * 15, "context": [1.0] * 60, "last_close": 1.0}
    assert compact(full) == {"up": True, "move_pct": 0.3, "horizon": 15}
    assert compact(None) is None


if __name__ == "__main__":
    test_fails_open()
    test_cache_keys_on_candle_rollover()
    test_compact_drops_chart_series()
    print("kronos_forecast_test: all checks passed")
