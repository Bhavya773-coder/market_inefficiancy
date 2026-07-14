# PROJECT INVENTORY

Status Legend

- COMPLETE
- WORKING
- PARTIAL
- PLANNED

----------------------------------------

CORE BRAIN

[WORKING] Learning Memory
[WORKING] Signal Ranker
[WORKING] Execution Engine
[WORKING] Position Sizer
[WORKING] Exposure Manager
[WORKING] Portfolio Manager
[WORKING] Trade Logger
[WORKING] Regime Engine

----------------------------------------

OPPORTUNITY FRAMEWORK

[WORKING] Opportunity Object
[WORKING] Opportunity Adapter

----------------------------------------

INEFFICIENCY ENGINE

[PARTIAL] Cross Market Board (static example markets)
[WORKING] Cost Engine (inefficiency/round_trip_cost_engine.py)
[WORKING] Settlement Engine (inefficiency/settlement_engine.py)
[WORKING] Capital Engine (inefficiency/capital_engine.py)
[WORKING] Liquidity Engine (inefficiency/liquidity_engine.py)
[WORKING] Opportunity Ranking (inefficiency/opportunity_ranking_engine.py)

----------------------------------------

MARKET CONNECTORS

[WORKING] Dhan/NSE Connector (connectors/dhan_connector.py — hardened:
          retries, backoff, rate-limit spacing, logging, standard
          NEXT_BUILD.md quote shape; live-verified only up to auth,
          current .env token expired 2026-06-09)
[WORKING] Crypto Connector (connectors/crypto_connector.py —
          Crypto.com public API, live-verified 2026-07-14, read-only)
[PARTIAL] Mock Steel Connector (random synthetic prices — dev only)

----------------------------------------

REPORTING

[WORKING] Strategy Report
[WORKING] Opportunity Report
[WORKING] Replay Reports

----------------------------------------

PLANNED

[ ] MCX Connector (no data access yet)
[ ] LME Connector (no data access yet)
[ ] COMEX Connector (no data access yet)
[ ] Forex Connector (no data access yet)

[ ] Inventory Engine
[ ] Delivery Engine

[ ] Dashboard
[ ] Historical Database
[ ] Alert Engine

----------------------------------------

AI FOLDER AUDIT

CORE SYSTEM

[WORKING] ai/event_bus.py
[WORKING] ai/feature_engine.py
[WORKING] ai/signal_ranker.py
[WORKING] ai/execution_engine.py
[WORKING] ai/trade_state_manager.py
[WORKING] ai/trade_logger.py
[WORKING] ai/live_dashboard.py

LEARNING / INTELLIGENCE

[WORKING] ai/learning_memory.py
[WORKING] ai/regime_engine.py
[WORKING] ai/regime_confidence_engine.py
[WORKING] ai/strategy_engine.py
[WORKING] ai/memory_report.py

RISK / PORTFOLIO

[WORKING] ai/portfolio_manager.py
[WORKING] ai/position_manager.py
[WORKING] ai/position_sizer.py
[WORKING] ai/exposure_manager.py
[WORKING] ai/loss_streak_guard.py
[WORKING] ai/equity_memory.py

OPPORTUNITY FRAMEWORK

[WORKING] ai/opportunity.py
[WORKING] ai/opportunity_adapter.py

EXPERIMENTAL / REVIEW LATER

[REVIEW] ai/adaptive_engine.py
[REVIEW] ai/consumer_test.py
[REVIEW] ai/inefficiency_detector.py
[REVIEW] ai/strategy_learner.py
[REVIEW] ai/strategy_scorer.py
[REVIEW] ai/strategy_selector.py
[REVIEW] ai/trade_memory.py

IGNORED

[IGNORE] ai/__pycache__/
[IGNORE] ai/*.bak
[IGNORE] ai/*.bak2

----------------------------------------

INEFFICIENCY FOLDER AUDIT

[WORKING] inefficiency_engine.py
[WORKING] round_trip_cost_engine.py
[WORKING] market_universe.py
[WORKING] inefficiency_opportunity_adapter.py

STATUS

Current Capability:

Cross-market spread calculation

Current Limitation:

Uses example/mock markets

Future Target:

Real-world market connectors
and executable arbitrage opportunities

[IGNORE] inefficiency/__pycache__/

PROJECT STATUS

Trading Brain: ~80% (execution/PnL still simulated with random fills)

Inefficiency Platform: ~55% (all five Phase 2 engines built and tested;
not yet fed by real cross-market data)

Steel Arbitrage Platform: ~20% (detection logic real and tested; data
sources are NSE-ETF proxies and mock prices, not steel markets)

Current Focus:
Real cross-market data sources and wiring Phase 2 engines into live
detection. See PROJECT_HEALTH_REPORT.md for the full audit.