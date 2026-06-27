import time
import ast
from datetime import datetime, timezone

class DhanLiveQuoteSource:
    """
    Interface for live quote updates from Dhan. Currently implements POLL mode
    via the DhanConnector batch quotes API with rich, sanitized diagnostics.
    """
    def __init__(self, connector, quote_buffer, poll_interval_seconds=1.0):
        self.connector = connector
        self.quote_buffer = quote_buffer
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.instruments = []
        self._running = False
        
        # Diagnostics
        self.sanitized_errors = []
        self.api_errors_by_code = {}
        self.api_errors_by_type = {}
        self.last_api_error = None

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

    def _record_api_error(self, e, exchange, requested_security_count):
        occurred_at = datetime.now(timezone.utc).isoformat()
        err_type = type(e).__name__
        
        status = "error"
        error_code = "UNKNOWN"
        error_message = str(e)
        classification = "unexpected_response_structure"
        
        if isinstance(e, ValueError) and "Invalid Dhan batch quote response" in error_message:
            try:
                start_idx = error_message.find("{")
                if start_idx != -1:
                    resp_dict_str = error_message[start_idx:]
                    resp = ast.literal_eval(resp_dict_str)
                    status = resp.get("status", "failure")
                    
                    remarks = resp.get("remarks", {})
                    if isinstance(remarks, dict):
                        error_code = remarks.get("error_code") or "unexpected_structure"
                        error_message = remarks.get("error_message") or error_message
                    else:
                        error_code = "unexpected_structure"
                        
                    remarks_msg = str(remarks).lower()
                    if "token" in remarks_msg or "expired" in remarks_msg or "auth" in remarks_msg:
                        classification = "invalid_or_expired_token"
                    elif "subscription" in remarks_msg or "subscribe" in remarks_msg:
                        classification = "market_data_subscription_unavailable"
                    elif "rate limit" in remarks_msg or "too many requests" in remarks_msg:
                        classification = "rate_limit"
                    elif "closed" in remarks_msg or "market closed" in remarks_msg:
                        classification = "market_closed"
                    elif "instrument" in remarks_msg or "security" in remarks_msg:
                        classification = "invalid_exchange_or_instrument"
            except Exception:
                pass
        else:
            msg_lower = error_message.lower()
            if "connection" in msg_lower or "timeout" in msg_lower or "unreachable" in msg_lower or "http" in msg_lower:
                classification = "network_exception"
                error_code = "NETWORK_ERROR"
            elif "rate" in msg_lower:
                classification = "rate_limit"
                error_code = "RATE_LIMIT"
            elif "token" in msg_lower or "auth" in msg_lower or "unauthorized" in msg_lower:
                classification = "invalid_or_expired_token"
                error_code = "AUTH_ERROR"
            else:
                classification = "unexpected_response_structure"
                error_code = "API_ERROR"

        # Sanitize credentials/tokens
        for token_word in ["token", "access_token", "secret", "auth", "authorization"]:
            if token_word in error_message.lower():
                error_message = "Redacted: API response error containing sensitive credentials"
                break
                
        sanitized_error = {
            "error_type": err_type,
            "status": status,
            "error_code": error_code,
            "error_message": error_message,
            "exchange": exchange,
            "requested_security_count": requested_security_count,
            "occurred_at": occurred_at,
            "classification": classification
        }
        
        self.last_api_error = sanitized_error
        self.sanitized_errors.append(sanitized_error)
        
        code_key = str(error_code)
        self.api_errors_by_code[code_key] = self.api_errors_by_code.get(code_key, 0) + 1
        
        type_key = str(err_type)
        self.api_errors_by_type[type_key] = self.api_errors_by_type.get(type_key, 0) + 1
        
        return sanitized_error

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
                    self._record_api_error(e, exchange, len(sec_ids))
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
            "api_errors_by_code": self.api_errors_by_code,
            "api_errors_by_type": self.api_errors_by_type,
            "last_api_error": self.last_api_error,
            "sanitized_errors": self.sanitized_errors,
            "buffer_snapshot": self.quote_buffer.snapshot()
        }
