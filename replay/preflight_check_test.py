"""
Adversarial test for scripts/preflight_check.py.

Deliberately breaks each precondition and asserts the check reports the
RIGHT failure with an actionable remedy — no vague 'check config'.
Fully offline except one real network probe.
"""
import base64
import io
import json
import pathlib
import sys
import tempfile
import time
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "scripts")
from preflight_check import (
    Check, check_dhan_token, check_market_hours, check_redis,
    check_engines, summarize, decode_jwt_exp, GREEN, RED, AMBER
)

print("=== PREFLIGHT CHECK ADVERSARIAL TEST ===")

tmpdir = pathlib.Path(tempfile.mkdtemp())


def write_env(content):
    p = tmpdir / f"env_{time.monotonic_ns()}"
    p.write_text(content, encoding="utf-8")
    return str(p)


def make_jwt(exp_epoch):
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": exp_epoch}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.fakesig"


# 1. Missing credentials
res = check_dhan_token(write_env("DHAN_CLIENT_ID=\nDHAN_ACCESS_TOKEN=\n"))
print("missing creds:", res.status, "|", res.detail[:60])
assert res.status == RED
assert "missing/empty" in res.detail
assert "Dhan web portal" in res.remedy

# 2. Malformed token (not a JWT)
res = check_dhan_token(write_env("DHAN_CLIENT_ID=123\nDHAN_ACCESS_TOKEN=not-a-jwt\n"))
print("bad format:", res.status, "|", res.detail[:60])
assert res.status == RED
assert "malformed" in res.detail
assert "Regenerate" in res.remedy

# 3. Expired token (local check catches it before any API call)
expired = make_jwt(int((datetime.now(timezone.utc) - timedelta(days=5)).timestamp()))
res = check_dhan_token(write_env(f"DHAN_CLIENT_ID=123\nDHAN_ACCESS_TOKEN={expired}\n"))
print("expired token:", res.status, "|", res.detail[:60])
assert res.status == RED
assert "EXPIRED" in res.detail
assert "Regenerate" in res.remedy

# 4. Valid-looking future token with API skipped -> local PASS
future = make_jwt(int((datetime.now(timezone.utc) + timedelta(days=20)).timestamp()))
res = check_dhan_token(write_env(f"DHAN_CLIENT_ID=123\nDHAN_ACCESS_TOKEN={future}\n"),
                       live_api=False)
print("future token (local only):", res.status, "|", res.detail[:60])
assert res.status == GREEN
assert "local check only" in res.detail

# 5. Market hours: Sunday / holiday / after-hours / open
sunday = datetime(2026, 7, 12, 6, 0, tzinfo=timezone.utc)          # Sun 11:30 IST
holiday = datetime(2026, 1, 26, 6, 0, tzinfo=timezone.utc)         # Republic Day (a Monday)
after_hours = datetime(2026, 7, 14, 12, 30, tzinfo=timezone.utc)   # Tue 18:00 IST
open_time = datetime(2026, 7, 14, 6, 0, tzinfo=timezone.utc)       # Tue 11:30 IST

res = check_market_hours(sunday)
print("sunday:", res.status, "|", res.detail[:50])
assert res.status == RED and "weekend" in res.detail

res = check_market_hours(holiday)
print("holiday:", res.status, "|", res.detail[:50])
assert res.status == RED and "holiday" in res.detail

res = check_market_hours(after_hours)
print("after hours:", res.status, "|", res.detail[:50])
assert res.status == RED and "outside_hours" in res.detail

res = check_market_hours(open_time)
print("open:", res.status, "|", res.detail[:50])
assert res.status == GREEN

# 6. Redis down (true on this machine) -> WARN, never a required failure
res = check_redis()
print("redis:", res.status, "| required:", res.required)
assert res.required is False
assert res.status in (GREEN, AMBER)
if res.status == AMBER:
    assert "OPTIONAL" in res.remedy

# 7. Engines import (skip subprocess tests for speed)
res = check_engines(skip_tests=True)
print("engines:", res.status, "|", res.detail[:60])
assert res.status == GREEN

# 8. summarize(): any required failure -> exit 1 and remedies printed
buf = io.StringIO()
failing = Check("Dhan credentials valid", required=True).fail("token EXPIRED", "Regenerate it")
passing = Check("Network", required=True).ok("fine")
optional_fail = check_redis()
with redirect_stdout(buf):
    code = summarize([failing, passing, optional_fail])
out = buf.getvalue()
assert code == 1
assert "NOT READY" in out and "Regenerate it" in out
print("summarize failure path: exit 1 + remedy shown")

# 9. summarize(): all required green (optional WARN allowed) -> exit 0 + launch commands
buf = io.StringIO()
with redirect_stdout(buf):
    code = summarize([
        Check("Dhan credentials valid").ok("token fine, API ok"),
        Check("NSE market open").ok("open"),
        optional_fail,  # Redis WARN must not block
        Check("Network").ok("fine"),
        Check("Phase 2 engines").ok("pass")
    ])
out = buf.getvalue()
assert code == 0
assert "ALL REQUIRED CHECKS PASSED" in out
assert "run_live_paper_trading.py" in out
assert "run_inefficiency_session.py" in out
assert "fno_dashboard.py" in out
print("summarize success path: exit 0 + launch commands printed")

# 10. decode_jwt_exp edge cases
assert decode_jwt_exp("one.two")[1] is not None
assert decode_jwt_exp("a.!!!.c")[1] is not None
no_exp = make_jwt(0).rsplit(".", 1)[0]
hdr = base64.urlsafe_b64encode(b'{"alg":"x"}').rstrip(b"=").decode()
pl = base64.urlsafe_b64encode(b'{"foo":1}').rstrip(b"=").decode()
assert decode_jwt_exp(f"{hdr}.{pl}.s")[1] == "JWT payload has no numeric 'exp' claim"
print("jwt decode edge cases: OK")

print("\nALL PREFLIGHT ADVERSARIAL TESTS PASSED")
