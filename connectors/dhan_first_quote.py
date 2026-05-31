from dotenv import load_dotenv
import os

from dhanhq import DhanContext, dhanhq

load_dotenv(".env")

context = DhanContext(
    os.getenv("DHAN_CLIENT_ID"),
    os.getenv("DHAN_ACCESS_TOKEN")
)

dhan = dhanhq(context)

securities = {
    "NSE": [10576]
}

response = dhan.quote_data(securities)

print(response)
