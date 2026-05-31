from dotenv import load_dotenv
import os

from dhanhq import DhanContext, dhanhq


class DhanConnector:

    def __init__(self):

        load_dotenv(".env")

        context = DhanContext(
            os.getenv("DHAN_CLIENT_ID"),
            os.getenv("DHAN_ACCESS_TOKEN")
        )

        self.dhan = dhanhq(context)

    def get_fund_limits(self):

        return self.dhan.get_fund_limits()

    def get_quote(self, exchange, security_id):

        securities = {
            exchange: [security_id]
        }

        return self.dhan.quote_data(securities)
    def get_last_price(self, exchange, security_id):

        response = self.get_quote(exchange, security_id)

        quote = response["data"]["data"][exchange][str(security_id)]

        return {
            "exchange": exchange,
            "security_id": security_id,
            "last_price": quote["last_price"],
            "volume": quote["volume"],
            "timestamp": quote["last_trade_time"]
        }
