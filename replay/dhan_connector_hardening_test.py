"""
Offline regression test for the hardened DhanConnector.

Uses an injected fake dhanhq client — no credentials, no network, no market
hours required. Verifies retry/backoff, rate-limit spacing, auth fail-fast,
interface preservation, and the docs/NEXT_BUILD.md standard quote shape.
"""
from connectors.dhan_connector import DhanConnector, DhanConnectorError

print("=== DHAN CONNECTOR HARDENING TEST ===")


def make_success_response(exchange="NSE_EQ", quotes=None):
    if quotes is None:
        quotes = {
            "10176": {
                "last_price": 250.5,
                "volume": 12000,
                "last_trade_time": "2026-07-14 13:00:00",
                "depth": {
                    "buy": [{"price": 250.4, "quantity": 500, "orders": 3}],
                    "sell": [{"price": 250.6, "quantity": 400, "orders": 2}]
                }
            }
        }
    return {"status": "success", "data": {"data": {exchange: quotes}}}


class FakeDhan:
    """Scriptable fake dhanhq client: pops one canned response per call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def quote_data(self, securities):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get_fund_limits(self):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


sleeps = []


def fake_sleep(seconds):
    sleeps.append(seconds)


def make_connector(responses, max_retries=3):
    return DhanConnector(
        dhan_client=FakeDhan(responses),
        max_retries=max_retries,
        backoff_base_seconds=0.5,
        min_request_interval_seconds=0.0,
        sleep_fn=fake_sleep
    )


# 1. Interface preserved: get_last_price shape unchanged
connector = make_connector([make_success_response()])
result = connector.get_last_price("NSE_EQ", 10176)
print("get_last_price:", result)
assert result == {
    "exchange": "NSE_EQ",
    "security_id": 10176,
    "last_price": 250.5,
    "volume": 12000,
    "timestamp": "2026-07-14 13:00:00"
}

# 2. Interface preserved: get_last_prices shape unchanged (quotes + errors)
connector = make_connector([make_success_response()])
result = connector.get_last_prices("NSE_EQ", [10176, 99999])
print("get_last_prices:", result["status"], len(result["quotes"]), "quotes,",
      len(result["errors"]), "errors")
assert result["status"] == "success"
assert result["quotes"][0]["last_price"] == 250.5
assert result["errors"][0]["security_id"] == 99999

# 3. Transient transport errors are retried, then succeed
sleeps.clear()
connector = make_connector([
    ConnectionError("boom"),
    ConnectionError("boom again"),
    make_success_response()
])
result = connector.get_last_price("NSE_EQ", 10176)
print("retry-after-transport-errors: OK, backoff sleeps:", sleeps)
assert result["last_price"] == 250.5
assert sleeps == [0.5, 1.0]  # exponential backoff

# 4. Rate-limit failure responses are retried
sleeps.clear()
connector = make_connector([
    {"status": "failure", "remarks": {"error_code": "805", "error_message": "Too many requests"}},
    make_success_response()
])
result = connector.get_last_price("NSE_EQ", 10176)
print("retry-after-rate-limit: OK")
assert result["last_price"] == 250.5

# 5. Auth failure fails fast — NOT retried
connector = make_connector([
    {"status": "failure", "remarks": "Token expired, unauthorized"},
    make_success_response()  # must never be reached
])
try:
    connector.get_last_price("NSE_EQ", 10176)
    raise AssertionError("expected DhanConnectorError on auth failure")
except DhanConnectorError as e:
    print("auth fail-fast: OK")
    assert connector.dhan.calls == 1, "auth failure must not be retried"

# 6. Exhausted retries raise DhanConnectorError
connector = make_connector(
    [ConnectionError("x")] * 4,
    max_retries=3
)
try:
    connector.get_last_price("NSE_EQ", 10176)
    raise AssertionError("expected DhanConnectorError after exhausted retries")
except DhanConnectorError:
    print("retry exhaustion: OK")
    assert connector.dhan.calls == 4  # initial + 3 retries

# 7. Rate-limit spacing between consecutive requests
sleeps.clear()
connector = DhanConnector(
    dhan_client=FakeDhan([make_success_response(), make_success_response()]),
    min_request_interval_seconds=10.0,  # deliberately huge so a sleep must occur
    sleep_fn=fake_sleep
)
connector.get_last_price("NSE_EQ", 10176)
connector.get_last_price("NSE_EQ", 10176)
print("rate-limit spacing sleeps:", sleeps)
assert len(sleeps) == 1 and sleeps[0] > 9.0

# 8. Standard quote shape per docs/NEXT_BUILD.md
connector = make_connector([make_success_response()])
result = connector.get_standard_quotes("NSE_EQ", [10176], symbol_map={10176: "SETFNIF50"})
q = result["quotes"][0]
print("standard quote:", q)
assert set(q.keys()) == {
    "source", "asset", "bid", "ask", "last_price",
    "currency", "timestamp", "liquidity_score"
}
assert q["source"] == "dhan"
assert q["asset"] == "SETFNIF50"
assert q["bid"] == 250.4
assert q["ask"] == 250.6
assert q["currency"] == "INR"
assert 0.0 < q["liquidity_score"] <= 1.0

# 9. Standard quote degrades cleanly without depth
no_depth = make_success_response(quotes={
    "10176": {"last_price": 100.0, "volume": 1, "last_trade_time": "2026-07-14 13:00:00"}
})
connector = make_connector([no_depth])
result = connector.get_standard_quotes("NSE_EQ", [10176])
q = result["quotes"][0]
print("no-depth standard quote:", q)
assert q["bid"] is None and q["ask"] is None
assert q["liquidity_score"] == 0.0
assert q["asset"] == "NSE_EQ:10176"

# 10. No order-placement surface: connector must not expose buy/sell/order methods
forbidden = [name for name in dir(connector)
             if any(word in name.lower() for word in ("place_order", "buy", "sell", "cancel_order", "modify_order"))]
print("order-api surface check:", forbidden)
assert forbidden == [], f"connector must stay read-only, found: {forbidden}"

print("\nALL DHAN CONNECTOR HARDENING TESTS PASSED")
