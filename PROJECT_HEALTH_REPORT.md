# PROJECT HEALTH REPORT

Date: 2026-07-14 (Tuesday, NSE trading day)
Session window: ~12:45–14:00 IST, NSE market open (9:15–15:30 IST)
Auditor: Claude (AI developer session)
Branch: feature/live-paper-trading

Every claim below traces to a command executed in this session and output
actually observed. Nothing in this report is extrapolated from file names
or documentation.

----------------------------------------

## 1. SCORECARD

Rubric style mirrors replay/live_dhan_engine_readiness_test.py: score,
grade, concrete blocking issues, warnings.

### 1.1 Learning/execution brain (simulated) — 45/100 — WEAK

What was verified:
- Full paper lifecycle: `replay/full_paper_lifecycle_test.py` PASS
  (asserted cash transitions 99000 → 100006 → 100000).
- `replay/paper_trading_engine_test.py`, `paper_auto_close_test.py`,
  `paper_position_exit_test.py`, `live_paper_trading_monitor_test.py`
  all PASS. PaperTradingAccount logic (cash, positions, rejections) is
  real and correct.
- Code sweep of all 36 core ai/ modules confirmed **zero real broker
  order calls anywhere** — execution is paper-only, as required.

Blocking issues:
- `ai/execution_engine.py` fabricates fills, win/loss and PnL with
  `random`. The "brain" has never traded against even simulated
  order-book dynamics; its learning memory learns from noise.
- The Redis substrate (feature_engine → signal_ranker →
  execution_engine) could not be run at all in this environment (no
  Redis server, no Docker, no WSL — verified by connection error
  `Error 10061` and empty `where` lookups).
- `ai/inefficiency_detector.py` calls `EventBus.create_group(...)` /
  `read_ticks(...)`, which do not exist on the current EventBus — this
  module is broken at call time.

Warnings:
- Learning weights and regime thresholds are hand-set constants.
- 3 `.bak` variants of core brain files sit in ai/ (drift risk).

### 1.2 Live data pipeline reliability (Dhan connector + quote sync) — 55/100 — BLOCKED EXTERNALLY

What was verified:
- `replay/live_quote_synchronization_test.py` PASS (offline, asserting:
  freshness, sync, secret-leak checks).
- New `replay/dhan_connector_hardening_test.py` PASS — 10 assertions
  covering retry/backoff (observed sleeps [0.5, 1.0]), rate-limit retry,
  auth fail-fast (exactly 1 API call, no retry), retry exhaustion,
  request spacing, standard NEXT_BUILD.md shape, and a check that the
  connector exposes **no order-placement surface**.
- `replay/live_dhan_engine_readiness_test.py` executed **twice during
  open market hours** (before and after hardening): **10/100,
  NOT_READY** both times.

Blocking issues:
- **The Dhan access token in .env expired 2026-06-09** (JWT `exp`
  decoded locally; 35 days stale). Every live Dhan call returns
  `{'status':'failure', remarks: {error_code: None ...}}`. No live quote
  was retrievable this session. Only the user can regenerate this token.
- LiveQuoteBuffer/sync/freshness layers are well-tested offline but have
  no verified live soak time beyond earlier sessions' claims.

Warnings:
- Dhan's expired-token failure carries no error text, so the connector
  classifies it "unknown" and burns retries instead of failing fast.
- Quote sourcing is 1s REST polling, not a websocket stream.

### 1.3 Inefficiency/cost modeling correctness — 75/100 — WORKING, NOT CALIBRATED

What was verified (all new modules built this session, tests executed):
- `replay/settlement_engine_test.py` PASS — lock-up days, financing cost
  (100000 @ 12% × 7d = 230.14 verified), lock-up limits, negative
  settlement mismatch, input validation.
- `replay/capital_engine_test.py` PASS — return on capital, annualization
  (1% over 7d → 52.14% annualized verified), fast-small-spread >
  slow-big-spread ordering, funding checks, zero-lockup guard.
- `replay/liquidity_engine_test.py` PASS — participation caps (25% of
  1000 → 250 executable verified), linear slippage proxy, spread costs,
  score monotonicity, zero-liquidity handling.
- `replay/opportunity_ranking_engine_test.py` PASS — full four-engine
  composition; explicit rejection reasons
  (`not_profitable_after_round_trip_costs`, `insufficient_capital`,
  `liquidity_not_viable`, `settlement_not_viable`,
  `below_min_annualized_return`); priority tiers (arbitrage outranked a
  higher-return relative-value candidate, verified).
- Pre-existing `round_trip_cost_engine.py` covered via
  `round_trip_feasibility_test.py` PASS.

Blocking issues: none for correctness of the math itself.

Warnings:
- Cost inputs (brokerage, taxes, freight) are caller-supplied numbers;
  there is no Indian cost-schedule table (STT, GST, stamp duty rates)
  in the repo, so results are only as honest as the inputs.
- Liquidity slippage is a linear proxy, declared as such in-code, not a
  fitted impact model.
- The engines are built and tested but **not yet wired** into the live
  detection path (steel/gold adapters still use their own thresholds).

### 1.4 Real-market opportunity detection (lag pipeline) — 15/100 — UNVERIFIED LIVE

Real numbers from this session:
- Readiness test (open market, both runs): quote retrieval FAILED (token
  expired) → 0 live opportunities observed, 0 false positives measurable.
  **Precision on real data this session: no data — not zero, not good;
  simply unmeasured.**
- Dry-run fixture session (`live/run_live_paper_trading.py --dry-run`,
  134 fixture records, 9 ticks): 7 paper entries, 3 exits, final
  portfolio value 100015.0 on 100000 start (+15.0), 9 episodes closed
  (6 steel + 3 gold), all artifacts written to
  `storage/dryrun_session_20260714/`. This validates plumbing behavior,
  **not edge** — fixture prices are hand-authored.

Blocking issues:
- No live measurement possible (expired token).
- The live runner's DEFAULT_DHAN_INSTRUMENT_MAP maps commodity registry
  symbols to NSE ETFs as stand-ins (e.g. "BALTIC_DRY" → NIFTYBEES,
  "GOLD_GLOBAL" → NIFTYBEES, "COKING_COAL" → MOVALUE). Detections
  produced this way are **not commodity inefficiencies**; they are
  pattern math over unrelated equity ETFs. Several registry symbols even
  share one ETF, so "cross-market" gaps between them are artifacts.
- Readiness rubric defect: `lag_opportunity_pipeline_passed` is scored
  as warning-only but hard-gates the grade, so a quiet market can never
  grade above NOT_READY (replay/live_dhan_engine_readiness_test.py:150).

### 1.5 Test coverage and quality — 70/100 — GOOD BREADTH, MIXED DEPTH

Full offline suite executed this session — 29/29 PASS:

| Result | Tests |
|---|---|
| PASS (29) | settlement_engine, capital_engine, liquidity_engine, opportunity_ranking_engine, dhan_connector_hardening, crypto_connector, full_paper_lifecycle, paper_trading_engine, live_paper_trading_monitor, live_quote_synchronization, paper_entry_decision, paper_exit_decision, paper_position_exit, paper_auto_close, paper_trade_candidate, paper_trade_simulator, opportunity_validator, quote_freshness, round_trip_feasibility, steel_commodity_instrument_registry, steel_signal_graph, steel_pressure_calculator, steel_inefficiency_detector, steel_inefficiency_episode_tracker, steel_episode_dataset, commodity_episode_feature_builder, commodity_historical_replay, gold_commodity_stack, cross_metal_regime_engine |
| BLOCKED (9 live-only) | live_dhan_engine_readiness (ran: 10/100 NOT_READY), dhan_live_quote_synchronization, dhan_quote_opportunity, live_market_event, live_reaction_event, live_lag_detection, live_dhan_pair_selector, dhan_batch_quote, live_lag_opportunity — all need a valid Dhan token |

Warnings:
- ~10 of the older "tests" are print-only scripts with no assertions
  (they can't fail except by crashing).
- The live paper trading runner itself had **three fatal bugs** that no
  test caught (see 1.6) — there is no test that even imports it. That is
  the single largest coverage hole.
- No CI; tests run ad hoc with PYTHONPATH=. from repo root.

### 1.6 Overall system readiness for the next phase — 55/100 — FOUNDATION SOLID, INTEGRATION UNPROVEN

(Not a judgment about live capital — that is a separate human/regulatory
decision outside this report's scope.)

Fixed this session (each verified by re-running the failing command):
1. `live/run_live_paper_trading.py` crashed at init —
   `QuoteFreshnessValidator(max_age_seconds=...)` passed args to a
   no-arg constructor. **The live runner had never successfully
   started.** Fixed, verified end-to-end.
2. Same file: `pprint.pprint()` used without importing pprint — every
   completed run would have died in its `finally` block. Fixed.
3. Same file: called `steel_episode_writer.write(ep)` /
   `gold_episode_writer.write(ep)`; the writers only expose
   `write_episode`. Crashed the dry-run mid-session (observed), fixed,
   dry-run then completed cleanly.

Built and committed this session:
- inefficiency/settlement_engine.py (+test)
- inefficiency/capital_engine.py (+test)
- inefficiency/liquidity_engine.py (+test)
- inefficiency/opportunity_ranking_engine.py (+test)
- connectors/dhan_connector.py hardened: retries, exponential backoff,
  rate-limit spacing, structured logging, credential-safe errors,
  injectable client, `get_standard_quotes` (NEXT_BUILD.md shape) (+test)
- connectors/crypto_connector.py: read-only Crypto.com public-API
  connector in the standard shape, offline tests + live smoke test
  passed with real BTC/ETH quotes this session (+test)

Blocking issues for the next phase:
- Expired Dhan token (user action required).
- Phase 2 engines not yet consuming live connector output.
- No real commodity data source (see Section 2, Phase 4).

----------------------------------------

## 2. GAP ANALYSIS VS docs/PHASE_ROADMAP.md

### Phase 1 — Foundation Brain: PARTIAL
Evidence: learning_memory / position_sizer / exposure_manager /
portfolio_manager / opportunity object+adapter exist and are real logic
(full-file audit). Paper-trading chain passes 10+ asserting tests.
BUT: execution_engine.py simulates fills with `random`; the
Redis-dependent loop was unrunnable here (no Redis); risk controls exist
but are only exercised inside the simulated loop. "Stable, version
controlled, tested" is met for the paper layer, not for the brain loop.

### Phase 2 — Inefficiency Framework: COMPLETE (as modules), PARTIAL (as a system)
- Cost Engine: COMPLETE — pre-existing, tested.
- Settlement Engine: COMPLETE — built this session, 5-scenario test PASS.
- Capital Engine: COMPLETE — built this session, 8-scenario test PASS.
- Liquidity Engine: COMPLETE — built this session, 8-scenario test PASS.
- Opportunity Ranking: COMPLETE — built this session, 10-scenario test
  PASS, enforces north-star priority order.
- System-level gap: nothing feeds these engines real market pairs yet.

### Phase 3 — Market Connectors: PARTIAL
- NSE (via Dhan): code COMPLETE and hardened; live verification BLOCKED
  by expired token (readiness 10/100 during open market, twice).
- Crypto: COMPLETE and live-verified today (Crypto.com public API,
  real BTC_USDT/ETH_USDT quotes, spread-based liquidity score).
- MCX: NOT STARTED — no credentials/data access in this environment.
- LME: NOT STARTED — same reason.
- COMEX: NOT STARTED — same reason.
- Forex: NOT STARTED — no source chosen; deliberately not stubbed.

### Phase 4 — Cross-Market Arbitrage: PARTIAL (logic), NOT STARTED (data)
Honest split:
- Logic built and tested: steel/gold signal graphs, pressure
  calculators, inefficiency detectors, episode trackers, leakage-safe
  feature datasets, cross-metal regime engine — 10 asserting offline
  suites PASS, deterministic replay verified by run-hash test.
- Data source is NOT real: MockSteelConnector is `random.randint`;
  the live runner substitutes NSE ETFs for steel/gold/freight symbols;
  signal-graph weights are hand-picked and self-labelled
  `is_historically_calibrated: False`. **No steel, gold, or freight
  market price has ever entered this system.** Phase 4 claims cannot be
  trusted until at least one real commodity feed exists.

### Phase 5 — Delivery Fallback: NOT STARTED
No inventory/procurement/delivery modules exist anywhere in the repo.
Left as backlog deliberately (Phases 2–3 gaps take priority).

### Phase 6 — GPU Optimization: NOT STARTED
No simulation/Monte-Carlo code exists. The replay test suite actively
asserts GPU/ollama imports are banned in ai/ (cross_metal test PASS).

### Phase 7 — Commercial Platform: NOT STARTED
live_dashboard.py is a terminal printer over Redis keys; no reporting,
alerting, or historical database beyond JSONL files.

----------------------------------------

## 3. PRIORITIZED IMPROVEMENT LIST

Ranked by (north-star impact, effort, risk-if-skipped):

1. **Regenerate the Dhan access token and re-run the readiness test
   during market hours.** (User action, minutes.) Everything live is
   dark until this. Risk if skipped: the entire NSE pipeline stays
   unverifiable and quietly rots.
2. **Wire the Phase 2 engines into the live path.** The opportunity
   ranking engine exists but nothing constructs candidates from real
   quotes. Replace the live runner's ad-hoc entry gating
   (fixed `quantity=1`, forced `BUY_ALLOWED` at
   live/run_live_paper_trading.py:494) with
   OpportunityRankingEngine.evaluate() so every entry/block carries
   engine-grade rejection reasons. Medium effort. Risk: two parallel
   notions of "opportunity" drift apart.
3. **Add a real commodity data source or stop labelling Phase 4 outputs
   as commodity detection.** Cheapest honest options: MCX market data
   subscription via Dhan (steel/gold futures), or an LME/COMEX delayed
   feed. Until then, rename outputs "ETF-proxy detection" in the live
   runner. Low effort for honesty fix, high effort for real feed. Risk:
   stakeholders read steel/gold PnL that has nothing to do with steel.
4. **Put the live runner under test.** It had three fatal bugs no test
   caught because no test imports it. A smoke test that constructs
   LivePaperTradingRunner with a stub connector and runs 3 ticks would
   have caught all three. Low effort. Risk: every future refactor
   re-breaks the only integration entry point.
5. **Replace random-fill execution_engine.py with cost-engine-based
   simulated fills** (use liquidity engine slippage + round-trip costs
   against the paper account). Medium effort. Risk: learning memory
   keeps training on noise.
6. **Build an Indian cost schedule table** (STT, stamp duty, GST,
   exchange charges by instrument type) so cost-engine inputs stop being
   guesses. Low-medium effort. Risk: "profitable after costs" claims are
   fiction without it.
7. **Fix the readiness-test rubric** so lag-pipeline absence in a quiet
   market doesn't force NOT_READY (it currently hard-gates the grade
   while being described as a warning). Low effort.
8. **Repo hygiene:** delete ai/*.bak*, fix or retire the stale
   ai/inefficiency_detector.py (broken EventBus API), decide the fate of
   the duplicate root-level market_terminal.zip and recovery_backup/.
   Low effort, prevents confusion.

----------------------------------------

## 4. WHAT COULD NOT BE VERIFIED OR COMPLETED THIS SESSION, AND WHY

- **Live Dhan data, end to end.** The .env access token expired
  2026-06-09 (decoded locally from the JWT; not printed anywhere).
  Both readiness runs and the live paper session attempt failed at
  quote retrieval with Dhan `status: failure`. Market WAS open during
  the entire test window (Tuesday 13:00–14:00 IST) — the blocker is
  purely the credential, which only the account holder can regenerate.
- **A real live paper-trading session.** Attempted
  (`live/run_live_paper_trading.py --duration 30`): initialized, polled,
  received only auth failures, closed cleanly with zero trades. The
  dry-run fixture session (7 entries / 3 exits / +15.0 on 100000) is
  plumbing validation only — it says nothing about real-market edge.
- **The Redis brain (feature_engine, signal_ranker, execution_engine,
  tick_simulator).** No Redis server, Docker, or WSL exists on this
  machine (verified). These modules were not modified this session, and
  were not run.
- **MCX / LME / COMEX / Forex connectors.** No credentials or data
  access from this environment. Deliberately not stubbed — a
  fake connector that looks real is worse than an honest gap.
- **Steel/gold detection against real commodity prices.** No such data
  source exists in the repo or this environment; all commodity-stack
  validation used fixtures, mocks, or ETF proxies.
- **Long-horizon soak stability** (multi-hour quote polling, reconnect
  behavior under real network flap): requires a valid token and a full
  market session.

----------------------------------------

## Session command log (traceability)

All test outputs referenced above were produced by these commands, run
from repo root with `PYTHONPATH=.`:

- `python replay/live_dhan_engine_readiness_test.py` (twice; 10/100 both)
- `python replay/<each>_test.py` for the 29 offline tests (29 PASS)
- `CRYPTO_CONNECTOR_LIVE_TEST=1 python replay/crypto_connector_test.py`
  (live BTC/ETH quotes received)
- `python live/run_live_paper_trading.py --duration 30 --output-dir
  storage/live_session_20260714` (auth failures, clean shutdown, 0 trades)
- `python live/run_live_paper_trading.py --dry-run --output-dir
  storage/dryrun_session_20260714` (7 entries, 3 exits, +15.0 final PnL)
- Token expiry check: local JWT payload decode of DHAN_ACCESS_TOKEN
  (exp=1780987692 → 2026-06-09T06:48:12Z)

Commits made this session (imperative style, matching repo history):
`Add live paper trading runner and live quote adapters` (pre-existing
work committed as baseline), `Fix missing pprint import in live runner`,
`Add settlement engine`, `Add capital engine`, `Add liquidity engine`,
`Add opportunity ranking engine`, `Harden Dhan connector with retries,
backoff and standard quote shape`, `Add read-only crypto connector with
standard quote shape`, `Fix live runner init and episode writer API
calls`, plus this report and the PROJECT_INVENTORY.md status refresh.
