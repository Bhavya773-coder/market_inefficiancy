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