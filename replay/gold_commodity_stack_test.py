import unittest
import math
import pathlib
import os
import shutil
import dataclasses
from datetime import datetime, timezone

from ai.gold_commodity_instrument_registry import GoldCommodityInstrumentRegistry
from ai.gold_signal_graph import GoldSignalGraph
from ai.gold_pressure_calculator import GoldPressureCalculator
from ai.gold_inefficiency_detector import GoldInefficiencyDetector
from ai.gold_inefficiency_episode import GoldInefficiencyEpisode
from ai.gold_inefficiency_episode_tracker import GoldInefficiencyEpisodeTracker
from storage.gold_episode_dataset_writer import GoldEpisodeDatasetWriter
from storage.gold_episode_dataset_reader import GoldEpisodeDatasetReader
from storage.gold_episode_feature_dataset_writer import GoldEpisodeFeatureDatasetWriter
from storage.gold_episode_feature_dataset_reader import GoldEpisodeFeatureDatasetReader
from ai.gold_historical_replay_adapter import GoldHistoricalReplayAdapter
from storage.commodity_historical_dataset_reader import CommodityHistoricalDatasetReader
from replay.commodity_historical_replay_runner import CommodityHistoricalReplayRunner
from ai.commodity_replay_config import GOLD_HISTORICAL_REPLAY_CONFIG

class TestGoldInstrumentRegistry(unittest.TestCase):
    def test_registry(self):
        reg = GoldCommodityInstrumentRegistry()
        
        # 1. Registry contains GOLD_GLOBAL
        inst = reg.get("GOLD_GLOBAL")
        self.assertIsNotNone(inst, "Assertion 1: GOLD_GLOBAL should be in registry")
        
        # 2. Role is TARGET
        self.assertEqual(inst["role"], "TARGET", "Assertion 2: GOLD_GLOBAL role must be TARGET")
        
        # 3. Duplicate rejection
        with self.assertRaises(ValueError, msg="Assertion 3"):
            reg.register(inst)
            
        # 4. Invalid role error
        bad_role = inst.copy()
        bad_role["symbol"] = "BAD_ROLE"
        bad_role["role"] = "INVALID"
        with self.assertRaises(ValueError, msg="Assertion 4"):
            reg.register(bad_role)
            
        # 5. Invalid category error
        bad_cat = inst.copy()
        bad_cat["symbol"] = "BAD_CAT"
        bad_cat["category"] = "INVALID"
        with self.assertRaises(ValueError, msg="Assertion 5"):
            reg.register(bad_cat)
            
        # 6. Lookback negative/zero error
        bad_lookback = inst.copy()
        bad_lookback["symbol"] = "BAD_LOOKBACK"
        bad_lookback["default_lookback_seconds"] = -10.0
        with self.assertRaises(ValueError, msg="Assertion 6"):
            reg.register(bad_lookback)
            
        # 7. Lookback boolean type error
        bad_lookback_bool = inst.copy()
        bad_lookback_bool["symbol"] = "BAD_LOOKBACK_BOOL"
        bad_lookback_bool["default_lookback_seconds"] = True
        with self.assertRaises(TypeError, msg="Assertion 7"):
            reg.register(bad_lookback_bool)
            
        # 8. Maximum age nan error
        bad_age = inst.copy()
        bad_age["symbol"] = "BAD_AGE"
        bad_age["default_maximum_age_seconds"] = float('nan')
        with self.assertRaises(ValueError, msg="Assertion 8"):
            reg.register(bad_age)
            
        # 9. is_tradeable boolean validation
        bad_tradeable = inst.copy()
        bad_tradeable["symbol"] = "BAD_TRADEABLE"
        bad_tradeable["is_tradeable"] = "Yes"
        with self.assertRaises(TypeError, msg="Assertion 9"):
            reg.register(bad_tradeable)
            
        # 10. Defensive copy check
        inst_mod = reg.get("GOLD_GLOBAL")
        inst_mod["name"] = "Modified Name"
        inst_original = reg.get("GOLD_GLOBAL")
        self.assertNotEqual(inst_original["name"], "Modified Name", "Assertion 10: Modifying retrieved dict should not affect registry")

class TestGoldSignalGraph(unittest.TestCase):
    def test_signal_graph(self):
        graph = GoldSignalGraph()
        
        # 11. Initial relationship count is 16
        self.assertEqual(len(graph.to_dict()), 16, "Assertion 11: Graph should start with 16 relations")
        
        # 12. Self-relation rejection
        with self.assertRaises(ValueError, msg="Assertion 12"):
            graph.add_relationship({
                "source": "GOLD_GLOBAL",
                "target": "GOLD_GLOBAL",
                "direction": "positive",
                "weight": 0.5
            })
            
        # 13. Negative weight rejection
        with self.assertRaises(ValueError, msg="Assertion 13"):
            graph.add_relationship({
                "source": "DXY",
                "target": "GOLD_GLOBAL",
                "direction": "negative",
                "weight": -0.5
            })
            
        # 14. Weight boolean type check
        with self.assertRaises(TypeError, msg="Assertion 14"):
            graph.add_relationship({
                "source": "DXY",
                "target": "GOLD_GLOBAL",
                "direction": "negative",
                "weight": True
            })
            
        # 15. Invalid direction rejection
        with self.assertRaises(ValueError, msg="Assertion 15"):
            graph.add_relationship({
                "source": "DXY",
                "target": "GOLD_GLOBAL",
                "direction": "invalid",
                "weight": 0.5
            })
            
        # 16. Duplicate relationship rejection
        with self.assertRaises(ValueError, msg="Assertion 16"):
            graph.add_relationship({
                "source": "DXY",
                "target": "GOLD_GLOBAL",
                "direction": "negative",
                "weight": 0.2
            })
            
        # 17. Unregistered source rejection
        with self.assertRaises(ValueError, msg="Assertion 17"):
            graph.add_relationship({
                "source": "UNREGISTERED_SRC",
                "target": "GOLD_GLOBAL",
                "direction": "positive",
                "weight": 0.5
            })
            
        # 18. Unregistered target rejection
        with self.assertRaises(ValueError, msg="Assertion 18"):
            graph.add_relationship({
                "source": "DXY",
                "target": "UNREGISTERED_TGT",
                "direction": "positive",
                "weight": 0.5
            })
            
        # 19. Calibrated flag must be False
        for rel in graph.to_dict():
            self.assertFalse(rel["is_historically_calibrated"], "Assertion 19: Calibration flag must be False")
            
        # 20. Sources for target correctness
        self.assertIn("USDINR", graph.sources_for_target("GOLD_FUTURE"), "Assertion 20: GOLD_FUTURE must be driven by USDINR")

class TestGoldPressureCalculator(unittest.TestCase):
    def test_pressure_calculator(self):
        calc = GoldPressureCalculator(minimum_coverage_ratio=0.50)
        
        # Scenario: DXY down 5%, yields down 5%, silver up 5%.
        # DXY (wt 0.15, neg direction): contribution = -5 * 0.15 * -1 = +0.75
        # US_REAL_YIELD (wt 0.15, neg direction): contribution = -5 * 0.15 * -1 = +0.75
        # US_NOMINAL_YIELD (wt 0.10, neg direction): contribution = -5 * 0.10 * -1 = +0.50
        # SILVER (wt 0.10, pos direction): contribution = +5 * 0.10 * 1 = +0.50
        # Total observed weight: 0.15 + 0.15 + 0.10 + 0.10 = 0.50
        # Total possible weight of GOLD_GLOBAL drivers: 0.15 + 0.15 + 0.10 + 0.10 + 0.10 + 0.05 + 0.05 + 0.05 + 0.05 + 0.10 + 0.10 = 1.00
        # Coverage ratio: 0.50 / 1.00 = 0.50
        # Raw pressure: 0.75 + 0.75 + 0.50 + 0.50 = 2.50
        # Expected change: 2.50 / 0.50 = 5.00
        
        changes = {
            "DXY": -5.0,
            "US_REAL_YIELD": -5.0,
            "US_NOMINAL_YIELD": -5.0,
            "SILVER": 5.0
        }
        res = calc.calculate("GOLD_GLOBAL", changes)
        
        # 21. Raw pressure rounding
        self.assertEqual(res["raw_pressure_score"], 2.500000, "Assertion 21: Raw pressure score calculation")
        
        # 22. Expected change
        self.assertEqual(res["expected_change"], 5.000000, "Assertion 22: Expected change calculation")
        
        # 23. Observed weight
        self.assertEqual(res["observed_weight"], 0.500000, "Assertion 23: Observed weight calculation")
        
        # 24. Coverage ratio
        self.assertEqual(res["coverage_ratio"], 0.500000, "Assertion 24: Coverage ratio calculation")
        
        # 25. Coverage sufficient
        self.assertTrue(res["is_sufficient_coverage"], "Assertion 25: Sufficient coverage check")
        
        # 26. Contributor sorting
        contribs = res["contributors"]
        self.assertEqual(contribs[0]["source"], "DXY", "Assertion 26: First contributor should be DXY (highest abs contribution)")
        
        # 27. Regime flags
        # SP500 and CRUDE_OIL are regime dependent. Let's add SP500 and verify flag.
        changes_with_regime = changes.copy()
        changes_with_regime["SP500"] = 1.0
        res_regime = calc.calculate("GOLD_GLOBAL", changes_with_regime)
        sp500_contrib = next(c for c in res_regime["contributors"] if c["source"] == "SP500")
        self.assertTrue(sp500_contrib["is_regime_dependent"], "Assertion 27: SP500 contributor should be marked as regime dependent")
        
        # 28. Missing sources alphabetical sorting
        self.assertIn("CRUDE_OIL", res["missing_sources"], "Assertion 28: CRUDE_OIL should be missing")
        self.assertEqual(res["missing_sources"], sorted(res["missing_sources"]), "Assertion 28: Missing sources should be sorted alphabetically")
        
        # 29. Unregistered target error
        with self.assertRaises(ValueError, msg="Assertion 29"):
            calc.calculate("UNREGISTERED_TGT", changes)
            
        # 30. Boolean values inside changes dictionary
        with self.assertRaises(TypeError, msg="Assertion 30"):
            calc.calculate("GOLD_GLOBAL", {"DXY": True})

class TestGoldInefficiencyDetector(unittest.TestCase):
    def test_detector(self):
        det = GoldInefficiencyDetector(
            minimum_pressure_threshold=0.50,
            minimum_coverage_ratio=0.50,
            efficient_gap_threshold=0.75,
            overreaction_multiplier=1.5
        )
        
        # Scenario 1: Missing target actual price
        changes_insufficient = {
            "DXY": -5.0,
            "US_REAL_YIELD": -5.0,
            "US_NOMINAL_YIELD": -5.0,
            "SILVER": 5.0
        }
        res_insufficient = det.detect(changes_insufficient)
        
        # 31. INSUFFICIENT_DATA when target missing
        self.assertEqual(res_insufficient["targets"]["GOLD_GLOBAL"]["status"], "INSUFFICIENT_DATA", "Assertion 31")
        
        # Scenario 2: Low coverage (only DXY provided)
        changes_low_cov = {
            "GOLD_GLOBAL": 0.0,
            "DXY": -5.0
        }
        res_low_cov = det.detect(changes_low_cov)
        
        # 32. LOW_COVERAGE when too few drivers
        self.assertEqual(res_low_cov["targets"]["GOLD_GLOBAL"]["status"], "LOW_COVERAGE", "Assertion 32")
        
        # Scenario 3: Low pressure (drivers have 0 change)
        changes_low_pres = {
            "GOLD_GLOBAL": 0.0,
            "DXY": 0.0,
            "US_REAL_YIELD": 0.0,
            "US_NOMINAL_YIELD": 0.0,
            "SILVER": 0.0,
            "INFLATION_EXPECTATION": 0.0,
            "CRUDE_OIL": 0.0
        }
        res_low_pres = det.detect(changes_low_pres)
        
        # 33. LOW_PRESSURE when pressure below threshold
        self.assertEqual(res_low_pres["targets"]["GOLD_GLOBAL"]["status"], "LOW_PRESSURE", "Assertion 33")
        
        # Scenario 4: Efficient (actual matches expected)
        # Expected: 5.0. Actual: 4.8. Gap: 0.2.
        changes_efficient = {
            "GOLD_GLOBAL": 4.8,
            "DXY": -5.0,
            "US_REAL_YIELD": -5.0,
            "US_NOMINAL_YIELD": -5.0,
            "SILVER": 5.0,
            "INFLATION_EXPECTATION": 5.0,
            "CRUDE_OIL": 5.0
        }
        res_efficient = det.detect(changes_efficient)
        
        # 34. EFFICIENT when gap below threshold
        self.assertEqual(res_efficient["targets"]["GOLD_GLOBAL"]["status"], "EFFICIENT", "Assertion 34")
        
        # Scenario 5: Divergence (Expected: 5.0. Actual: -1.0. Gap: 6.0)
        changes_div = changes_efficient.copy()
        changes_div["GOLD_GLOBAL"] = -1.0
        res_div = det.detect(changes_div)
        
        # 35. DIVERGENCE when opposite signs
        self.assertEqual(res_div["targets"]["GOLD_GLOBAL"]["status"], "DIVERGENCE", "Assertion 35")
        
        # Scenario 6: Non-Reaction (Expected: 5.0. Actual: 0.1. Gap: 4.9)
        changes_non_react = changes_efficient.copy()
        changes_non_react["GOLD_GLOBAL"] = 0.1
        res_non_react = det.detect(changes_non_react)
        
        # 36. NON_REACTION when actual near 0
        self.assertEqual(res_non_react["targets"]["GOLD_GLOBAL"]["status"], "NON_REACTION", "Assertion 36")
        
        # Scenario 7: Underreaction (Expected: 5.0. Actual: 2.0. Gap: 3.0)
        changes_under = changes_efficient.copy()
        changes_under["GOLD_GLOBAL"] = 2.0
        res_under = det.detect(changes_under)
        
        # 37. UNDERREACTION when same sign but smaller
        self.assertEqual(res_under["targets"]["GOLD_GLOBAL"]["status"], "UNDERREACTION", "Assertion 37")
        
        # Scenario 8: Overreaction (Expected: 5.0. Actual: 8.0. Gap: 3.0)
        changes_over = changes_efficient.copy()
        changes_over["GOLD_GLOBAL"] = 8.0
        res_over = det.detect(changes_over)
        
        # 38. OVERREACTION when same sign but larger
        self.assertEqual(res_over["targets"]["GOLD_GLOBAL"]["status"], "OVERREACTION", "Assertion 38")
        
        # 39. Direction recommended for underreaction (Expected 5.0 > Actual 2.0 => LONG)
        self.assertEqual(res_under["targets"]["GOLD_GLOBAL"]["recommended_direction"], "LONG_TARGET", "Assertion 39")
        
        # 40. Dynamic explanation contains target keyword
        self.assertIn("Gold showed little or no upward reaction", res_non_react["targets"]["GOLD_GLOBAL"]["explanation"], "Assertion 40")

class TestGoldReplayIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = pathlib.Path("storage/test_gold_replay")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.episode_output = self.test_dir / "episodes.jsonl"
        self.feature_output = self.test_dir / "features.jsonl"
        self.fixture_path = pathlib.Path("replay/fixtures/gold_historical_replay_fixture.csv")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_replay(self):
        # 41. Backtest runner successfully processes input records
        reader = CommodityHistoricalDatasetReader(str(self.fixture_path), strict=True)
        records = reader.read_all()
        self.assertGreater(len(records), 0, "Assertion 41: Records count should be greater than 0")
        
        config = dataclasses.replace(
            GOLD_HISTORICAL_REPLAY_CONFIG,
            output_episode_dataset_path=str(self.episode_output),
            output_feature_dataset_path=str(self.feature_output),
            replay_run_id="gold-test-run-id",
            strict_chronology=True
        )

        adapter = GoldHistoricalReplayAdapter(config)
        tracker = GoldInefficiencyEpisodeTracker(
            convergence_gap_threshold=config.convergence_gap_threshold,
            max_episode_age_seconds=config.episode_max_age_seconds
        )
        episode_writer = GoldEpisodeDatasetWriter(str(self.episode_output))
        feature_writer = GoldEpisodeFeatureDatasetWriter(str(self.feature_output))

        runner = CommodityHistoricalReplayRunner(
            records=records,
            config=config,
            adapter=adapter,
            episode_tracker=tracker,
            episode_writer=episode_writer,
            feature_writer=feature_writer
        )

        manifest_data = runner.manifest(input_path=str(self.fixture_path), input_sha256="test-sha")
        summary = manifest_data["result_summary"]
        
        # 42. Closed episode count is greater than 0
        self.assertGreater(summary["closed_episode_count"], 0, "Assertion 42: Replay must close at least one episode")
        
        # 43. Dataset writer generated correct file and record count
        self.assertTrue(self.episode_output.exists(), "Assertion 43: Episode output file should exist")
        
        # 44. Outcome distribution includes expected outcomes (e.g. CONVERGED)
        outcome_counts = summary["outcome_counts"]
        self.assertIn("CONVERGED", outcome_counts, "Assertion 44: CONVERGED outcome should be logged")
        
        # 45. Manifest version is correct
        self.assertEqual(manifest_data["replay_schema_version"], "1.0", "Assertion 45")
        
        # 46. is_historically_calibrated is False
        self.assertFalse(manifest_data["is_historically_calibrated"], "Assertion 46")

if __name__ == "__main__":
    unittest.main()
