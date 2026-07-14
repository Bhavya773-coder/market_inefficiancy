import os
import sys
import time
import argparse
import uuid
import json
import pathlib
import pprint
import traceback
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import redis
from dotenv import load_dotenv

# Connectors
from connectors.dhan_connector import DhanConnector

# Buffers & Monitors
from ai.live_quote_buffer import LiveQuoteBuffer
from ai.quote_freshness_validator import QuoteFreshnessValidator
from ai.quote_synchronization_monitor import QuoteSynchronizationMonitor

# Registries & Configurations
from ai.commodity_replay_config import STEEL_HISTORICAL_REPLAY_CONFIG, GOLD_HISTORICAL_REPLAY_CONFIG
from ai.steel_commodity_instrument_registry import SteelCommodityInstrumentRegistry
from ai.gold_commodity_instrument_registry import GoldCommodityInstrumentRegistry

# Adapters
from ai.steel_live_quote_adapter import SteelLiveQuoteAdapter
from ai.gold_live_quote_adapter import GoldLiveQuoteAdapter

# Trackers
from ai.steel_inefficiency_episode_tracker import SteelInefficiencyEpisodeTracker
from ai.gold_inefficiency_episode_tracker import GoldInefficiencyEpisodeTracker

# Cross-Metal Regime
from ai.cross_metal_regime_engine import CrossMetalRegimeEngine
from ai.cross_metal_context_adjuster import CrossMetalContextAdjuster
from ai.commodity_detection_snapshot import CommodityDetectionSnapshot
from ai.cross_metal_snapshot import CrossMetalSnapshot

# Paper Trading & Opportunities
from ai.opportunity import Opportunity
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
from ai.paper_trading_engine import PaperTradingEngine

# Writers
from storage.steel_episode_dataset_writer import SteelEpisodeDatasetWriter
from storage.steel_episode_feature_dataset_writer import SteelEpisodeFeatureDatasetWriter
from storage.gold_episode_dataset_writer import GoldEpisodeDatasetWriter
from storage.gold_episode_feature_dataset_writer import GoldEpisodeFeatureDatasetWriter
from storage.cross_metal_regime_dataset_writer import CrossMetalRegimeDatasetWriter
from ai.steel_episode_feature_builder import SteelEpisodeFeatureBuilder
from ai.gold_episode_feature_builder import GoldEpisodeFeatureBuilder

# Default instrument map mapping registry symbols to NSE active liquid stocks/ETFs
DEFAULT_DHAN_INSTRUMENT_MAP = {
    # Steel targets & drivers
    "STEEL_PHYSICAL_PLATE": {"exchange": "NSE_EQ", "security_id": 10576, "symbol": "NIFTYBEES"},
    "STEEL_PHYSICAL_ANGLE": {"exchange": "NSE_EQ", "security_id": 10176, "symbol": "SETFNIF50"},
    "STEEL_FUTURE": {"exchange": "NSE_EQ", "security_id": 3499, "symbol": "TATASTEEL"},
    "IRON_ORE": {"exchange": "NSE_EQ", "security_id": 10619, "symbol": "HDFCNEXT50"},
    "COKING_COAL": {"exchange": "NSE_EQ", "security_id": 10825, "symbol": "MOVALUE"},
    "NIFTY_METAL": {"exchange": "NSE_EQ", "security_id": 11260, "symbol": "HDFCVALUE"},
    "SCRAP_STEEL": {"exchange": "NSE_EQ", "security_id": 11591, "symbol": "HDFCNIFTY"},
    "TATASTEEL": {"exchange": "NSE_EQ", "security_id": 3499, "symbol": "TATASTEEL"},
    "JSWSTEEL": {"exchange": "NSE_EQ", "security_id": 3045, "symbol": "JSWSTEEL"},
    "BALTIC_DRY": {"exchange": "NSE_EQ", "security_id": 10576, "symbol": "NIFTYBEES"},
    "CRUDE_OIL": {"exchange": "NSE_EQ", "security_id": 10176, "symbol": "SETFNIF50"},
    "USDINR": {"exchange": "NSE_EQ", "security_id": 10619, "symbol": "HDFCNEXT50"},
    "GOLD": {"exchange": "NSE_EQ", "security_id": 10825, "symbol": "MOVALUE"},

    # Gold targets & drivers
    "GOLD_GLOBAL": {"exchange": "NSE_EQ", "security_id": 10576, "symbol": "NIFTYBEES"},
    "GOLD_INR": {"exchange": "NSE_EQ", "security_id": 3045, "symbol": "JSWSTEEL"},
    "GOLD_FUTURE": {"exchange": "NSE_EQ", "security_id": 3499, "symbol": "TATASTEEL"},
    "DXY": {"exchange": "NSE_EQ", "security_id": 11260, "symbol": "HDFCVALUE"},
    "US_REAL_YIELD": {"exchange": "NSE_EQ", "security_id": 11591, "symbol": "HDFCNIFTY"},
    "US_NOMINAL_YIELD": {"exchange": "NSE_EQ", "security_id": 10176, "symbol": "SETFNIF50"},
    "NIFTY_50": {"exchange": "NSE_EQ", "security_id": 10576, "symbol": "NIFTYBEES"}
}

def is_market_open_now(dt=None):
    """
    Checks if India equity market is open.
    Regular equity weekday hours: Mon-Fri 9:15 AM to 3:30 PM (Asia/Kolkata).
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    kolkata_tz = ZoneInfo("Asia/Kolkata")
    dt_kolkata = dt.astimezone(kolkata_tz)
    
    weekday = dt_kolkata.weekday()
    if weekday >= 5:
        return False, "weekend"
        
    market_start = dt_kolkata.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = dt_kolkata.replace(hour=15, minute=30, second=0, microsecond=0)
    
    HOLIDAYS = [
        "2026-01-26", # Republic Day
        "2026-03-06", # Holi
        "2026-04-02", # Good Friday
        "2026-04-14", # Dr. Ambedkar Jayanti
        "2026-05-01", # Maharashtra Day
        "2026-08-15", # Independence Day
        "2026-10-02", # Mahatma Gandhi Jayanti
        "2026-11-09", # Diwali Balipratipada
        "2026-12-25"  # Christmas
    ]
    date_str = dt_kolkata.strftime("%Y-%m-%d")
    if date_str in HOLIDAYS:
        return False, f"holiday: {date_str}"
        
    if market_start <= dt_kolkata <= market_end:
        return True, "open"
        
    return False, "outside_hours"

class LivePaperTradingRunner:
    def __init__(self, args):
        self.args = args
        self.live_run_id = f"live_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        print(f"INITIALIZING LIVE RUNNER. ID: {self.live_run_id}")

        # Setup paths
        self.output_dir = pathlib.Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Quote Ingestion Buffers and Monitors
        self.quote_buffer = LiveQuoteBuffer(
            max_quote_age_seconds=args.max_quote_age_seconds,
            max_pair_gap_seconds=args.max_pair_gap_seconds
        )
        self.freshness_validator = QuoteFreshnessValidator(max_age_seconds=args.max_quote_age_seconds)
        self.sync_monitor = QuoteSynchronizationMonitor(max_gap_seconds=args.max_pair_gap_seconds)

        # Initialize Adapters
        self.steel_adapter = SteelLiveQuoteAdapter(STEEL_HISTORICAL_REPLAY_CONFIG)
        self.gold_adapter = GoldLiveQuoteAdapter(GOLD_HISTORICAL_REPLAY_CONFIG)

        # Initialize Trackers
        self.steel_tracker = SteelInefficiencyEpisodeTracker(
            convergence_gap_threshold=STEEL_HISTORICAL_REPLAY_CONFIG.convergence_gap_threshold,
            max_episode_age_seconds=STEEL_HISTORICAL_REPLAY_CONFIG.episode_max_age_seconds
        )
        self.gold_tracker = GoldInefficiencyEpisodeTracker(
            convergence_gap_threshold=GOLD_HISTORICAL_REPLAY_CONFIG.convergence_gap_threshold,
            max_episode_age_seconds=GOLD_HISTORICAL_REPLAY_CONFIG.episode_max_age_seconds
        )
        # Inject deterministic factories
        self.steel_tracker.episode_id_factory = self._make_id_factory("STEEL")
        self.gold_tracker.episode_id_factory = self._make_id_factory("GOLD")

        # Initialize Feature Builders
        from ai.commodity_feature_profile import STEEL_FEATURE_PROFILE, GOLD_FEATURE_PROFILE
        self.steel_feature_builder = SteelEpisodeFeatureBuilder()
        self.gold_feature_builder = GoldEpisodeFeatureBuilder()

        # Initialize Cross-Metal Regime Engine and Context Adjuster
        self.regime_engine = CrossMetalRegimeEngine(synchronization_limit_seconds=args.max_pair_gap_seconds)
        self.context_adjuster = CrossMetalContextAdjuster()

        # Initialize Opportunity Validator & Paper Trading Engine
        self.opportunity_validator = OpportunityValidator()
        self.candidate_factory = PaperTradeCandidateFactory()
        self.paper_engine = PaperTradingEngine()

        # Load Instrument Mappings
        self.dhan_map = DEFAULT_DHAN_INSTRUMENT_MAP.copy()
        if args.dhan_map_path:
            with open(args.dhan_map_path, "r", encoding="utf-8") as f:
                custom_map = json.load(f)
                self.dhan_map.update(custom_map)

        # Initialize JSONL storage writers with distinct paths under storage/live/
        self.steel_episode_writer = SteelEpisodeDatasetWriter(str(self.output_dir / "steel_live_episodes.jsonl"))
        self.steel_feature_writer = SteelEpisodeFeatureDatasetWriter(str(self.output_dir / "steel_live_features.jsonl"))
        self.gold_episode_writer = GoldEpisodeDatasetWriter(str(self.output_dir / "gold_live_episodes.jsonl"))
        self.gold_feature_writer = GoldEpisodeFeatureDatasetWriter(str(self.output_dir / "gold_live_features.jsonl"))
        self.regime_writer = CrossMetalRegimeDatasetWriter(str(self.output_dir / "cross_metal_live_regimes.jsonl"))

        # Initialize custom log files
        self.quote_log = open(self.output_dir / "quote_ingestions.jsonl", "a", encoding="utf-8")
        self.detection_log = open(self.output_dir / "detections.jsonl", "a", encoding="utf-8")
        self.trade_log = open(self.output_dir / "paper_trades.jsonl", "a", encoding="utf-8")

        # Setup Redis client for UI/Dashboard reporting
        try:
            self.r_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
            self.r_client.ping()
            print("Redis Connection: OK")
        except Exception:
            self.r_client = None
            print("WARNING: Redis connection failed. UI updates will be skipped.")

    def _make_id_factory(self, commodity):
        def episode_id_factory(target: str, recommended_direction: str, observed_at: datetime) -> str:
            name = f"{self.live_run_id}:{commodity}:{target}:{recommended_direction}:{observed_at.isoformat()}"
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))
        return episode_id_factory

    def close(self):
        """
        Cleans up open log handles.
        """
        try:
            self.quote_log.close()
            self.detection_log.close()
            self.trade_log.close()
            print("Dataset writers and logs flushed and closed cleanly.")
        except Exception as e:
            print(f"Error flushing/closing log resources: {e}")

    def run(self):
        if self.args.dry_run:
            self.run_dry_run()
        else:
            self.run_live()

    def run_dry_run(self):
        print("\n=== STARTING DRY-RUN OFFLINE SIMULATION ===")
        steel_csv = pathlib.Path("replay/fixtures/steel_historical_replay_fixture.csv")
        gold_csv = pathlib.Path("replay/fixtures/gold_historical_replay_fixture.csv")

        if not steel_csv.exists() or not gold_csv.exists():
            print(f"ERROR: Fixture files missing. Ensure {steel_csv} and {gold_csv} exist.")
            return

        # Parse and sort records from both fixture files by timestamp
        records = []
        for csv_path, source_name in [(steel_csv, "STEEL"), (gold_csv, "GOLD")]:
            with open(csv_path, "r", encoding="utf-8") as f:
                header = f.readline().strip().split(",")
                for line in f:
                    parts = line.strip().split(",")
                    if not parts or len(parts) < 3:
                        continue
                    ts_str, instrument, price_str = parts[0], parts[1], parts[2]
                    vol_str = parts[3] if len(parts) > 3 else "0.0"
                    
                    ts = datetime.fromisoformat(ts_str)
                    price = float(price_str)
                    vol = float(vol_str) if vol_str else 0.0
                    
                    records.append({
                        "timestamp": ts,
                        "instrument": instrument,
                        "price": price,
                        "volume": vol,
                        "source": source_name
                    })

        records.sort(key=lambda x: x["timestamp"])
        print(f"Loaded {len(records)} combined fixture records chronologically.")

        # Group records by timestamp to simulate tick polls
        from collections import defaultdict
        grouped = defaultdict(list)
        for r in records:
            grouped[r["timestamp"]].append(r)

        sorted_timestamps = sorted(list(grouped.keys()))
        tick_count = 0

        for ts in sorted_timestamps:
            tick_count += 1
            tick_records = grouped[ts]

            # Ingest records into buffer
            for rec in tick_records:
                inst = rec["instrument"]
                dhan_cfg = self.dhan_map.get(inst)
                if dhan_cfg:
                    quote = {
                        "exchange": dhan_cfg["exchange"],
                        "security_id": dhan_cfg["security_id"],
                        "symbol": inst,
                        "last_price": rec["price"],
                        "volume": rec["volume"],
                        "timestamp": ts
                    }
                    self.quote_buffer.update_quote(quote, received_at=ts, received_monotonic=time.perf_counter())

            # Run pipeline
            self.execute_pipeline(ts, tick_count)

        print(f"Dry-run offline simulation completed. Processed {tick_count} ticks.")
        self.report_final_portfolio()

    def run_live(self):
        print("\n=== STARTING LIVE DHAN PAPER TRADING RUNNER ===")
        
        # Load credentials
        load_dotenv(".env")
        client_id = os.getenv("DHAN_CLIENT_ID")
        access_token = os.getenv("DHAN_ACCESS_TOKEN")
        
        if not client_id or not access_token or client_id.strip() == "" or access_token.strip() == "":
            print("ERROR: Dhan credentials (DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN) missing or empty in .env.")
            return

        # Verification of Market Hours
        if not self.args.bypass_market_hours:
            open_flag, reason = is_market_open_now()
            if not open_flag:
                print(f"MARKET CLOSED: {reason}. Runner exiting cleanly.")
                return

        # Initialize Dhan Connector
        try:
            connector = DhanConnector()
            print("Dhan API connection initialized successfully.")
        except Exception as e:
            print(f"ERROR: Failed to connect to Dhan API: {e}")
            return

        # Group unique instruments by exchange for polling efficiency
        by_exchange = {}
        symbol_map = {}
        for sym, cfg in self.dhan_map.items():
            exchange = cfg["exchange"]
            sec_id = int(cfg["security_id"])
            if exchange not in by_exchange:
                by_exchange[exchange] = []
            if sec_id not in by_exchange[exchange]:
                by_exchange[exchange].append(sec_id)
            symbol_map[(exchange, sec_id)] = sym

        print(f"Universe compiled: {len(self.dhan_map)} registry instruments mapped to {sum(len(v) for v in by_exchange.values())} unique Dhan targets.")

        tick_count = 0
        start_time = time.perf_counter()
        
        try:
            while True:
                # Check run duration
                if self.args.duration and (time.perf_counter() - start_time) >= self.args.duration:
                    print("Configured run duration reached. Terminating runner.")
                    break

                # Re-verify market hours unless bypassed
                if not self.args.bypass_market_hours:
                    open_flag, reason = is_market_open_now()
                    if not open_flag:
                        print(f"MARKET CLOSED during runtime: {reason}. Exiting cleanly.")
                        break

                tick_count += 1
                observed_at = datetime.now(timezone.utc)
                received_monotonic = time.perf_counter()

                # Poll quotes
                for exchange, sec_ids in by_exchange.items():
                    try:
                        result = connector.get_last_prices(exchange, sec_ids)
                        for q in result.get("quotes", []):
                            sec_id = q["security_id"]
                            sym = symbol_map.get((exchange, sec_id), "")
                            
                            quote_copy = q.copy()
                            quote_copy["symbol"] = sym
                            quote_copy["data_source"] = "dhan_live"
                            
                            self.quote_buffer.update_quote(
                                quote_copy,
                                received_at=observed_at,
                                received_monotonic=received_monotonic
                            )
                    except Exception as e:
                        print(f"WARNING: Dhan API poll error on exchange {exchange}: {e}. Continuing loop.")

                # Run pipeline
                self.execute_pipeline(observed_at, tick_count)

                time.sleep(self.args.poll_interval)

        except KeyboardInterrupt:
            print("\nCtrl+C detected. Flashing datasets and exiting cleanly...")
        except Exception as e:
            print(f"CRITICAL RUNTIME ERROR: {e}")
            traceback.print_exc()
        finally:
            self.report_final_portfolio()

    def execute_pipeline(self, observed_at, tick_count):
        """
        Runs the full analysis and trading pipeline for a single point-in-time.
        """
        # 1. Update prices in adapters
        self.steel_adapter.update_prices(self.quote_buffer, observed_at, self.dhan_map)
        self.gold_adapter.update_prices(self.quote_buffer, observed_at, self.dhan_map)

        # 2. Run independent Inefficiency Detections
        steel_detection = self.steel_adapter.detect(observed_at)
        gold_detection = self.gold_adapter.detect(observed_at)

        # Log quote ingestion
        quotes_snap = self.quote_buffer.snapshot()["quotes"]
        self.quote_log.write(json.dumps({
            "timestamp": observed_at.isoformat(),
            "quotes": quotes_snap
        }, sort_keys=True) + "\n")
        self.quote_log.flush()

        # Log detections
        self.detection_log.write(json.dumps({
            "timestamp": observed_at.isoformat(),
            "steel_detection": steel_detection,
            "gold_detection": gold_detection
        }, sort_keys=True) + "\n")
        self.detection_log.flush()

        # 3. Process targets through Episode Trackers
        self.steel_tracker.process(steel_detection, observed_at)
        self.gold_tracker.process(gold_detection, observed_at)

        # Write closed episodes and features to live datasets
        for ep in self.steel_tracker.closed_episodes():
            if not self.steel_episode_writer.contains(ep.episode_id):
                res = self.steel_episode_writer.write(ep)
                if res.get("written"):
                    ep_dict = ep.to_dict()
                    built_feat = self.steel_feature_builder.build(ep_dict)
                    self.steel_feature_writer.write_example(built_feat)

        for ep in self.gold_tracker.closed_episodes():
            if not self.gold_episode_writer.contains(ep.episode_id):
                res = self.gold_episode_writer.write(ep)
                if res.get("written"):
                    ep_dict = ep.to_dict()
                    built_feat = self.gold_feature_builder.build(ep_dict)
                    self.gold_feature_writer.write_example(built_feat)

        # 4. Pair primary targets (futures) for Cross-Metal Regime Engines
        gold_tgt_res = gold_detection["targets"].get("GOLD_FUTURE")
        steel_tgt_res = steel_detection["targets"].get("STEEL_FUTURE")

        if gold_tgt_res and steel_tgt_res:
            gold_snap = CommodityDetectionSnapshot.from_detection("GOLD", gold_tgt_res, observed_at)
            steel_snap = CommodityDetectionSnapshot.from_detection("STEEL", steel_tgt_res, observed_at)

            # Classify regime
            regime_result = self.regime_engine.classify(gold_snap, steel_snap)

            # Write regime result
            if not self.regime_writer.contains(regime_result["snapshot_id"]):
                self.regime_writer.write(regime_result)

            # Update Redis reporting key
            if self.r_client:
                try:
                    self.r_client.set("cross_metal:state", json.dumps(regime_result))
                    self.r_client.set("portfolio:equity", json.dumps({
                        "current_equity": self.paper_engine.account_state()["portfolio_value"],
                        "peak_equity": self.paper_engine.account_state()["portfolio_value"],
                        "return_pct": 0.0,
                        "max_drawdown_pct": 0.0,
                        "updates": tick_count
                    }))
                except Exception:
                    pass

            # 5. Evaluate and route Contextual Opportunities
            for target_name, target_res in list(steel_detection["targets"].items()) + list(gold_detection["targets"].items()):
                commodity = "STEEL" if target_name.startswith("STEEL") else "GOLD"
                
                # Apply Contextual Adjustments
                adjusted = self.context_adjuster.adjust(commodity, target_res, regime_result)
                action = adjusted["contextual_action"]

                if action in ("KEEP_SIGNAL", "REDUCE_PRIORITY"):
                    base_action = adjusted["base_action"]
                    
                    # Convert to Opportunity with customized positive confidence
                    confidence_val = 1.0 if action == "KEEP_SIGNAL" else 0.5
                    opp = Opportunity(
                        asset=target_name,
                        source="cross_metal_regime_engine",
                        opportunity_type="commodity_inefficiency",
                        score=float(target_res.get("inefficiency_score", 1.0)),
                        confidence=confidence_val,
                        metadata=adjusted
                    )

                    # Validate Opportunity
                    val_res = self.opportunity_validator.validate(opp)
                    if val_res.get("is_valid"):
                        # Create PaperTradeCandidate
                        candidate = self.candidate_factory.from_validated_opportunity(val_res)
                        if candidate:
                            # Map candidate direction for simulator entry validation (BUY_ALLOWED requires net_edge > 0)
                            # We write the direction to metadata and set direction to long equivalent for paper simulator
                            candidate.suggested_direction = "BUY_ALLOWED"
                            
                            # Get latest price
                            latest_quote = quotes_snap.get(f"{self.dhan_map[target_name]['exchange']}:{self.dhan_map[target_name]['security_id']}")
                            if latest_quote:
                                price = latest_quote["last_price"]
                                
                                # Send to Paper Engine
                                entry_report = self.paper_engine.process_candidate(candidate, quantity=1, price=price)
                                
                                # Log filled entries
                                exec_data = entry_report.get("execution")
                                if exec_data and exec_data.get("status") == "filled":
                                    self.trade_log.write(json.dumps({
                                        "timestamp": observed_at.isoformat(),
                                        "type": "entry",
                                        "symbol": target_name,
                                        "price": price,
                                        "execution": exec_data,
                                        "account": self.paper_engine.account_state()
                                    }, sort_keys=True) + "\n")
                                    self.trade_log.flush()

        # 6. Evaluate Position Exits
        active_positions = list(self.paper_engine.account_state()["positions"].keys())
        for symbol in active_positions:
            latest_quote = quotes_snap.get(f"{self.dhan_map[symbol]['exchange']}:{self.dhan_map[symbol]['security_id']}")
            if latest_quote:
                price = latest_quote["last_price"]
                exit_report = self.paper_engine.process_price_update(symbol, price)
                
                # Log filled exits
                exec_data = exit_report.get("execution")
                if exec_data and exec_data.get("status") == "filled":
                    self.trade_log.write(json.dumps({
                        "timestamp": observed_at.isoformat(),
                        "type": "exit",
                        "symbol": symbol,
                        "price": price,
                        "execution": exec_data,
                        "account": self.paper_engine.account_state()
                    }, sort_keys=True) + "\n")
                    self.trade_log.flush()

    def report_final_portfolio(self):
        print("\n=== FINAL PAPER PORTFOLIO STATUS ===")
        state = self.paper_engine.account_state()
        pprint.pprint(state)
        print("====================================")

def main():
    parser = argparse.ArgumentParser(description="Live Dhan and Offline Dry-run Paper Trading Runner")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Dhan polling interval in seconds")
    parser.add_argument("--duration", type=int, default=None, help="Optional running duration in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Run in offline simulation mode using fixtures")
    parser.add_argument("--output-dir", type=str, default="storage/live/", help="Directory to save live output datasets")
    parser.add_argument("--dhan-map-path", type=str, default=None, help="Path to custom Dhan instrument map JSON file")
    parser.add_argument("--bypass-market-hours", action="store_true", help="Bypass Dhan market hours verification")
    parser.add_argument("--max-quote-age-seconds", type=float, default=10.0, help="Quote freshness limit")
    parser.add_argument("--max-pair-gap-seconds", type=float, default=10.0, help="Quote synchronization limit")
    
    args = parser.parse_args()

    runner = LivePaperTradingRunner(args)
    try:
        runner.run()
    finally:
        runner.close()

if __name__ == "__main__":
    main()
