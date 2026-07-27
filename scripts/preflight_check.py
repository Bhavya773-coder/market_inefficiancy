"""
Preflight / readiness watchdog for a live NSE paper-trading session.

Runs ordered checks and prints an unambiguous PASS/FAIL per check, then
either the exact launch commands (all green) or exactly what is blocking
and what to do about it.

Usage:
    PYTHONPATH=. python scripts/preflight_check.py
    # test overrides:
    #   --env-file PATH   check a different .env
    #   --now ISO8601     pretend it is this time (market-hours check)
    #   --skip-engine-tests  skip re-running Phase 2 engine tests (faster)

Exit code 0 only when every REQUIRED check passes.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import requests
from dotenv import dotenv_values

# Reuse the runner's market-hours logic — one source of truth.
from live.run_live_paper_trading import is_market_open_now

DHAN_API_HOST = "https://api.dhan.co"

ENGINE_TESTS = [
    "replay/settlement_engine_test.py",
    "replay/capital_engine_test.py",
    "replay/liquidity_engine_test.py",
    "replay/opportunity_ranking_engine_test.py",
    "replay/live_opportunity_gate_test.py"
]

GREEN = "PASS"
RED = "FAIL"
AMBER = "WARN"


class Check:
    def __init__(self, name, required=True):
        self.name = name
        self.required = required
        self.status = None
        self.detail = ""
        self.remedy = ""

    def ok(self, detail=""):
        self.status = GREEN
        self.detail = detail
        return self

    def fail(self, detail, remedy):
        self.status = RED if self.required else AMBER
        self.detail = detail
        self.remedy = remedy
        return self


def decode_jwt_exp(token):
    """Returns (exp_datetime_utc, None) or (None, error_string)."""
    parts = token.split(".")
    if len(parts) != 3:
        return None, "token is not a JWT (expected 3 dot-separated parts)"
    try:
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as e:
        return None, f"cannot decode JWT payload ({type(e).__name__})"
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return None, "JWT payload has no numeric 'exp' claim"
    return datetime.fromtimestamp(exp, tz=timezone.utc), None


def check_dhan_token(env_file, live_api=True):
    check = Check("Dhan credentials valid (token not expired, API accepts it)")
    values = dotenv_values(env_file)
    client_id = (values.get("DHAN_CLIENT_ID") or "").strip()
    token = (values.get("DHAN_ACCESS_TOKEN") or "").strip()

    if not client_id or not token:
        return check.fail(
            f"DHAN_CLIENT_ID or DHAN_ACCESS_TOKEN missing/empty in {env_file}",
            "Add both values to .env (Dhan web portal -> My Profile -> Access DhanHQ APIs)."
        )

    exp_dt, err = decode_jwt_exp(token)
    if err:
        return check.fail(
            f"DHAN_ACCESS_TOKEN malformed: {err}",
            "Regenerate the access token in the Dhan web portal and paste the full JWT into .env."
        )

    now = datetime.now(timezone.utc)
    if exp_dt <= now:
        return check.fail(
            f"token EXPIRED {exp_dt.isoformat()} (now {now.isoformat()})",
            "Regenerate the access token in the Dhan web portal (tokens last ~30 days), update .env."
        )

    if not live_api:
        return check.ok(f"token expires {exp_dt.isoformat()} (local check only, API not called)")

    # Real API verification — fund limits works outside market hours too.
    try:
        os.environ["DHAN_CLIENT_ID"] = client_id
        os.environ["DHAN_ACCESS_TOKEN"] = token
        from connectors.dhan_connector import DhanConnector, DhanConnectorError
        try:
            response = DhanConnector(max_retries=1).get_fund_limits()
        except DhanConnectorError as e:
            return check.fail(
                f"Dhan API rejected the token: {e}",
                "Regenerate the access token in the Dhan web portal, update .env, rerun preflight."
            )
        if isinstance(response, dict) and response.get("status") == "failure":
            return check.fail(
                f"Dhan API returned failure: {response.get('remarks')}",
                "Regenerate the access token in the Dhan web portal, update .env, rerun preflight."
            )
        return check.ok(f"token expires {exp_dt.isoformat()}; Dhan API call succeeded")
    except Exception as e:
        return check.fail(
            f"unexpected error calling Dhan API: {type(e).__name__}: {e}",
            "Check network connectivity to api.dhan.co, then retry."
        )


def check_market_hours(now_override=None):
    check = Check("NSE market open (9:15-15:30 IST, Mon-Fri, non-holiday)")
    now = now_override or datetime.now(timezone.utc)
    is_open, reason = is_market_open_now(now)
    ist = now.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    if is_open:
        return check.ok(f"market open now ({ist.strftime('%Y-%m-%d %H:%M IST')})")
    return check.fail(
        f"market closed: {reason} ({ist.strftime('%Y-%m-%d %H:%M IST')})",
        "Run this again on a trading day between 9:15 and 15:30 IST."
    )


def check_redis():
    check = Check("Redis reachable (learning-brain dashboard only)", required=False)
    try:
        import redis
        client = redis.Redis(host="localhost", port=6379, socket_connect_timeout=3)
        client.ping()
        return check.ok("localhost:6379 responded to PING")
    except Exception as e:
        return check.fail(
            f"Redis not reachable on localhost:6379 ({type(e).__name__})",
            "OPTIONAL: only the Redis learning-brain/live_dashboard.py needs it. "
            "The paper-trading runners work without Redis. To enable: install and "
            "start a Redis server (e.g. Memurai on Windows, or Docker)."
        )


def check_network():
    check = Check("Network reachable (Dhan endpoint)")
    problems = []
    for name, url in [("Dhan", DHAN_API_HOST)]:
        try:
            requests.get(url, timeout=8)
        except Exception as e:
            problems.append(f"{name} unreachable ({type(e).__name__})")
    if problems:
        return check.fail(
            "; ".join(problems),
            "Check the internet connection / VPN / firewall, then rerun preflight."
        )
    return check.ok("both endpoints answered HTTPS")


def check_engines(skip_tests=False):
    check = Check("Phase 2 engines importable and their tests passing")
    try:
        from inefficiency.settlement_engine import SettlementEngine        # noqa: F401
        from inefficiency.capital_engine import CapitalEngine              # noqa: F401
        from inefficiency.liquidity_engine import LiquidityEngine          # noqa: F401
        from inefficiency.opportunity_ranking_engine import OpportunityRankingEngine  # noqa: F401
        from ai.live_opportunity_gate import LiveOpportunityGate           # noqa: F401
    except Exception as e:
        return check.fail(
            f"import failed: {type(e).__name__}: {e}",
            "The codebase is broken — fix the import error before launching anything."
        )
    if skip_tests:
        return check.ok("all engines import (tests skipped via --skip-engine-tests)")

    env = dict(os.environ, PYTHONPATH=".")
    for test in ENGINE_TESTS:
        result = subprocess.run(
            [sys.executable, test], capture_output=True, text=True, env=env
        )
        if result.returncode != 0:
            tail = (result.stdout + result.stderr).strip().splitlines()[-3:]
            return check.fail(
                f"{test} FAILED: {' | '.join(tail)}",
                f"Run `PYTHONPATH=. python {test}` and fix the failure before launching."
            )
    return check.ok(f"{len(ENGINE_TESTS)} engine test scripts passed")


def main():
    parser = argparse.ArgumentParser(description="Live-session preflight check")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--now", default=None,
                        help="ISO-8601 override for the market-hours check (testing)")
    parser.add_argument("--skip-engine-tests", action="store_true")
    parser.add_argument("--skip-live-api", action="store_true",
                        help="Skip the real Dhan API call (local token checks only)")
    args = parser.parse_args()

    now_override = None
    if args.now:
        now_override = datetime.fromisoformat(args.now)
        if now_override.tzinfo is None:
            now_override = now_override.replace(tzinfo=timezone.utc)

    print("=" * 64)
    print("PREFLIGHT CHECK — live paper-trading readiness")
    print(f"run at: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 64)

    checks = [
        check_dhan_token(args.env_file, live_api=not args.skip_live_api),
        check_market_hours(now_override),
        check_redis(),
        check_network(),
        check_engines(skip_tests=args.skip_engine_tests)
    ]

    sys.exit(summarize(checks))


def summarize(checks):
    """Prints per-check results + verdict. Returns process exit code."""
    print()
    for i, c in enumerate(checks, 1):
        tag = "REQUIRED" if c.required else "OPTIONAL"
        print(f"[{c.status}] {i}. {c.name}  ({tag})")
        print(f"       {c.detail}")
        if c.status != GREEN and c.remedy:
            print(f"       FIX: {c.remedy}")
    print()

    required_failures = [c for c in checks if c.required and c.status != GREEN]
    if not required_failures:
        print("ALL REQUIRED CHECKS PASSED — launch commands:")
        print()
        print("  # NSE live paper-trading session (runs until market close):")
        print("  PYTHONPATH=. python live/run_live_paper_trading.py \\")
        print("      --output-dir storage/live_nse_$(date +%Y%m%d) --poll-interval 1")
        print()
        print("  # F&O / spot inefficiency session (all Dhan-reachable markets):")
        print("  PYTHONPATH=. python scripts/run_inefficiency_session.py --watch \\")
        print("      --capital 1000000 --output-dir storage/session_$(date +%Y%m%d)")
        print()
        print("  # F&O dashboard (open http://localhost:8730 after starting):")
        print("  PYTHONPATH=. python live/fno_dashboard.py \\")
        print("      --session-dir storage/session_$(date +%Y%m%d)")
        return 0

    print(f"NOT READY — {len(required_failures)} required check(s) failing:")
    for c in required_failures:
        print(f"  - {c.name}")
        print(f"    -> {c.remedy}")
    return 1


if __name__ == "__main__":
    main()
