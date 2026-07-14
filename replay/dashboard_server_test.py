"""
Offline test for live/dashboard_server.py.

Builds a synthetic session directory, asserts the /api/state JSON and
the HTML page over a real HTTP round trip, and verifies the honesty
tagging: simulated feeds MUST surface is_simulated_data=True.
"""
import json
import pathlib
import shutil
import threading
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer

from live.dashboard_server import DashboardState, make_handler, DASHBOARD_HTML

print("=== DASHBOARD SERVER TEST (offline) ===")

SESSION = pathlib.Path("storage/test_dashboard_session")
shutil.rmtree(SESSION, ignore_errors=True)
SESSION.mkdir(parents=True)

now_iso = datetime.now(timezone.utc).isoformat()

(SESSION / "quotes.jsonl").write_text(json.dumps({
    "timestamp": now_iso,
    "quotes": {
        "BTC_USDT": {"last_price": 62000.0, "bid": 61999.0, "ask": 62001.0,
                     "timestamp": now_iso, "data_source": "crypto_com_live"},
        "ETH_USDT": {"last_price": 1780.0, "bid": 1779.9, "ask": 1780.1,
                     "timestamp": now_iso, "data_source": "crypto_com_live"}
    }
}) + "\n", encoding="utf-8")

(SESSION / "detections.jsonl").write_text(json.dumps({
    "timestamp": now_iso, "type": "lag_signal",
    "lag_result": {"reference_symbol": "BTC_USDT", "target_symbol": "ETH_USDT"}
}) + "\n", encoding="utf-8")

trades = [
    {"timestamp": now_iso, "type": "blocked", "symbol": "ETH_USDT", "price": 1780.0,
     "lag_reference": "BTC_USDT", "rejection_reasons": ["below_min_annualized_return"]},
    {"timestamp": now_iso, "type": "entry", "symbol": "ETH_USDT", "price": 1780.0,
     "quantity": 1, "lag_reference": "BTC_USDT",
     "gate_evaluation": {"annualized_return_pct": 120.0, "net_profit_pct": 0.4,
                          "liquidity_score": 0.99, "rank_score": 118.8},
     "execution": {"status": "filled"},
     "account": {"starting_cash": 100000.0, "cash": 98220.0,
                 "positions": {"ETH_USDT": {"quantity": 1, "average_price": 1780.0}},
                 "trade_log": [], "portfolio_value": 100000.0}}
]
(SESSION / "paper_trades.jsonl").write_text(
    "".join(json.dumps(t) + "\n" for t in trades), encoding="utf-8")

# 1. State builder: live feed recognized, positions marked to market
state = DashboardState(SESSION).build()
assert state["execution_mode"].startswith("PAPER ONLY")
assert state["is_simulated_data"] is False, "crypto_com_live must count as real"
assert state["data_sources"] == ["crypto_com_live"]
assert state["health"]["session_feed"] == "LIVE"
assert state["counters"] == {"entries": 1, "exits": 0, "blocked": 1, "detections_seen": 1}
assert state["positions"][0]["symbol"] == "ETH_USDT"
assert state["positions"][0]["mark_price"] == 1780.0
assert abs(state["account"]["mark_to_market_value"] - 100000.0) < 1e-9
kinds = [o["kind"] for o in state["opportunities"]]
assert "ENTRY" in kinds and "BLOCKED" in kinds
entry_row = next(o for o in state["opportunities"] if o["kind"] == "ENTRY")
assert entry_row["gate"]["annualized_return_pct"] == 120.0
print("state builder (live feed): OK")

# 2. Dhan token status honestly reported (repo .env token is expired/missing)
assert state["health"]["dhan_token"]["status"] in ("VALID", "EXPIRED", "MISSING", "MALFORMED")
print("dhan token status:", state["health"]["dhan_token"]["status"])

# 3. Honesty: a simulated feed flips the SIMULATED tag
(SESSION / "quotes.jsonl").write_text(json.dumps({
    "timestamp": now_iso,
    "quotes": {"X": {"last_price": 1.0, "data_source": "smoke_test"}}
}) + "\n", encoding="utf-8")
sim_state = DashboardState(SESSION).build()
assert sim_state["is_simulated_data"] is True, "non-live source must be tagged SIMULATED"
print("simulated-data tagging: OK")

# 4. Real HTTP round trip: /api/state and /
server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(DashboardState(SESSION)))
port = server.server_address[1]
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5) as resp:
    api = json.loads(resp.read())
assert api["is_simulated_data"] is True
with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
    html = resp.read().decode("utf-8")
assert "PAPER EXECUTION ONLY" in html
assert "SIMULATED DATA" in DASHBOARD_HTML  # honesty badge wired into the page

try:
    urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=5)
    raise AssertionError("expected HTTP 404")
except urllib.error.HTTPError as e:
    assert e.code == 404
print("HTTP round trip (/, /api/state, 404): OK")

server.shutdown()

# 5. BUG HUNT (Item 7): empty/missing session dir (data gap) must render a
#    truthful NO DATA state, not crash.
empty_state = DashboardState("storage/does_not_exist_session").build()
assert empty_state["health"]["session_feed"] == "NO DATA"
assert empty_state["quotes"] == {}
assert empty_state["positions"] == []
assert empty_state["counters"]["entries"] == 0
print("empty session dir (data gap): OK")

shutil.rmtree(SESSION, ignore_errors=True)
print("\nALL DASHBOARD SERVER TESTS PASSED")
