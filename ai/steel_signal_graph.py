class SteelSignalGraph:
    def __init__(self):
        self.relationships = [
            {
                "source": "IRON_ORE",
                "target": "STEEL_FUTURE",
                "relationship_type": "cost_pressure",
                "direction": "positive",
                "weight": 0.20,
                "lag_expectation": "medium",
                "notes": "Primary raw material driver for steel futures"
            },
            {
                "source": "COKING_COAL",
                "target": "STEEL_FUTURE",
                "relationship_type": "cost_pressure",
                "direction": "positive",
                "weight": 0.15,
                "lag_expectation": "medium",
                "notes": "Crucial cost component in blast furnace steelmaking"
            },
            {
                "source": "SCRAP_STEEL",
                "target": "STEEL_FUTURE",
                "relationship_type": "cost_pressure",
                "direction": "positive",
                "weight": 0.10,
                "lag_expectation": "short",
                "notes": "Fast-reacting feedstock cost driver"
            },
            {
                "source": "BALTIC_DRY",
                "target": "STEEL_PHYSICAL_PLATE",
                "relationship_type": "freight_pressure",
                "direction": "positive",
                "weight": 0.10,
                "lag_expectation": "medium",
                "notes": "Global dry bulk freight rates affect import parity of plates"
            },
            {
                "source": "CRUDE_OIL",
                "target": "STEEL_PHYSICAL_PLATE",
                "relationship_type": "freight_pressure",
                "direction": "positive",
                "weight": 0.10,
                "lag_expectation": "medium",
                "notes": "Fuel cost impacts physical transportation and logistics"
            },
            {
                "source": "USDINR",
                "target": "STEEL_PHYSICAL_PLATE",
                "relationship_type": "currency_pressure",
                "direction": "positive",
                "weight": 0.10,
                "lag_expectation": "short",
                "notes": "Exchange rate variations immediately impact import margins"
            },
            {
                "source": "NIFTY_METAL",
                "target": "STEEL_FUTURE",
                "relationship_type": "early_warning",
                "direction": "positive",
                "weight": 0.10,
                "lag_expectation": "short",
                "notes": "Sector index often leads commodity price expectations"
            },
            {
                "source": "TATASTEEL",
                "target": "STEEL_FUTURE",
                "relationship_type": "producer_sentiment",
                "direction": "positive",
                "weight": 0.05,
                "lag_expectation": "short",
                "notes": "Market capitalization and volume leader in domestic steel"
            },
            {
                "source": "JSWSTEEL",
                "target": "STEEL_FUTURE",
                "relationship_type": "producer_sentiment",
                "direction": "positive",
                "weight": 0.05,
                "lag_expectation": "short",
                "notes": "Key private sector producer sentiment benchmark"
            },
            {
                "source": "GOLD",
                "target": "STEEL_FUTURE",
                "relationship_type": "risk_hedge",
                "direction": "mixed",
                "weight": 0.05,
                "lag_expectation": "medium",
                "notes": "General risk sentiment indicator and inflation hedge"
            }
        ]

    def all(self):
        return self.relationships

    def drivers_for(self, target):
        return [r for r in self.relationships if r["target"] == target]

    def targets_for(self, source):
        return [r for r in self.relationships if r["source"] == source]

    def by_type(self, relationship_type):
        return [r for r in self.relationships if r["relationship_type"] == relationship_type]

    def weighted_drivers_for(self, target):
        drivers = self.drivers_for(target)
        return sorted(drivers, key=lambda x: x["weight"], reverse=True)
