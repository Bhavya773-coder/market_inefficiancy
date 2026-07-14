import logging
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger("connectors.crypto")

CRYPTO_COM_TICKER_URL = "https://api.crypto.com/exchange/v1/public/get-tickers"
CRYPTO_COM_CANDLESTICK_URL = "https://api.crypto.com/exchange/v1/public/get-candlestick"


class CryptoConnectorError(Exception):
    """Raised when the crypto exchange API cannot produce a usable response."""


class CryptoConnector:
    """
    Read-only market-data connector for the Crypto.com Exchange public API.

    - Uses only public, credential-free endpoints. There is deliberately no
      order-placement surface; execution stays in PaperTradingAccount.
    - Returns quotes in the project-standard connector shape from
      docs/NEXT_BUILD.md: source / asset / bid / ask / last_price /
      currency / timestamp / liquidity_score.
    - Retries transient failures with exponential backoff and spaces
      requests to stay far inside the public rate limits.
    - Transport is injectable for offline testing.
    """

    def __init__(
        self,
        http_get=None,
        max_retries=3,
        backoff_base_seconds=0.5,
        min_request_interval_seconds=0.35,
        request_timeout_seconds=10.0,
        sleep_fn=time.sleep
    ):
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if backoff_base_seconds < 0:
            raise ValueError("backoff_base_seconds must be >= 0")
        if min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds must be >= 0")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be > 0")

        self._http_get = http_get if http_get is not None else self._default_http_get
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.min_request_interval_seconds = min_request_interval_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self._sleep = sleep_fn
        self._last_request_monotonic = None
        # One pooled session for the connector's lifetime. Without this,
        # every request opened a fresh TCP+TLS connection; sustained polling
        # accumulated socket churn until new connections started failing
        # (observed live 2026-07-14: every call ConnectionError after ~8 min).
        self._session = requests.Session()

    def _default_http_get(self, url, params):
        response = self._session.get(url, params=params, timeout=self.request_timeout_seconds)
        response.raise_for_status()
        return response.json()

    def reset_session(self):
        """Drops and recreates the pooled HTTP session (recovery hook)."""
        try:
            self._session.close()
        except Exception:
            pass
        self._session = requests.Session()
        logger.info("crypto connector HTTP session reset")

    def _respect_rate_limit(self):
        if self._last_request_monotonic is None:
            return
        elapsed = time.monotonic() - self._last_request_monotonic
        remaining = self.min_request_interval_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)

    def _call_with_retries(self, description, url, params):
        last_error = None
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                delay = self.backoff_base_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "%s: retry %d/%d after %.2fs (%s)",
                    description, attempt, self.max_retries, delay, last_error
                )
                self._sleep(delay)

            self._respect_rate_limit()
            try:
                payload = self._http_get(url, params)
                self._last_request_monotonic = time.monotonic()
            except Exception as e:
                self._last_request_monotonic = time.monotonic()
                last_error = f"transport_error: {type(e).__name__}"
                logger.warning("%s: transport error: %s", description, type(e).__name__)
                continue

            if not isinstance(payload, dict) or payload.get("code") != 0:
                last_error = f"api_failure: code={payload.get('code') if isinstance(payload, dict) else 'non-dict'}"
                logger.warning("%s: API failure (%s)", description, last_error)
                continue

            return payload

        raise CryptoConnectorError(
            f"{description}: failed after {self.max_retries + 1} attempts ({last_error})"
        )

    @staticmethod
    def _quote_currency(instrument_name):
        # Crypto.com instrument names are BASE_QUOTE, e.g. BTC_USDT.
        parts = instrument_name.split("_")
        return parts[-1] if len(parts) >= 2 else "USD"

    def get_standard_quotes(self, instrument_names):
        """
        Fetches tickers for the given instrument names (e.g. ["BTC_USDT"])
        and returns them in the docs/NEXT_BUILD.md standard shape.

        liquidity_score is a bounded 0..1 proxy from bid/ask spread
        tightness only — the public ticker carries no depth, so quantity
        balance cannot be measured here. 0.0 when bid/ask are missing.
        """
        if not instrument_names:
            raise ValueError("instrument_names must be a non-empty list")

        quotes = []
        errors = []

        # One batch call: the endpoint returns ALL tickers when no
        # instrument_name is given. This keeps sustained polling at one
        # HTTP request per poll instead of one per instrument.
        payload = self._call_with_retries(
            f"get_tickers(batch x{len(instrument_names)})",
            CRYPTO_COM_TICKER_URL,
            None
        )
        data = payload.get("result", {}).get("data", [])
        tickers_by_name = {
            t.get("i"): t for t in data if isinstance(t, dict)
        }

        for instrument_name in instrument_names:
            ticker = tickers_by_name.get(instrument_name)
            if ticker is None:
                errors.append({
                    "instrument_name": instrument_name,
                    "error": "instrument missing from batch ticker response"
                })
                continue
            try:
                last_price = float(ticker["a"]) if ticker.get("a") is not None else None
                bid = float(ticker["b"]) if ticker.get("b") is not None else None
                ask = float(ticker["k"]) if ticker.get("k") is not None else None
                ts_millis = ticker.get("t")
            except (TypeError, ValueError) as e:
                errors.append({
                    "instrument_name": instrument_name,
                    "error": f"unparseable ticker fields: {e}"
                })
                continue

            # Reject malformed market data at the boundary: a non-positive
            # or NaN price must never reach detection/trading layers.
            if (
                last_price is None
                or not (last_price > 0)  # False for NaN too
                or (bid is not None and not (bid > 0))
                or (ask is not None and not (ask > 0))
            ):
                errors.append({
                    "instrument_name": instrument_name,
                    "error": f"out-of-range ticker prices (last={last_price}, bid={bid}, ask={ask})"
                })
                continue

            liquidity_score = 0.0
            if bid is not None and ask is not None and ask >= bid > 0:
                mid = (bid + ask) / 2.0
                spread_pct = ((ask - bid) / mid) * 100.0 if mid > 0 else 100.0
                liquidity_score = 1.0 / (1.0 + spread_pct)

            timestamp = None
            if isinstance(ts_millis, (int, float)) and ts_millis > 0:
                timestamp = datetime.fromtimestamp(
                    ts_millis / 1000.0, tz=timezone.utc
                ).isoformat()

            quotes.append({
                "source": "crypto_com",
                "asset": ticker.get("i", instrument_name),
                "bid": bid,
                "ask": ask,
                "last_price": last_price,
                "currency": self._quote_currency(instrument_name),
                "timestamp": timestamp,
                "liquidity_score": liquidity_score
            })

        if not quotes:
            raise CryptoConnectorError(
                f"No usable quotes returned; errors: {errors}"
            )

        return {
            "status": "success",
            "quotes": quotes,
            "errors": errors
        }

    def get_candlesticks(self, instrument_name, timeframe="1m", count=300):
        """
        Fetches historical OHLCV candles (real exchange data, public
        endpoint). Returns a list of dicts sorted by time ascending:
            {"timestamp_ms": int, "open": float, "high": float,
             "low": float, "close": float, "volume": float}
        """
        if not instrument_name:
            raise ValueError("instrument_name is required")
        if count <= 0:
            raise ValueError("count must be > 0")

        payload = self._call_with_retries(
            f"get_candlestick({instrument_name},{timeframe})",
            CRYPTO_COM_CANDLESTICK_URL,
            {"instrument_name": instrument_name, "timeframe": timeframe, "count": count}
        )

        data = payload.get("result", {}).get("data", [])
        candles = []
        for row in data:
            if not isinstance(row, dict):
                continue
            try:
                candles.append({
                    "timestamp_ms": int(row["t"]),
                    "open": float(row["o"]),
                    "high": float(row["h"]),
                    "low": float(row["l"]),
                    "close": float(row["c"]),
                    "volume": float(row["v"])
                })
            except (KeyError, TypeError, ValueError):
                continue

        if not candles:
            raise CryptoConnectorError(
                f"No usable candles for {instrument_name} ({timeframe})"
            )
        candles.sort(key=lambda c: c["timestamp_ms"])
        return candles
