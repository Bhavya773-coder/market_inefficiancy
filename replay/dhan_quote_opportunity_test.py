from connectors.dhan_connector import DhanConnector
from ai.opportunity import Opportunity

connector = DhanConnector()

quote = connector.get_last_price(
    "NSE_EQ",
    10576
)

opportunity = Opportunity(
    asset="NIFTYBEES",
    source="dhan_connector",
    opportunity_type="live_market_quote",
    score=0.0,
    confidence=1.0,
    metadata=quote
)

print(opportunity.to_dict())
