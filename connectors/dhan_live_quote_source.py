import time
from datetime import datetime, timezone

class DhanLiveQuoteSource:
    """
    Interface for live quote updates from Dhan. Currently implements POLL mode
    via the DhanConnector batch quotes API.
    """
    def __init__(self, connector, quote_buffer, poll_interval_seconds=1.0):
        self.connector = connector
        self.quote_buffer = quote_buffer
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.instruments = []
        self._running = False

    def subscribe(self, instruments):
        """
        Subscribes to a list of instrument dictionaries:
        [{"exchange": "NSE_EQ", "security_id": 10176, "symbol": "SETFNIF50"}]
        """
        self.instruments = list(instruments)

    def stop(self):
        """
        Stops the observation loop cleanly.
        """
        self._running = False

    def run_for(self, duration_seconds):
        """
        Collects quotes for the requested duration. Runs in POLL mode.
        """
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")

        self._running = True
        start_time = time.perf_counter()
        started_at = datetime.now(timezone.utc)

        api_error_count = 0
        partial_error_count = 0
        received_quote_count = 0

        # Group instruments by exchange for batch polling
        by_exchange = {}
        symbol_map = {}
        for inst in self.instruments:
            exchange = inst["exchange"]
            sec_id = int(inst["security_id"])
            symbol = inst.get("symbol", "")
            
            if exchange not in by_exchange:
                by_exchange[exchange] = []
            by_exchange[exchange].append(sec_id)
            symbol_map[(exchange, sec_id)] = symbol

        requested_instrument_count = len(self.instruments)

        while self._running:
            now_perf = time.perf_counter()
            if (now_perf - start_time) >= duration_seconds:
                break

            for exchange, sec_ids in by_exchange.items():
                if not self._running:
                    break

                received_at = datetime.now(timezone.utc)
                received_monotonic = time.perf_counter()

                try:
                    # Fetch batch quotes from DhanConnector
                    result = self.connector.get_last_prices(exchange, sec_ids)
                    
                    # Update buffer for valid quotes
                    for q in result.get("quotes", []):
                        sec_id = q["security_id"]
                        symbol = symbol_map.get((exchange, sec_id), "")
                        
                        quote_copy = q.copy()
                        quote_copy["symbol"] = symbol
                        quote_copy["data_source"] = "dhan_live"
                        
                        self.quote_buffer.update_quote(
                            quote_copy,
                            received_at=received_at,
                            received_monotonic=received_monotonic
                        )
                        received_quote_count += 1

                    # Count partial failures
                    errors = result.get("errors", [])
                    if errors:
                        partial_error_count += len(errors)

                except Exception as e:
                    print(f"DhanLiveQuoteSource API error: {e}")
                    api_error_count += 1

            time.sleep(self.poll_interval_seconds)

        self._running = False
        ended_at = datetime.now(timezone.utc)

        return {
            "mode": "POLL",
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "duration_seconds": time.perf_counter() - start_time,
            "requested_instrument_count": requested_instrument_count,
            "received_quote_count": received_quote_count,
            "api_error_count": api_error_count,
            "partial_error_count": partial_error_count,
            "buffer_snapshot": self.quote_buffer.snapshot()
        }
