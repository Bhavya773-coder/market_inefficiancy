import math
import copy
from typing import List, Dict, Any
from ai.gold_commodity_instrument_registry import GoldCommodityInstrumentRegistry

class GoldSignalGraph:
    """
    Directional relationships and weights between Gold targets and driver instruments.
    """
    def __init__(self):
        self._relationships: List[Dict[str, Any]] = []

        initial_relationships = [
            {
                "source": "DXY",
                "target": "GOLD_GLOBAL",
                "direction": "negative",
                "weight": 0.15,
                "relationship_type": "macro_pressure",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "Stronger US Dollar typically pressures dollar-denominated global gold price"
            },
            {
                "source": "US_REAL_YIELD",
                "target": "GOLD_GLOBAL",
                "direction": "negative",
                "weight": 0.15,
                "relationship_type": "rates_pressure",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "Higher real interest rates increase the opportunity cost of holding non-yielding gold"
            },
            {
                "source": "US_NOMINAL_YIELD",
                "target": "GOLD_GLOBAL",
                "direction": "negative",
                "weight": 0.10,
                "relationship_type": "rates_pressure",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "Nominal rate increases general yields, negative for gold"
            },
            {
                "source": "INFLATION_EXPECTATION",
                "target": "GOLD_GLOBAL",
                "direction": "positive",
                "weight": 0.10,
                "relationship_type": "inflation_hedge",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "Rising inflation expectations support gold demand as a purchasing power store"
            },
            {
                "source": "SILVER",
                "target": "GOLD_GLOBAL",
                "direction": "positive",
                "weight": 0.10,
                "relationship_type": "precious_metals_beta",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "Silver price co-movements reflect broader precious metals sector demand"
            },
            {
                "source": "VIX",
                "target": "GOLD_GLOBAL",
                "direction": "positive",
                "weight": 0.05,
                "relationship_type": "risk_off_hedge",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "Fear index spikes reflect systemic risk, driving safe-haven gold demand"
            },
            {
                "source": "SP500",
                "target": "GOLD_GLOBAL",
                "direction": "negative",
                "weight": 0.05,
                "relationship_type": "equity_competition",
                "is_regime_dependent": True,
                "is_historically_calibrated": False,
                "explanation": "Weak equity markets drive flows into defensive assets like gold under certain regimes"
            },
            {
                "source": "CRUDE_OIL",
                "target": "GOLD_GLOBAL",
                "direction": "positive",
                "weight": 0.05,
                "relationship_type": "commodity_index_beta",
                "is_regime_dependent": True,
                "is_historically_calibrated": False,
                "explanation": "Higher energy prices lead general commodity basket inflation pressure"
            },
            {
                "source": "GOLD_ETF_FLOW",
                "target": "GOLD_GLOBAL",
                "direction": "positive",
                "weight": 0.05,
                "relationship_type": "investment_flow",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "Physical gold ETF creations signal retail and institutional investment demand"
            },
            {
                "source": "CENTRAL_BANK_BUYING",
                "target": "GOLD_GLOBAL",
                "direction": "positive",
                "weight": 0.10,
                "relationship_type": "sovereign_flow",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "Official sector purchasing supports physical gold demand floor"
            },
            {
                "source": "GLOBAL_LIQUIDITY",
                "target": "GOLD_GLOBAL",
                "direction": "positive",
                "weight": 0.10,
                "relationship_type": "liquidity_expansion",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "Fiat monetary base expansion acts as long-term tailwind for gold valuation"
            },
            # Indian Spot target
            {
                "source": "GOLD_GLOBAL",
                "target": "GOLD_INR",
                "direction": "positive",
                "weight": 0.50,
                "relationship_type": "direct_arbitrage",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "Indian physical spot gold tracks global London gold prices closely"
            },
            {
                "source": "USDINR",
                "target": "GOLD_INR",
                "direction": "positive",
                "weight": 0.40,
                "relationship_type": "import_parity",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "Rupee depreciation raises landed import costs of gold in India"
            },
            {
                "source": "DXY",
                "target": "GOLD_INR",
                "direction": "negative",
                "weight": 0.10,
                "relationship_type": "indirect_macro",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "US Dollar strength pressures global gold, indirectly affecting Indian landed cost"
            },
            # Futures target
            {
                "source": "GOLD_GLOBAL",
                "target": "GOLD_FUTURE",
                "direction": "positive",
                "weight": 0.50,
                "relationship_type": "direct_arbitrage",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "MCX futures track international spot gold reference prices"
            },
            {
                "source": "USDINR",
                "target": "GOLD_FUTURE",
                "direction": "positive",
                "weight": 0.50,
                "relationship_type": "import_parity",
                "is_regime_dependent": False,
                "is_historically_calibrated": False,
                "explanation": "USDINR moves directly affect domestic futures contract valuations"
            }
        ]

        for rel in initial_relationships:
            self.add_relationship(rel)

    def validate(self, rel: Dict[str, Any]):
        """
        Validates a relationship definition.
        """
        if not isinstance(rel, dict):
            raise TypeError("Relationship must be a dictionary")
            
        required_keys = ["source", "target", "direction", "weight"]
        for k in required_keys:
            if k not in rel:
                raise KeyError(f"Missing required key in relationship: {k}")

        source = rel["source"]
        target = rel["target"]
        direction = rel["direction"]
        weight = rel["weight"]

        if source == target:
            raise ValueError(f"Self-relation is not allowed: {source} -> {target}")

        if type(weight) is bool or not isinstance(weight, (int, float)):
            raise TypeError("Weight must be float or int and not bool")
        if weight <= 0 or math.isnan(weight) or math.isinf(weight):
            raise ValueError("Weight must be positive and finite")

        if direction not in ("positive", "negative", "mixed"):
            raise ValueError(f"Invalid direction: {direction}")

        # Check for duplicates
        for existing in self._relationships:
            if existing["source"] == source and existing["target"] == target:
                raise ValueError(f"Duplicate relationship already exists: {source} -> {target}")

        # Check registered instruments
        registry = GoldCommodityInstrumentRegistry()
        if not registry.contains(source):
            raise ValueError(f"Source instrument '{source}' is not registered")
        if not registry.contains(target):
            raise ValueError(f"Target instrument '{target}' is not registered")

    def add_relationship(self, rel: Dict[str, Any]):
        """
        Validates and adds a new relationship.
        """
        self.validate(rel)
        new_rel = {
            "source": rel["source"],
            "target": rel["target"],
            "direction": rel["direction"],
            "weight": float(rel["weight"]),
            "relationship_type": rel.get("relationship_type", "proxy_relationship"),
            "is_regime_dependent": bool(rel.get("is_regime_dependent", False)),
            "is_historically_calibrated": False,
            "explanation": rel.get("explanation", "")
        }
        self._relationships.append(new_rel)

    def relationships_for_target(self, target: str) -> List[Dict[str, Any]]:
        """
        Returns defensive copies of relationships where the instrument is target.
        """
        return [copy.deepcopy(r) for r in self._relationships if r["target"] == target]

    def sources_for_target(self, target: str) -> List[str]:
        """
        Returns list of source instrument symbols driving the target.
        """
        return [r["source"] for r in self._relationships if r["target"] == target]

    def to_dict(self) -> List[Dict[str, Any]]:
        """
        Returns a complete copy of the graph relationships list.
        """
        return copy.deepcopy(self._relationships)
