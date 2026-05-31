from dotenv import load_dotenv
import os
import inspect

from dhanhq import DhanContext, dhanhq

load_dotenv(".env")

context = DhanContext(
    os.getenv("DHAN_CLIENT_ID"),
    os.getenv("DHAN_ACCESS_TOKEN")
)

dhan = dhanhq(context)

print("FETCH SECURITY LIST DOC")
print(dhan.fetch_security_list.__doc__)

print("\nFETCH SECURITY LIST SIGNATURE")
print(inspect.signature(dhan.fetch_security_list))
