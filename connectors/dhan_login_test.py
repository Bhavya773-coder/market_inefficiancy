from dotenv import load_dotenv
import os

from dhanhq import DhanContext, dhanhq

load_dotenv(".env")

client_id = os.getenv("DHAN_CLIENT_ID")
access_token = os.getenv("DHAN_ACCESS_TOKEN")

context = DhanContext(
    client_id,
    access_token
)

dhan = dhanhq(context)

print("CONNECTED TO DHAN SDK")

response = dhan.get_fund_limits()

print(response)
