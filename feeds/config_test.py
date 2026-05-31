from dotenv import load_dotenv
import os

print("===================================")
print("CONFIGURATION TEST")
print("===================================")

# Load environment variables
load_dotenv("../.env")

# Read variables
client_id = os.getenv("DHAN_CLIENT_ID")
environment = os.getenv("ENVIRONMENT")
project_name = os.getenv("PROJECT_NAME")

print(f"Project Name: {project_name}")
print(f"Environment: {environment}")
print(f"Dhan Client ID: {client_id}")

print("Configuration loaded successfully.")
