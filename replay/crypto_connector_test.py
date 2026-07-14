"""
Regression test for CryptoConnector.

Part 1 is fully offline (injected fake transport). Part 2 is an optional
live smoke test against the public Crypto.com API — it runs only when
CRYPTO_CONNECTOR_LIVE_TEST=1, needs no credentials, and asserts only on
shape, not on prices.
"""
import os

from connectors.crypto_connector import CryptoConnector, CryptoConnectorError

print("=== CRYPTO CONNECTOR TEST (offline) ===")


def make_ticker_payload(instrument="BTC_USDT", last="62521.15",
                        bid="62521.14", ask="62521.15", ts=1784015231350):
    return {
        "id": -1,
        "method": "public/get-tickers",
        "code": 0,
        "result": {
            "data": [{
                "i": instrument, "a": last, "b": bid, "k": ask,
                "v": "2142.69", "t": ts
            }]
        }
    }


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, url, params):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


sleeps = []


def fake_sleep(seconds):
    sleeps.append(seconds)


def make_connector(responses, **kwargs):
    return CryptoConnector(
        http_get=FakeHttp(responses),
        min_request_interval_seconds=0.0,
        sleep_fn=fake_sleep,
        **kwargs
    )


# 1. Standard shape per docs/NEXT_BUILD.md
connector = make_connector([make_ticker_payload()])
result = connector.get_standard_quotes(["BTC_USDT"])
q = result["quotes"][0]
print("standard quote:", q)
assert set(q.keys()) == {
    "source", "asset", "bid", "ask", "last_price",
    "currency", "timestamp", "liquidity_score"
}
assert q["source"] == "crypto_com"
assert q["asset"] == "BTC_USDT"
assert q["bid"] == 62521.14
assert q["ask"] == 62521.15
assert q["last_price"] == 62521.15
assert q["currency"] == "USDT"
assert q["timestamp"].startswith("2026-")
assert 0.0 < q["liquidity_score"] <= 1.0

# 2. Transient transport errors retried with exponential backoff
sleeps.clear()
connector = make_connector([
    ConnectionError("down"),
    ConnectionError("still down"),
    make_ticker_payload()
])
result = connector.get_standard_quotes(["BTC_USDT"])
print("retry backoff sleeps:", sleeps)
assert result["quotes"][0]["last_price"] == 62521.15
assert sleeps == [0.5, 1.0]

# 3. Non-zero API code retried, then per-instrument error when exhausted
connector = make_connector(
    [{"code": 40004, "message": "bad"}] * 4 + [make_ticker_payload("ETH_USDT", "3000")],
    max_retries=3
)
result = connector.get_standard_quotes(["BTC_USDT", "ETH_USDT"])
print("partial failure:", len(result["quotes"]), "quotes,", len(result["errors"]), "errors")
assert len(result["quotes"]) == 1
assert result["quotes"][0]["asset"] == "ETH_USDT"
assert len(result["errors"]) == 1
assert result["errors"][0]["instrument_name"] == "BTC_USDT"

# 4. All instruments failing raises CryptoConnectorError
connector = make_connector([{"code": 500}] * 4, max_retries=3)
try:
    connector.get_standard_quotes(["BTC_USDT"])
    raise AssertionError("expected CryptoConnectorError")
except CryptoConnectorError:
    print("total failure raises: OK")

# 5. Missing bid/ask degrades to liquidity_score 0.0
payload = make_ticker_payload(bid=None, ask=None)
connector = make_connector([payload])
result = connector.get_standard_quotes(["BTC_USDT"])
q = result["quotes"][0]
print("no bid/ask:", q["bid"], q["ask"], q["liquidity_score"])
assert q["bid"] is None and q["ask"] is None
assert q["liquidity_score"] == 0.0

# 6. Empty ticker data is a per-instrument error
connector = make_connector([
    {"code": 0, "result": {"data": []}},
    make_ticker_payload("ETH_USDT")
])
result = connector.get_standard_quotes(["BTC_USDT", "ETH_USDT"])
assert result["errors"][0]["instrument_name"] == "BTC_USDT"
print("empty data handled: OK")

# 7. Empty instrument list is an explicit error
try:
    make_connector([]).get_standard_quotes([])
    raise AssertionError("expected ValueError")
except ValueError:
    print("empty instrument list rejected: OK")

# 8. No order-placement surface
forbidden = [name for name in dir(connector)
             if any(word in name.lower() for word in ("place_order", "buy", "sell", "cancel_order", "modify_order", "withdraw", "transfer"))]
assert forbidden == [], f"connector must stay read-only, found: {forbidden}"
print("order-api surface check: OK")

print("\nALL OFFLINE CRYPTO CONNECTOR TESTS PASSED")

# ---------------------------------------------------------------------
# Optional live smoke test (public API, no credentials)
# ---------------------------------------------------------------------
if os.getenv("CRYPTO_CONNECTOR_LIVE_TEST") == "1":
    print("\n=== CRYPTO CONNECTOR LIVE SMOKE TEST ===")
    live = CryptoConnector()
    result = live.get_standard_quotes(["BTC_USDT", "ETH_USDT"])
    for q in result["quotes"]:
        print("live:", q)
        assert q["last_price"] > 0
        assert q["source"] == "crypto_com"
    assert len(result["quotes"]) >= 1
    print("LIVE SMOKE TEST PASSED")
else:
    print("(live smoke test skipped; set CRYPTO_CONNECTOR_LIVE_TEST=1 to run)")
