class SteelCommodityInstrumentRegistry:
    def __init__(self):
        self.instruments = [
            {
                "symbol": "STEEL_PHYSICAL_PLATE",
                "name": "Physical Steel Plate",
                "category": "steel",
                "role": "delivery_asset",
                "market": "physical_india",
                "data_source": "supplier_quotes",
                "priority": 1,
                "delivery_relevance": True,
                "notes": "Used for physical deliveries of plates up to 400 tons"
            },
            {
                "symbol": "STEEL_PHYSICAL_ANGLE",
                "name": "Physical Steel Angle",
                "category": "steel",
                "role": "delivery_asset",
                "market": "physical_india",
                "data_source": "supplier_quotes",
                "priority": 1,
                "delivery_relevance": True,
                "notes": "Used for physical deliveries of angles up to 400 tons"
            },
            {
                "symbol": "STEEL_FUTURE",
                "name": "Steel Futures",
                "category": "steel",
                "role": "primary_trade",
                "market": "exchange",
                "data_source": "futures_feed",
                "priority": 1,
                "delivery_relevance": True,
                "notes": "Exchange-traded steel futures"
            },
            {
                "symbol": "IRON_ORE",
                "name": "Iron Ore",
                "category": "iron_ore",
                "role": "cost_driver",
                "market": "global",
                "data_source": "commodity_feed",
                "priority": 1,
                "delivery_relevance": False,
                "notes": "Primary raw material for steel production"
            },
            {
                "symbol": "COKING_COAL",
                "name": "Coking Coal",
                "category": "coal",
                "role": "cost_driver",
                "market": "global",
                "data_source": "commodity_feed",
                "priority": 1,
                "delivery_relevance": False,
                "notes": "Key energy source and reducing agent"
            },
            {
                "symbol": "SCRAP_STEEL",
                "name": "Scrap Steel",
                "category": "scrap",
                "role": "cost_driver",
                "market": "physical_india",
                "data_source": "supplier_quotes",
                "priority": 2,
                "delivery_relevance": True,
                "notes": "Recycled steel source for electric arc furnaces"
            },
            {
                "symbol": "BALTIC_DRY",
                "name": "Baltic Dry Index",
                "category": "freight",
                "role": "early_warning",
                "market": "global",
                "data_source": "freight_index",
                "priority": 1,
                "delivery_relevance": False,
                "notes": "Global dry bulk shipping cost indicator"
            },
            {
                "symbol": "CRUDE_OIL",
                "name": "Crude Oil",
                "category": "fuel",
                "role": "cost_driver",
                "market": "global",
                "data_source": "commodity_feed",
                "priority": 1,
                "delivery_relevance": False,
                "notes": "Fuel cost driver affecting logistics"
            },
            {
                "symbol": "USDINR",
                "name": "USD INR",
                "category": "currency",
                "role": "macro_filter",
                "market": "fx",
                "data_source": "fx_feed",
                "priority": 1,
                "delivery_relevance": False,
                "notes": "Exchange rate impact on import/export parity"
            },
            {
                "symbol": "GOLD",
                "name": "Gold",
                "category": "gold",
                "role": "hedge",
                "market": "commodity",
                "data_source": "commodity_feed",
                "priority": 1,
                "delivery_relevance": True,
                "notes": "Capital parking asset when predictability is low"
            },
            {
                "symbol": "NIFTY_METAL",
                "name": "Nifty Metal Index",
                "category": "index",
                "role": "early_warning",
                "market": "NSE",
                "data_source": "dhan",
                "priority": 1,
                "delivery_relevance": False,
                "notes": "Indian metal sector index"
            },
            {
                "symbol": "TATASTEEL",
                "name": "Tata Steel",
                "category": "equity",
                "role": "early_warning",
                "market": "NSE",
                "data_source": "dhan",
                "priority": 2,
                "delivery_relevance": False,
                "notes": "Major steel producer equity"
            },
            {
                "symbol": "JSWSTEEL",
                "name": "JSW Steel",
                "category": "equity",
                "role": "early_warning",
                "market": "NSE",
                "data_source": "dhan",
                "priority": 2,
                "delivery_relevance": False,
                "notes": "Major steel producer equity"
            },
            {
                "symbol": "SAIL",
                "name": "Steel Authority of India",
                "category": "equity",
                "role": "early_warning",
                "market": "NSE",
                "data_source": "dhan",
                "priority": 2,
                "delivery_relevance": False,
                "notes": "State-owned steel producer equity"
            },
            {
                "symbol": "JINDALSTEL",
                "name": "Jindal Steel",
                "category": "equity",
                "role": "early_warning",
                "market": "NSE",
                "data_source": "dhan",
                "priority": 2,
                "delivery_relevance": False,
                "notes": "Private steel producer equity"
            }
        ]

    def all(self):
        return self.instruments

    def by_category(self, category):
        return [inst for inst in self.instruments if inst["category"] == category]

    def by_role(self, role):
        return [inst for inst in self.instruments if inst["role"] == role]

    def priority_universe(self, max_priority=1):
        return [inst for inst in self.instruments if inst["priority"] <= max_priority]

    def delivery_relevant(self):
        return [inst for inst in self.instruments if inst["delivery_relevance"] is True]
