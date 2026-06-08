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

        if (
            not isinstance(response, dict)
            or response.get("status") != "success"
            or "data" not in response
            or not isinstance(response["data"], dict)
            or "data" not in response["data"]
            or not isinstance(response["data"]["data"], dict)
            or exchange not in response["data"]["data"]
            or not isinstance(response["data"]["data"][exchange], dict)
            or str(security_id) not in response["data"]["data"][exchange]
        ):
            raise ValueError(f"Invalid Dhan quote response: {response}")

        quote = response["data"]["data"][exchange][str(security_id)]

        return {
            "exchange": exchange,
            "security_id": security_id,
            "last_price": quote["last_price"],
            "volume": quote["volume"],
            "timestamp": quote["last_trade_time"]
        }

    def get_last_prices(self, exchange, security_ids):
        securities = {
            exchange: security_ids
        }
        response = self.dhan.quote_data(securities)

        if (
            not isinstance(response, dict)
            or response.get("status") != "success"
            or "data" not in response
            or not isinstance(response["data"], dict)
            or "data" not in response["data"]
            or not isinstance(response["data"]["data"], dict)
            or exchange not in response["data"]["data"]
            or not isinstance(response["data"]["data"][exchange], dict)
        ):
            raise ValueError(f"Invalid Dhan batch quote response: {response}")

        quotes = []
        errors = []
        exchange_data = response["data"]["data"][exchange]

        for security_id in security_ids:
            sec_id_str = str(security_id)
            if sec_id_str in exchange_data and isinstance(exchange_data[sec_id_str], dict):
                quote = exchange_data[sec_id_str]
                if "last_price" in quote and "volume" in quote and "last_trade_time" in quote:
                    quotes.append({
                        "exchange": exchange,
                        "security_id": security_id,
                        "last_price": quote["last_price"],
                        "volume": quote["volume"],
                        "timestamp": quote["last_trade_time"]
                    })
                else:
                    errors.append({
                        "security_id": security_id,
                        "error": f"Missing required fields in quote: {quote}"
                    })
            else:
                errors.append({
                    "security_id": security_id,
                    "error": f"Security ID {security_id} missing or invalid in response data"
                })

        if not quotes:
            raise ValueError(f"Invalid Dhan batch quote response: {response}")

        return {
            "status": "success",
            "quotes": quotes,
            "errors": errors
        }


