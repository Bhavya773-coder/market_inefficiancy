# MVP READINESS REPORT

Date: 2026-07-14 (evening session, ~16:40–19:00 IST)
Branch: feature/live-paper-trading
Full offline regression at end of session: **36/36 PASS**

Every claim below traces to a command run this session with output
observed. Where something failed, the failure is stated, not smoothed.

----------------------------------------

## 1. WHAT'S REAL AND DEMOABLE RIGHT NOW — the crypto live pipeline

The full chain ran end-to-end today against the real Crypto.com public
API, with zero mock data:

    real quotes → lag detection → OpportunityRankingEngine gate
    (cost + settlement + capital + liquidity) → paper entries/exits
    → JSONL audit trail → live dashboard

Proof (35-minute sustained live session, `storage/crypto_live_session_20260714/`):

- **426 poll ticks, 2,130 real quotes, 0 poll errors** after the
  connection-pooling fix (the first attempt wedged at ~8 minutes with
  ConnectionErrors — root-caused to per-request TCP churn, fixed with a
  pooled session + single-call batch tickers + auto session-reset,
  regression-tested, rerun from scratch clean).
- **222 lag signals detected; 207 blocked by the ranking engine** with
  logged reasons (`below_min_annualized_return` on all 207; 205 also
  `not_profitable_after_round_trip_costs`) — the Phase 2 economics are
  genuinely deciding, not rubber-stamping.
- **3 paper entries filled** (BTC_USDT, SOL_USDT, LTC_USDT), each with
  the full engine breakdown logged (sample: net edge 0.82%, annualized
  299.5%, liquidity score 0.9999).
- Clean shutdown with session summary: final mark-to-market
  999,981.77 on 1,000,000 start (**PnL −18.23**, i.e. −0.0018% — flat,
  honestly reported).
- **Dashboard verified live in a browser**: real-time quotes (feed age
  <2s), "REAL LIVE FEED" tag on crypto_com_live, honest EXPIRED badge on
  the Dhan token, honest CLOSED badge on NSE market hours, opportunity
  flow with per-signal verdicts, PAPER EXECUTION ONLY banner.
  Launch: `PYTHONPATH=. python live/dashboard_server.py --session-dir <dir>`

What this does NOT prove: profitable edge. See section 3's calibration
result.

## 2. BUILT AND TESTED, WAITING ON YOU — the NSE side

The moment a fresh Dhan token is in `.env`, this happens with no code
changes:

1. `PYTHONPATH=. python scripts/preflight_check.py` goes green on
   check 1 (it verifies the token against the real Dhan API, not just
   the string) and prints the exact launch commands.
2. `live/run_live_paper_trading.py` polls real NSE quotes through the
   hardened connector (retries, backoff, rate-limit spacing), runs
   detection, and — new today — routes **every** entry through the same
   OpportunityRankingEngine gate as crypto, logging blocked
   opportunities with reasons.
3. The same dashboard points at the NSE session directory.

Wiring proof executed today (`replay/live_opportunity_gate_test.py`):
a 0.15% edge candidate that the OLD flat-cost check approves is
REJECTED by the ranking engine (`below_min_annualized_return`), and the
paper-trade outcome follows the ranking engine's verdict — 8 scenarios,
all asserted. The runner smoke test additionally proves a force-blocked
gate prevents all entries end-to-end.

Preflight was adversarially tested: bad token format, expired JWT,
weekend/holiday/after-hours clocks, Redis down — each reports the right
failure with a concrete fix line, exit code 1. (13 assertions, all pass.)

## 3. EXPLICITLY SIMULATED / NOT REAL — say none of this is live

- **Steel and gold "commodity" detection**: logic is real and heavily
  tested (10+ offline suites), but it has NEVER seen a steel or gold
  price. Live mode maps registry symbols to NSE ETFs as stand-ins
  (e.g. "BALTIC_DRY" → NIFTYBEES) and dry-run mode uses hand-authored
  fixtures. No accessible steel/gold data source exists in this
  environment. All outputs remain `is_historically_calibrated: False`.
- **Signal-graph weights** (steel/gold): hand-picked constants, not fitted.
- **The Redis learning brain** (`ai/execution_engine.py` etc.):
  fabricates fills and PnL with `random`; additionally unrunnable here
  (no Redis). Not part of the demo path.
- **Detection edge, including crypto**: calibration on REAL data
  (300×1m and 300×15m Crypto.com candles, 20 instrument pairs,
  `scripts/calibrate_crypto_lag.py`) found **no threshold where lag
  events historically beat round-trip costs** (best win rate ~31%,
  mean capture below the 0.12% cost bar). The calibrator therefore
  refused to flip any `is_historically_calibrated` flag. The heuristic
  0.05% threshold stays, honestly labeled heuristic. Evidence:
  `storage/calibration/crypto_lag_calibration*.json`.

## 4. NOT BUILT AT ALL

- MCX, LME, COMEX, Forex connectors — no data access from this
  environment; deliberately not stubbed.
- Phase 5 (Delivery Fallback): no inventory/procurement/delivery code.
- Phase 7 (Commercial platform): no auth, no persistence beyond JSONL,
  no alerting; the dashboard is a single-user local view.
- Phase 6 note: GPU is NOT blocked — an RTX 4050 with CUDA 13.3 was
  reached today (`cupy-cuda13x[ctk]` installed). The batch scorer's
  columnar path benchmarked **43.4M candidates/s on GPU vs 6.0M/s
  numpy (x7.2) vs ~0.29M/s scalar**, with parity asserted against the
  scalar engine on 1M candidates. Honest caveat: on realistic dict-based
  workloads (≤20k candidates) the batch paths are SLOWER than the plain
  loop (x0.7) — conversion dominates. GPU only matters at massive
  columnar scale, which nothing in the live loop needs today.

## 5. CAN I SHOW THIS TO A CUSTOMER TOMORROW?

Yes — as an infrastructure demo, not a returns pitch. You can truthfully
say: "This system ingests live market data (crypto today, NSE equities
as soon as our broker token refreshes), detects cross-instrument
reaction lags, and — before any simulated trade — prices the full round
trip: brokerage, taxes, spread, market-impact slippage, settlement
lock-up financing, capital efficiency and liquidity, then blocks
anything that doesn't clear those hurdles, with every decision logged
and auditable on a live dashboard. Execution is paper-only by design."
You may NOT say it makes money: our own calibration on real data shows
the current lag signal does not historically beat costs, the visible
session PnL is flat (−18 on 1M), and steel/gold commodity detection has
never touched real commodity data. If asked "does it work?", the honest
answer is: "the machinery works end-to-end and rejects bad trades
correctly; a profitable signal is the open research problem."

----------------------------------------

## TOMORROW MORNING RUNBOOK (copy-paste)

    # 0. Get a fresh access token from the Dhan web portal
    #    (My Profile -> Access DhanHQ APIs), then edit .env:
    #    DHAN_ACCESS_TOKEN=<new JWT>

    cd market_terminal   # repo root

    # 1. Preflight — must end with "ALL REQUIRED CHECKS PASSED"
    PYTHONPATH=. python scripts/preflight_check.py

    # 2. Launch the live NSE paper session (weekday 9:15-15:30 IST)
    PYTHONPATH=. python live/run_live_paper_trading.py \
        --output-dir storage/live_nse_20260715 --poll-interval 1

    # 3. Dashboard (second terminal), open http://127.0.0.1:8720
    PYTHONPATH=. python live/dashboard_server.py \
        --session-dir storage/live_nse_20260715

    # 4. Optional: crypto session in parallel (works any hour)
    PYTHONPATH=. python live/run_live_crypto_paper_trading.py \
        --duration 3600 --output-dir storage/crypto_live_20260715

    # 5. After the first hour, readiness score
    PYTHONPATH=. python replay/live_dhan_engine_readiness_test.py

Readiness-score prediction (to VERIFY, not a guarantee): with a valid
token during market hours, categories 1–5 (creds, retrieval, activity,
sync, freshness — 70 pts) should pass on infrastructure now proven
against crypto; categories 6–9 (movement, lag opportunity, feasibility,
entry) depend on the market actually moving inside the 3-second test
window, so scores of 70–100 are plausible and NOT_READY is still
possible in a quiet minute because the lag-pipeline category hard-gates
the grade (known rubric quirk, replay/live_dhan_engine_readiness_test.py:150).
Yesterday's 10/100 was purely the expired token.

    # 6. Write TODAY_MVP_DEMO_REPORT.md scoring the NSE session with the
    #    same honesty as the crypto one (entries/blocked/PnL/errors from
    #    storage/live_nse_20260715/paper_trades.jsonl).

----------------------------------------

## Session traceability

Commits (this session): `Wire opportunity ranking engine into live entry
gating`, `Add live crypto paper trading runner with gated entries`,
`Add preflight readiness watchdog with adversarial tests`, `Fix crypto
polling with pooled session, batch fetch and reset recovery`, `Add
crypto lag calibrator; real data declines to calibrate`, `Add batch
opportunity scorer with GPU backend and parity tests`, `Add live
dashboard with honest data tagging; harden quote validation`, `Add
data-gap regression for dashboard state`, plus this report and doc
updates.

Test inventory: 36 offline asserting suites — 29 pre-existing + 7 new
today (gate wiring, runner smoke, crypto runner, preflight adversarial,
calibrator, batch scorer parity/benchmark, dashboard). 9 live-Dhan
scripts remain blocked on the token. Live crypto evidence:
`storage/crypto_live_session_20260714/` (completed 35-min run) and
`storage/crypto_live_dash_demo/` (dashboard verification session).
