from dataclasses import dataclass

@dataclass(frozen=True)
class CommodityFeatureProfile:
    """
    Immutable configuration profiling a specific commodity's targets,
    driver sources, and code mappings.
    """
    commodity: str
    commodity_code: int
    target_codes: dict
    driver_sources: tuple
    status_codes: dict
    outcome_codes: dict
    feature_schema_version: str

    def __post_init__(self):
        if not isinstance(self.commodity, str) or not self.commodity.strip() or not self.commodity.isupper():
            raise ValueError("commodity must be a non-empty uppercase string")
            
        if type(self.commodity_code) is bool or not isinstance(self.commodity_code, int):
            raise TypeError("commodity_code must be an integer and not bool")
            
        if not isinstance(self.target_codes, dict) or not self.target_codes:
            raise ValueError("target_codes must be a non-empty dictionary")
        for k, v in self.target_codes.items():
            if not isinstance(k, str) or not k.strip():
                raise ValueError("target_codes keys must be non-empty strings")
            if type(v) is bool or not isinstance(v, int):
                raise TypeError("target_codes values must be integers and not bool")
                
        if not isinstance(self.driver_sources, tuple) or not self.driver_sources:
            raise ValueError("driver_sources must be a non-empty tuple")
        seen_drivers = set()
        for d in self.driver_sources:
            if not isinstance(d, str) or not d.strip() or not d.isupper():
                raise ValueError("driver name must be a non-empty uppercase string")
            if d in seen_drivers:
                raise ValueError(f"Duplicate driver name found: {d}")
            seen_drivers.add(d)
            
        if not isinstance(self.status_codes, dict) or not self.status_codes:
            raise ValueError("status_codes must be a non-empty dictionary")
        for k, v in self.status_codes.items():
            if not isinstance(k, str) or not k.strip():
                raise ValueError("status_codes keys must be non-empty strings")
            if type(v) is bool or not isinstance(v, int):
                raise TypeError("status_codes values must be integers and not bool")
                
        if not isinstance(self.outcome_codes, dict) or not self.outcome_codes:
            raise ValueError("outcome_codes must be a non-empty dictionary")
        for k, v in self.outcome_codes.items():
            if not isinstance(k, str) or not k.strip():
                raise ValueError("outcome_codes keys must be non-empty strings")
            if type(v) is bool or not isinstance(v, int):
                raise TypeError("outcome_codes values must be integers and not bool")
                
        if not isinstance(self.feature_schema_version, str) or not self.feature_schema_version.strip():
            raise ValueError("feature_schema_version must be a non-empty string")

# Predefined profiles
STEEL_FEATURE_PROFILE = CommodityFeatureProfile(
    commodity="STEEL",
    commodity_code=1,
    target_codes={
        "STEEL_FUTURE": 1,
        "STEEL_PHYSICAL_PLATE": 2,
        "STEEL_PHYSICAL_ANGLE": 3
    },
    driver_sources=(
        "IRON_ORE",
        "COKING_COAL",
        "SCRAP_STEEL",
        "BALTIC_DRY",
        "CRUDE_OIL",
        "USDINR",
        "NIFTY_METAL",
        "TATASTEEL",
        "JSWSTEEL",
        "GOLD"
    ),
    status_codes={
        "NON_REACTION": 1,
        "UNDERREACTION": 2,
        "DIVERGENCE": 3,
        "OVERREACTION": 4,
        "EFFICIENT": 5,
        "LOW_PRESSURE": 6,
        "LOW_COVERAGE": 7,
        "INSUFFICIENT_DATA": 8
    },
    outcome_codes={
        "CONVERGED": 1,
        "DIRECTION_REVERSED": 2,
        "SIGNAL_DECAYED": 3,
        "EXPIRED": 4,
        "MANUALLY_CLOSED": 5
    },
    feature_schema_version="1.0"
)
