from dotenv import load_dotenv
import os

load_dotenv(".env")

print("CLIENT ID FOUND:", bool(os.getenv("DHAN_CLIENT_ID")))
print("ACCESS TOKEN FOUND:", bool(os.getenv("DHAN_ACCESS_TOKEN")))

try:
    from dhanhq import dhanhq
    print("DHAN SDK IMPORT: OK")
except Exception as e:
    print("DHAN SDK IMPORT FAILED:", e)