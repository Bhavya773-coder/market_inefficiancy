"""
Kronos directional second-opinion for the crypto lag strategy.

The lag gate already answers "is this profitable IF it works". This answers
"is it likely to work" by forecasting the target's next candles.

Fail-open by contract: every failure path returns None ("no opinion"), which
callers must treat as "do not block". A broken model must never stop trading.

Validated offline by scripts/kronos_backtest.py (2026-07-24): on 1m and 5m
samples the UP subset beat the unfiltered baseline by +3.5pp win rate both
times, and the DOWN subset was consistently worse. Small, not individually
significant — hence --kronos-filter defaults to off/shadow.
"""
OHLCV = ["open", "high", "low", "close", "volume"]
LOOKBACK = 180
HORIZON = 15

# (symbol, last_candle_ms) -> result. Keying on the candle timestamp means a
# new candle invalidates naturally, so no TTL bookkeeping is needed.
_CACHE = {}
_PREDICTOR = None


def _resolve_device(device):
    """"auto" -> cuda when a GPU is actually usable, else cpu."""
    if device not in (None, "auto"):
        return device
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _predictor(model, tokenizer, device, max_context):
    """Loads once per process. Imported lazily so torch stays out of the
    default (filter-off) path entirely."""
    global _PREDICTOR
    if _PREDICTOR is None:
        from vendor.kronos import Kronos, KronosTokenizer, KronosPredictor
        _PREDICTOR = KronosPredictor(
            Kronos.from_pretrained(model),
            KronosTokenizer.from_pretrained(tokenizer),
            device=_resolve_device(device), max_context=max_context,
        )
    return _PREDICTOR


def direction(connector, symbol, model="NeoQuasar/Kronos-small",
              tokenizer="NeoQuasar/Kronos-Tokenizer-base", device="auto",
              max_context=512, lookback=LOOKBACK, horizon=HORIZON,
              timeframe="1m", temperature=1.0, top_p=0.9):
    """
    Forecasts `symbol` and returns {"up": bool, "move_pct": float,
    "horizon": int} — or None if anything at all goes wrong.

    ponytail: synchronous. ~0.4-0.6s on the RTX 4050 (125MB VRAM), ~3.8s on
    CPU. Well inside the 3s poll cadence on GPU, and callers only ask about
    candidates that already cleared the cost gate, so no prefetch thread is
    needed. Revisit if forced onto CPU or if the instrument list grows a lot.
    """
    try:
        import pandas as pd

        candles = connector.get_candlesticks(symbol, timeframe=timeframe,
                                             count=lookback + 1)
        if len(candles) < 2:
            return None

        key = (symbol, candles[-1]["timestamp_ms"])
        if key in _CACHE:
            return _CACHE[key]

        df = pd.DataFrame(candles)
        df["timestamps"] = pd.to_datetime(df["timestamp_ms"], unit="ms")
        x = df.iloc[-lookback:][OHLCV].reset_index(drop=True)
        xt = df.iloc[-lookback:]["timestamps"].reset_index(drop=True)
        step = df["timestamps"].iloc[-1] - df["timestamps"].iloc[-2]
        yt = pd.Series([df["timestamps"].iloc[-1] + step * (i + 1)
                        for i in range(horizon)])

        pred = _predictor(model, tokenizer, device, max_context).predict(
            df=x, x_timestamp=xt, y_timestamp=yt, pred_len=horizon,
            T=temperature, top_p=top_p, sample_count=1, verbose=False,
        )

        last = float(x["close"].iloc[-1])
        move_pct = (float(pred["close"].iloc[-1]) - last) / last * 100.0
        result = {"up": move_pct > 0, "move_pct": move_pct, "horizon": horizon}

        if len(_CACHE) > 64:
            _CACHE.clear()
        _CACHE[key] = result
        return result
    except Exception as exc:  # fail-open: no opinion, never block a trade
        return None
