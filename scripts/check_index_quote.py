import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from connectors.dhan_connector import DhanConnector

def main():
    connector = DhanConnector()
    
    # We want to check Nifty 50 Index (ID: 286 or check if there is another ID for NSE Index)
    # Let's try querying different exchanges/IDs
    securities = {
        "NSE_EQ": [286, 10576]
    }
    
    response = connector.dhan.quote_data(securities)
    print("Response:")
    import pprint
    pprint.pprint(response)

if __name__ == "__main__":
    main()
