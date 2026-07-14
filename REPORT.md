# REPORT — Session Changes & Project Capabilities

Date: 2026-07-14
Branch: `feature/live-paper-trading`
Companion document: [PROJECT_HEALTH_REPORT.md](PROJECT_HEALTH_REPORT.md) (full audit, scorecard, gap analysis)

---

## PART 1 — CHANGES MADE THIS SESSION

### 1. New Phase 2 engines (Inefficiency Framework — now complete as modules)

All four missing engines from the Phase 2 roadmap were built in the same
style as the existing `round_trip_cost_engine.py`: explicit inputs,
explicit dict outputs, no hidden state. Each has its own asserting test
in `replay/`, and every test was executed and passed.

| Module | What it does | Test |
|---|---|---|
| `inefficiency/settlement_engine.py` | Computes capital lock-up days, settlement mismatch between buy/sell legs, and the financing cost of the lock-up window. Enforces a maximum acceptable lock-up. | `replay/settlement_engine_test.py` |
| `inefficiency/capital_engine.py` | Converts net profit into return-on-capital and annualized return, so a fast small spread can be compared fairly against a slow large one. Checks fundability against available capital and a minimum-return threshold. | `replay/capital_engine_test.py` |
| `inefficiency/liquidity_engine.py` | Caps executable quantity by market depth and participation limits, estimates slippage (linear proxy, declared as such), prices in bid/ask spreads, and produces a bounded 0–1 liquidity score. | `replay/liquidity_engine_test.py` |
| `inefficiency/opportunity_ranking_engine.py` | Runs every candidate through all four engines (cost, settlement, capital, liquidity) and returns one ranked list. Enforces the north-star priority order (Arbitrage > Relative Value > Delivery Fallback > Inventory Optimization). Rejected candidates are returned separately with explicit reasons, never silently dropped. | `replay/opportunity_ranking_engine_test.py` |

### 2. Hardened Dhan/NSE connector

`connectors/dhan_connector.py` was rewritten (public method signatures
and return shapes preserved):

- Retries transient failures with exponential backoff.
- Authentication failures fail fast (no pointless retries) with a clear error.
- Minimum spacing between requests to respect Dhan rate limits.
- Structured `logging` instead of prints; error text never leaks credentials.
- New `get_standard_quotes()` returning the project-standard shape from
  `docs/NEXT_BUILD.md`: `source / asset / bid / ask / last_price /
  currency / timestamp / liquidity_score`.
- Injectable client so it can be tested offline (`replay/dhan_connector_hardening_test.py`, 10 scenarios, all passing).
- Explicitly read-only: the test suite asserts the connector exposes no
  order-placement surface.

### 3. New crypto connector (first non-Dhan real data source)

`connectors/crypto_connector.py` — read-only connector for the
Crypto.com Exchange **public** API (no credentials needed). Returns the
same standard quote shape. Verified live during this session with real
BTC_USDT and ETH_USDT quotes. Offline test suite plus an optional live
smoke test in `replay/crypto_connector_test.py`.

MCX / LME / COMEX / Forex connectors were deliberately **not** built —
no data access exists from this environment, and a fake connector that
looks real is worse than an honest gap.

### 4. Three fatal bugs fixed in the live paper-trading runner

`live/run_live_paper_trading.py` had never successfully completed a run:

1. **Crash at startup** — passed constructor arguments to
   `QuoteFreshnessValidator`, which takes none.
2. **Crash at shutdown** — used `pprint.pprint()` without importing `pprint`.
3. **Crash mid-session** — called `.write()` on episode dataset writers
   whose real method is `.write_episode()`.

After the fixes the dry-run session completed end-to-end (7 paper
entries, 3 exits, 9 episodes written, clean shutdown), and the live mode
starts, polls, handles API failures gracefully, and reports a final
portfolio.

### 5. Documentation and verification

- `PROJECT_HEALTH_REPORT.md` — full honest audit: scorecard per
  subsystem, phase-by-phase gap analysis, prioritized improvement list,
  and an explicit list of what could not be verified and why.
- `docs/PROJECT_INVENTORY.md` — status tags refreshed to match reality.
- Full offline test suite executed: **29/29 passing** (23 pre-existing + 6 new).
- Live readiness test executed twice during open market hours: 10/100,
  NOT_READY — blocked solely by the **expired Dhan token** (expired
  2026-06-09; only the account holder can regenerate it).

---

## PART 2 — WHAT THIS PROJECT CAN DO (CAPABILITIES)

### Market data ingestion
- **Live NSE equity/ETF quotes** through the hardened Dhan connector —
  single and batch quotes, retry/backoff, rate-limit respect. (Needs a
  valid Dhan token in `.env`.)
- **Live crypto quotes** (bid/ask/last, spread-based liquidity score)
  from Crypto.com's public API with no credentials at all.
- **A standard connector interface** so the inefficiency engine can
  consume any market without knowing where the data came from.
- **Quote quality control**: a hardened live quote buffer with
  freshness validation, staleness limits, pair-synchronization
  monitoring, and activity detection — quotes that are stale or
  unsynchronized are blocked before any decision is made.

### Inefficiency economics (the core of the project)
- **Round-trip cost modeling**: brokerage, taxes, GST, stamp duty, FX
  spread, slippage, funding, freight, warehousing, handling, hedging —
  answers "is this spread still profitable after everything?"
- **Settlement modeling**: how long capital is locked, what that costs
  in financing, and whether the two legs create a funding gap.
- **Capital efficiency**: annualized return per rupee committed, so
  opportunities of different sizes and speeds are comparable.
- **Liquidity reality-check**: how much can actually be executed at
  what slippage, given market depth.
- **Opportunity ranking**: one ranked, fully-explained list across all
  candidates, ordered by the north-star priority (arbitrage first),
  with every rejected candidate carrying its explicit rejection reason.

### Detection intelligence
- **Steel and gold inefficiency detection stacks**: driver→target
  signal graphs, pressure calculators, divergence/under-reaction/
  over-reaction classification, and episode trackers that follow each
  detected inefficiency from open to convergence/expiry.
- **Cross-metal regime engine**: classifies the joint gold/steel state
  (e.g. GOLD_STRONG_STEEL_WEAK) and contextually keeps, deprioritizes,
  or rejects signals accordingly.
- **Lag detection pipeline**: detects when one instrument reacts and a
  related one hasn't yet, then converts that into a validated,
  feasibility-checked paper-trade candidate.
- Every detector output is honestly self-labelled
  `is_historically_calibrated: False` — weights are heuristic, not fitted.

### Paper trading (execution simulation — no real orders, by design)
- **PaperTradingAccount**: simulated cash, positions, average-price
  tracking, trade log, portfolio valuation. There is no real
  order-placement code anywhere in the repository (verified by audit).
- **Full lifecycle engine**: candidate → feasibility → entry decision →
  position → take-profit/stop-loss evaluation → exit decision →
  auto-close, with every step logged.
- **Live paper-trading runner**: polls real quotes, runs the full
  detection pipeline each tick, trades on paper, writes every quote,
  detection, episode, feature row, and trade to JSONL datasets, and
  respects NSE market hours and holidays.

### Research & learning infrastructure
- **Deterministic historical replay**: point-in-time, leakage-safe
  replay of steel/gold datasets — same input always produces the same
  run hash (asserted by test).
- **Leakage-safe ML feature datasets**: features built only from each
  episode's first observation, with a built-in audit that bans
  future-derived fields; append-only, deduplicated, fsync'd JSONL
  storage with strict schema validation on read.
- **Redis-based learning brain** (runs where Redis exists): event bus,
  feature engine, signal ranker with per-symbol/strategy/regime memory
  bias, position sizing, exposure caps, loss-streak guard, equity/
  drawdown tracking, and a terminal dashboard.
- **Offline test suite**: 29 self-contained test scripts runnable with
  nothing but Python — no credentials, no network, no Redis.

### What it can NOT do yet (honest limits)
- No real steel/gold/freight market data — the commodity stack currently
  runs on fixtures, mocks, or NSE-ETF proxies.
- No MCX/LME/COMEX/Forex connectivity.
- The learning brain's fills/PnL are random simulations, not
  market-realistic; and Phase 2 engines are not yet wired into the live
  detection path.
- Live NSE verification is blocked until the Dhan token is regenerated.
- It will never place real orders — paper execution only, proprietary
  capital only. That is a design constraint, not a gap.
