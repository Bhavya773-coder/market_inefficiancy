import time
from connectors.dhan_connector import DhanConnector

class LiveDhanPairSelector:
    """
    Finds two instruments that return valid live quotes right now from Dhan.
    """
    def select_pair(self, candidates, min_required=2):
        connector = DhanConnector()
        working = []
        failed = []
        
        for candidate in candidates:
            exchange = candidate.get("exchange", "NSE_EQ")
            security_id = candidate.get("security_id")
            symbol = candidate.get("symbol")
            
            try:
                # Retrieve quote using Dhan API
                quote = connector.get_last_price(exchange, security_id)
                quote["symbol"] = symbol
                quote["mock"] = False
                quote["data_source"] = "dhan_live"
                
                working.append({
                    "config": candidate,
                    "quote": quote
                })
                
                if len(working) >= min_required:
                    break
            except Exception as e:
                failed.append({
                    "config": candidate,
                    "error": str(e)
                })
            
            # Introduce a small sleep to avoid Dhan API throttling/rate-limiting
            time.sleep(0.3)
                
        ready = len(working) >= min_required
        
        return {
            "ready": ready,
            "working": working,
            "failed": failed,
            "reference": working[0] if len(working) > 0 else None,
            "target": working[1] if len(working) > 1 else None
        }
