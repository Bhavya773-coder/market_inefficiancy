"""
Live crypto paper-trading runner.

Pipeline per poll tick, all real components, no mock data:

    CryptoConnector (Crypto.com public API, real quotes)
      -> PriceChangeDetector -> ReactionEvent -> LagDetector
      -> OpportunityAdapter -> OpportunityValidator
      -> LiveOpportunityGate (cost + settlement + capital + liquidity
         via OpportunityRankingEngine — the deciding verdict)
      -> PaperTradingEngine (paper entries/exits ONLY — never real orders)

Every quote, detection, blocked opportunity and paper trade is written to
JSONL under --output-dir. Ctrl+C or --duration ends the run cleanly with
a final portfolio report.
"""
import argparse
import json
import pathlib
import pprint
import time
import traceback
from datetime import datetime, timezone

from connectors.crypto_connector import CryptoConnector, CryptoConnectorError
from ai.market_event import MarketEvent
from ai.price_change_detector import PriceChangeDetector
from ai.reaction_event import ReactionEvent
from ai.lag_detector import LagDetector
from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
from ai.paper_trading_engine import PaperTradingEngine
from ai.paper_trade_simulator import PaperTradeSimulator
from ai.paper_trading_account import PaperTradingAccount
from ai.live_opportunity_gate import LiveOpportunityGate
from ai.kronos_forecast import direction as kronos_direction

DEFAULT_INSTRUMENTS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "LTC_USDT"]

# Crypto trades settle instantly on-venue and carry no exchange financing
# leg in this paper model; costs are taker-fee-like percentages.
CRYPTO_GATE_CONFIG = {
    "desired_quantity": 1,
    "buy_settlement_days": 0,
    "sell_settlement_days": 0,
    "holding_period_days": 0.0,
    "annual_financing_rate_pct": 0.0,
    "buy_brokerage_pct": 0.05,   # ~taker fee per leg
    "sell_brokerage_pct": 0.05,
    "buy_tax_pct": 0.0,
    "sell_tax_pct": 0.0,
    "latency_buffer_pct": 0.02,
    "min_annualized_return_pct": 5.0,
    "min_fill_ratio": 0.5
}


class CryptoPaperTradingRunner:
    def __init__(self, args, connector=None):
        self.args = args
        self.run_id = f"crypto_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self.instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
        if len(self.instruments) < 2:
            raise ValueError("need at least 2 instruments for lag detection")

        # max_retries=1: the poll loop itself repeats every few seconds, so
        # long in-call retry chains only starve the cadence (observed
        # 2026-07-14: 4-attempt chains x 5 instruments wedged the session).
        self.connector = connector if connector is not None else CryptoConnector(max_retries=1)
        self.consecutive_poll_failures = 0

        self.change_detector = PriceChangeDetector()
        self.lag_detector = LagDetector()
        self.opportunity_adapter = OpportunityAdapter()
        self.opportunity_validator = OpportunityValidator()
        self.candidate_factory = PaperTradeCandidateFactory()
        self.opportunity_gate = LiveOpportunityGate(config=CRYPTO_GATE_CONFIG)
        self.paper_engine = PaperTradingEngine(
            simulator=PaperTradeSimulator(
                account=PaperTradingAccount(starting_cash=args.starting_cash)
            )
        )

        self.kronos_mode = getattr(args, "kronos_filter", "off")

        self.previous_events = {}
        self.latest_quotes = {}

        self.output_dir = pathlib.Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.quote_log = open(self.output_dir / "quotes.jsonl", "a", encoding="utf-8")
        self.detection_log = open(self.output_dir / "detections.jsonl", "a", encoding="utf-8")
        self.trade_log = open(self.output_dir / "paper_trades.jsonl", "a", encoding="utf-8")

        self.stats = {
            "ticks": 0,
            "quotes_received": 0,
            "poll_errors": 0,
            "lag_signals": 0,
            "entries": 0,
            "exits": 0,
            "blocked": 0
        }

    # ------------------------------------------------------------------

    @staticmethod
    def _to_internal_quote(std_quote):
        """
        Converts a standard-shape connector quote
        (source/asset/bid/ask/last_price/currency/timestamp/liquidity_score)
        into the internal quote dict the pipeline components expect.
        """
        return {
            "exchange": "CRYPTO_COM",
            "security_id": std_quote["asset"],
            "symbol": std_quote["asset"],
            "last_price": std_quote["last_price"],
            "bid": std_quote.get("bid"),
            "ask": std_quote.get("ask"),
            "timestamp": std_quote.get("timestamp"),
            "currency": std_quote.get("currency"),
            "liquidity_score": std_quote.get("liquidity_score"),
            "data_source": "crypto_com_live"
        }

    def _log(self, handle, payload):
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
        handle.flush()

    # ------------------------------------------------------------------

    def poll_quotes(self):
        """One poll of all instruments. Returns dict symbol -> MarketEvent."""
        observed_at = datetime.now(timezone.utc)
        try:
            result = self.connector.get_standard_quotes(self.instruments)
            self.consecutive_poll_failures = 0
        except (CryptoConnectorError, ValueError) as e:
            self.stats["poll_errors"] += 1
            self.consecutive_poll_failures += 1
            self._log(self.detection_log, {
                "timestamp": observed_at.isoformat(),
                "type": "poll_error",
                "consecutive": self.consecutive_poll_failures,
                "error": str(e)[:300]
            })
            # Recovery: after 3 consecutive failed polls, drop the pooled
            # HTTP session so the next poll starts on fresh connections.
            if (
                self.consecutive_poll_failures % 3 == 0
                and hasattr(self.connector, "reset_session")
            ):
                self.connector.reset_session()
                self._log(self.detection_log, {
                    "timestamp": observed_at.isoformat(),
                    "type": "session_reset",
                    "after_consecutive_failures": self.consecutive_poll_failures
                })
            return {}

        events = {}
        for std_quote in result["quotes"]:
            quote = self._to_internal_quote(std_quote)
            self.latest_quotes[quote["symbol"]] = quote
            events[quote["symbol"]] = MarketEvent.from_quote(quote)
            self.stats["quotes_received"] += 1

        self._log(self.quote_log, {
            "timestamp": observed_at.isoformat(),
            "quotes": {s: {
                "last_price": q["last_price"], "bid": q["bid"], "ask": q["ask"],
                "timestamp": q["timestamp"],
                # data_source is what the dashboard's REAL/SIMULATED honesty
                # tagging reads — never drop it from the log.
                "data_source": q["data_source"]
            } for s, q in self.latest_quotes.items()},
            "errors": result.get("errors", [])
        })
        return events

    def detect_and_trade(self, events, observed_at):
        """Lag detection across all ordered pairs, gated paper entries."""
        reactions = {}
        for symbol, event in events.items():
            prev = self.previous_events.get(symbol)
            change = self.change_detector.detect(event, prev) if prev else None
            if change:
                reactions[symbol] = ReactionEvent.from_price_change(change)

        for ref_symbol, ref_reaction in reactions.items():
            for tgt_symbol, tgt_reaction in reactions.items():
                if ref_symbol == tgt_symbol:
                    continue

                lag_result = self.lag_detector.detect(
                    ref_reaction, tgt_reaction,
                    min_gap_percent=self.args.min_gap_percent
                )
                if not lag_result or not lag_result.get("is_lagging"):
                    continue

                self.stats["lag_signals"] += 1
                lag_result["mock"] = False
                lag_result["data_source"] = "crypto_com_live"
                self._log(self.detection_log, {
                    "timestamp": observed_at.isoformat(),
                    "type": "lag_signal",
                    "lag_result": lag_result
                })

                # Skip if we already hold this asset (no pyramiding)
                if tgt_symbol in self.paper_engine.account_state()["positions"]:
                    continue

                opportunity = self.opportunity_adapter.from_lag_result(lag_result)
                if opportunity is None:
                    continue
                val_res = self.opportunity_validator.validate(opportunity)
                if not val_res.get("is_valid"):
                    continue
                candidate = self.candidate_factory.from_validated_opportunity(val_res)
                if candidate is None:
                    continue

                quote = self.latest_quotes.get(tgt_symbol)
                # Adapt the lag result into the gate's detection shape: the
                # unpriced edge is the reaction gap the target hasn't closed.
                target_result = {
                    "target": tgt_symbol,
                    "status": "REACTION_LAG",
                    "is_inefficient": True,
                    "residual_gap": lag_result["reaction_gap"],
                    "absolute_gap": lag_result["reaction_gap"]
                }
                gate_result = self.opportunity_gate.evaluate_target(
                    tgt_symbol, target_result, "KEEP_SIGNAL", quote,
                    available_capital=self.paper_engine.account_state()["cash"]
                )

                price = quote["last_price"]
                # Kronos second opinion, only for candidates the cost gate
                # already cleared (forecasting is ~3-4s; never spend it on a
                # signal that was going to be rejected anyway).
                allowed = gate_result["allowed"]
                kronos = None
                if self.kronos_mode != "off" and allowed:
                    kronos = kronos_direction(self.connector, tgt_symbol,
                                              device=self.args.kronos_device)
                    if (self.kronos_mode == "on" and kronos is not None
                            and not kronos["up"]):
                        allowed = False
                        gate_result["rejection_reasons"] = ["kronos_forecast_disagrees"]

                if allowed:
                    entry_report = self.paper_engine.process_gated_candidate(
                        candidate, gate_result, price
                    )
                    exec_data = entry_report.get("execution")
                    if exec_data and exec_data.get("status") == "filled":
                        self.stats["entries"] += 1
                        self._log(self.trade_log, {
                            "timestamp": observed_at.isoformat(),
                            "type": "entry",
                            "symbol": tgt_symbol,
                            "price": price,
                            "quantity": gate_result["quantity"],
                            "lag_reference": ref_symbol,
                            "gate_evaluation": {
                                "annualized_return_pct": gate_result["evaluation"]["annualized_return_pct"],
                                "net_profit_pct": gate_result["evaluation"]["net_profit_pct"],
                                "liquidity_score": gate_result["evaluation"]["liquidity_score"],
                                "rank_score": gate_result["evaluation"]["rank_score"]
                            },
                            "kronos": kronos,
                            "execution": exec_data,
                            "account": self.paper_engine.account_state()
                        })
                else:
                    self.stats["blocked"] += 1
                    self._log(self.trade_log, {
                        "timestamp": observed_at.isoformat(),
                        "type": "blocked",
                        "symbol": tgt_symbol,
                        "price": price,
                        "lag_reference": ref_symbol,
                        "rejection_reasons": gate_result["rejection_reasons"],
                        "kronos": kronos
                    })

        self.previous_events.update(events)

    def manage_exits(self, observed_at):
        positions = list(self.paper_engine.account_state()["positions"].keys())
        for symbol in positions:
            quote = self.latest_quotes.get(symbol)
            if not quote:
                continue
            exit_report = self.paper_engine.process_price_update(
                symbol, quote["last_price"],
                target_profit_pct=self.args.take_profit_pct,
                stop_loss_pct=self.args.stop_loss_pct
            )
            exec_data = exit_report.get("execution")
            if exec_data and exec_data.get("status") == "filled":
                self.stats["exits"] += 1
                self._log(self.trade_log, {
                    "timestamp": observed_at.isoformat(),
                    "type": "exit",
                    "symbol": symbol,
                    "price": quote["last_price"],
                    "decision": exit_report.get("decision"),
                    "execution": exec_data,
                    "account": self.paper_engine.account_state()
                })

    # ------------------------------------------------------------------

    def run(self):
        print(f"=== LIVE CRYPTO PAPER TRADING RUNNER (run_id={self.run_id}) ===")
        print(f"Instruments: {self.instruments}")
        print(f"Duration: {self.args.duration}s | Poll interval: {self.args.poll_interval}s")
        print("Execution: PAPER ONLY (PaperTradingAccount). No real orders exist in this codebase.")

        start = time.perf_counter()
        try:
            while (time.perf_counter() - start) < self.args.duration:
                tick_started = time.perf_counter()
                self.stats["ticks"] += 1
                observed_at = datetime.now(timezone.utc)

                events = self.poll_quotes()
                if events:
                    self.detect_and_trade(events, observed_at)
                    self.manage_exits(observed_at)

                if self.stats["ticks"] % 20 == 0:
                    state = self.paper_engine.account_state()
                    latest_prices = {s: q["last_price"] for s, q in self.latest_quotes.items()}
                    print(f"[tick {self.stats['ticks']}] quotes={self.stats['quotes_received']} "
                          f"lags={self.stats['lag_signals']} entries={self.stats['entries']} "
                          f"exits={self.stats['exits']} blocked={self.stats['blocked']} "
                          f"errors={self.stats['poll_errors']} cash={state['cash']:.2f}")

                elapsed = time.perf_counter() - tick_started
                remaining = self.args.poll_interval - elapsed
                if remaining > 0:
                    time.sleep(remaining)
        except KeyboardInterrupt:
            print("\nCtrl+C — shutting down cleanly...")
        except Exception as e:
            print(f"CRITICAL RUNTIME ERROR: {e}")
            traceback.print_exc()
        finally:
            self.report_final()
            self.close()

    def report_final(self):
        state = self.paper_engine.account_state()
        latest_prices = {s: q["last_price"] for s, q in self.latest_quotes.items()}
        mtm = self.paper_engine.simulator.account.portfolio_value(latest_prices)
        print("\n=== FINAL CRYPTO PAPER SESSION REPORT ===")
        print(f"run_id: {self.run_id}")
        pprint.pprint(self.stats)
        print(f"cash: {state['cash']:.2f}")
        print(f"open positions: {state['positions']}")
        print(f"mark-to-market portfolio value: {mtm:.2f}")
        print(f"PnL vs {self.args.starting_cash:.2f} start: {mtm - self.args.starting_cash:+.2f}")
        print("=========================================")
        self._log(self.trade_log, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "session_summary",
            "run_id": self.run_id,
            "stats": self.stats,
            "final_cash": state["cash"],
            "open_positions": state["positions"],
            "mark_to_market_value": mtm,
            "pnl": mtm - self.args.starting_cash
        })

    def close(self):
        for handle in (self.quote_log, self.detection_log, self.trade_log):
            try:
                handle.close()
            except Exception:
                pass
        print("Logs flushed and closed.")


def main():
    parser = argparse.ArgumentParser(description="Live crypto paper trading (paper execution only)")
    parser.add_argument("--duration", type=int, default=1800, help="Run duration in seconds")
    parser.add_argument("--poll-interval", type=float, default=3.0, help="Seconds between polls")
    parser.add_argument("--instruments", type=str, default=",".join(DEFAULT_INSTRUMENTS))
    parser.add_argument("--output-dir", type=str, default="storage/crypto_live/")
    parser.add_argument("--starting-cash", type=float, default=1000000.0)
    parser.add_argument("--min-gap-percent", type=float, default=0.05,
                        help="Minimum reaction gap (%%) for a lag signal")
    parser.add_argument("--take-profit-pct", type=float, default=0.5)
    parser.add_argument("--stop-loss-pct", type=float, default=0.25)
    parser.add_argument("--kronos-filter", choices=["off", "shadow", "on"], default="off",
                        help="off: unchanged behaviour. shadow: log what Kronos "
                             "would have said without changing decisions. "
                             "on: also skip entries Kronos disagrees with.")
    parser.add_argument("--kronos-device", default="cpu")
    args = parser.parse_args()

    CryptoPaperTradingRunner(args).run()


if __name__ == "__main__":
    main()
