import math
import copy
from typing import Dict, Any, List, Optional

class GoldCommodityInstrumentRegistry:
    """
    Registry for Gold commodity target and driver instruments.
    """
    def __init__(self):
        self._instruments: Dict[str, Dict[str, Any]] = {}
        
        # Initial registration of the Gold universe
        default_lookback = 86400.0  # 1 day
        default_max_age = 172800.0   # 2 days

        initial_universe = [
            # Targets
            {
                "symbol": "GOLD_GLOBAL",
                "name": "Global Spot Gold",
                "role": "TARGET",
                "category": "PRECIOUS_METAL",
                "unit": "USD/OZ",
                "currency": "USD",
                "market": "London Spot",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "Benchmark global gold spot price reference"
            },
            {
                "symbol": "GOLD_INR",
                "name": "Indian Gold Spot Reference",
                "role": "TARGET",
                "category": "PRECIOUS_METAL",
                "unit": "INR/10G",
                "currency": "INR",
                "market": "Physical India",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": True,
                "is_required": True,
                "description": "Physical Gold spot reference price in India"
            },
            {
                "symbol": "GOLD_FUTURE",
                "name": "MCX Gold Futures",
                "role": "TARGET",
                "category": "PRECIOUS_METAL",
                "unit": "INR/10G",
                "currency": "INR",
                "market": "MCX",
                "default_lookback_seconds": 3600.0,  # 1 hour lookback for futures
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": True,
                "is_required": True,
                "description": "Exchange-traded gold futures contract"
            },
            # Drivers
            {
                "symbol": "DXY",
                "name": "US Dollar Index",
                "role": "DRIVER",
                "category": "FX",
                "unit": "Index",
                "currency": "USD",
                "market": "ICE",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "US Dollar index measuring greenback strength"
            },
            {
                "symbol": "USDINR",
                "name": "USD INR Exchange Rate",
                "role": "DRIVER",
                "category": "FX",
                "unit": "INR",
                "currency": "INR",
                "market": "Interbank FX",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "USD to INR spot exchange rate"
            },
            {
                "symbol": "US_REAL_YIELD",
                "name": "US 10Y Real Yield",
                "role": "DRIVER",
                "category": "RATES",
                "unit": "Percent",
                "currency": "USD",
                "market": "Treasury inflation-protected securities",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "US 10-year inflation-adjusted real yield"
            },
            {
                "symbol": "US_NOMINAL_YIELD",
                "name": "US 10Y Treasury Yield",
                "role": "DRIVER",
                "category": "RATES",
                "unit": "Percent",
                "currency": "USD",
                "market": "Treasury",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "US 10-year nominal government bond yield"
            },
            {
                "symbol": "INFLATION_EXPECTATION",
                "name": "US 10Y Break-even Inflation",
                "role": "DRIVER",
                "category": "INFLATION",
                "unit": "Percent",
                "currency": "USD",
                "market": "Derived",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "Market-implied 10-year expected inflation rate"
            },
            {
                "symbol": "SILVER",
                "name": "Global Spot Silver",
                "role": "DRIVER",
                "category": "PRECIOUS_METAL",
                "unit": "USD/OZ",
                "currency": "USD",
                "market": "London Spot",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "Global spot silver price index"
            },
            {
                "symbol": "CRUDE_OIL",
                "name": "Brent Crude Oil",
                "role": "DRIVER",
                "category": "ENERGY",
                "unit": "USD/BBL",
                "currency": "USD",
                "market": "ICE",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "Brent crude oil futures contract"
            },
            {
                "symbol": "VIX",
                "name": "CBOE Volatility Index",
                "role": "DRIVER",
                "category": "VOLATILITY",
                "unit": "Index",
                "currency": "USD",
                "market": "CBOE",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "Market volatility index"
            },
            {
                "symbol": "SP500",
                "name": "S&P 500 Index",
                "role": "DRIVER",
                "category": "EQUITY",
                "unit": "Index",
                "currency": "USD",
                "market": "US Exchanges",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "Standard & Poor's 500 equity index"
            },
            {
                "symbol": "GOLD_ETF_FLOW",
                "name": "Gold ETF Capital Flows",
                "role": "DRIVER",
                "category": "FLOW",
                "unit": "Tons",
                "currency": "USD",
                "market": "Global",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "Estimated physical gold ETF fund flows"
            },
            {
                "symbol": "CENTRAL_BANK_BUYING",
                "name": "Central Bank Buying Net Flow",
                "role": "DRIVER",
                "category": "CENTRAL_BANK",
                "unit": "Tons",
                "currency": "USD",
                "market": "Global",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "Net official sovereign gold reserves flow"
            },
            {
                "symbol": "GLOBAL_LIQUIDITY",
                "name": "Global M2 Liquidity Proxy",
                "role": "DRIVER",
                "category": "LIQUIDITY",
                "unit": "USD Billions",
                "currency": "USD",
                "market": "Global",
                "default_lookback_seconds": default_lookback,
                "default_maximum_age_seconds": default_max_age,
                "is_tradeable": False,
                "is_required": True,
                "description": "Aggregate global major central bank money supply"
            }
        ]

        for definition in initial_universe:
            self.register(definition)

    def validate(self, definition: Dict[str, Any]):
        """
        Validates the instrument definition dictionary.
        """
        if not isinstance(definition, dict):
            raise TypeError("Instrument definition must be a dictionary")
            
        required_keys = [
            "name", "symbol", "role", "category", "unit", "currency", "market",
            "default_lookback_seconds", "default_maximum_age_seconds",
            "is_tradeable", "is_required", "description"
        ]
        for k in required_keys:
            if k not in definition:
                raise KeyError(f"Missing required key in definition: {k}")

        symbol = definition["symbol"]
        if not isinstance(symbol, str) or not symbol.strip() or not symbol.isupper():
            raise ValueError(f"symbol must be non-empty uppercase string, got: {symbol}")
            
        if not isinstance(definition["name"], str) or not definition["name"].strip():
            raise ValueError("name must be a non-empty string")
            
        role = definition["role"]
        if role not in ("TARGET", "DRIVER", "REGIME"):
            raise ValueError(f"Invalid role: {role}")
            
        category = definition["category"]
        valid_categories = ("FX", "RATES", "INFLATION", "PRECIOUS_METAL", "ENERGY", "VOLATILITY", "EQUITY", "FLOW", "CENTRAL_BANK", "LIQUIDITY")
        if category not in valid_categories:
            raise ValueError(f"Invalid category: {category}")
            
        for field in ("unit", "currency", "market", "description"):
            if not isinstance(definition[field], str) or not definition[field].strip():
                raise ValueError(f"{field} must be a non-empty string")
                
        if not isinstance(definition["is_tradeable"], bool):
            raise TypeError("is_tradeable must be a boolean")
        if not isinstance(definition["is_required"], bool):
            raise TypeError("is_required must be a boolean")
            
        lookback = definition["default_lookback_seconds"]
        if type(lookback) is bool or not isinstance(lookback, (int, float)):
            raise TypeError("default_lookback_seconds must be a float or int and not bool")
        if lookback <= 0 or math.isnan(lookback) or math.isinf(lookback):
            raise ValueError("default_lookback_seconds must be positive and finite")
            
        age = definition["default_maximum_age_seconds"]
        if type(age) is bool or not isinstance(age, (int, float)):
            raise TypeError("default_maximum_age_seconds must be a float or int and not bool")
        if age <= 0 or math.isnan(age) or math.isinf(age):
            raise ValueError("default_maximum_age_seconds must be positive and finite")

    def register(self, definition: Dict[str, Any]):
        """
        Validates and registers an instrument definition.
        """
        self.validate(definition)
        symbol = definition["symbol"]
        if symbol in self._instruments:
            raise ValueError(f"Instrument '{symbol}' is already registered")
        self._instruments[symbol] = copy.deepcopy(definition)

    def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Returns a defensive copy of the registered instrument definition.
        """
        if symbol not in self._instruments:
            return None
        return copy.deepcopy(self._instruments[symbol])

    def contains(self, symbol: str) -> bool:
        """
        Checks if the symbol is registered.
        """
        return symbol in self._instruments

    def all(self) -> List[Dict[str, Any]]:
        """
        Returns defensive copies of all registered instruments.
        """
        return [copy.deepcopy(inst) for inst in self._instruments.values()]

    def targets(self) -> List[Dict[str, Any]]:
        """
        Returns defensive copies of target instruments.
        """
        return [copy.deepcopy(inst) for inst in self._instruments.values() if inst["role"] == "TARGET"]

    def drivers(self) -> List[Dict[str, Any]]:
        """
        Returns defensive copies of driver instruments.
        """
        return [copy.deepcopy(inst) for inst in self._instruments.values() if inst["role"] == "DRIVER"]

    def required_drivers(self) -> List[Dict[str, Any]]:
        """
        Returns defensive copies of required driver instruments.
        """
        return [copy.deepcopy(inst) for inst in self._instruments.values() if inst["role"] == "DRIVER" and inst["is_required"]]
