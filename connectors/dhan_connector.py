import logging
import os
import time

from dotenv import load_dotenv

from dhanhq import DhanContext, dhanhq

logger = logging.getLogger("connectors.dhan")


class DhanConnectorError(Exception):
    """Raised when the Dhan API cannot produce a usable response."""


class DhanConnector:
    """
    Thin, hardened wrapper around the dhanhq REST client.

    Hardening over the raw client:
    - Retries transient failures (network errors, rate limits) with
      exponential backoff. Auth failures and malformed responses are NOT
      retried — they need human or upstream attention, not repetition.
    - Minimum spacing between requests to respect Dhan data-API rate limits.
    - Structured logging instead of prints; error text never includes
      credentials.
    - Optional client injection for offline testing.

    Public method signatures and return shapes are unchanged from the
    original connector. `get_standard_quotes` additionally exposes the
    project-standard connector shape defined in docs/NEXT_BUILD.md.

    This connector is read-only market data + account info. It must never
    gain order-placement methods; execution stays in PaperTradingAccount.
    """

    def __init__(
        self,
        dhan_client=None,
        max_retries=3,
        backoff_base_seconds=0.5,
        min_request_interval_seconds=0.35,
        sleep_fn=time.sleep
    ):
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if backoff_base_seconds < 0:
            raise ValueError("backoff_base_seconds must be >= 0")
        if min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds must be >= 0")

        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.min_request_interval_seconds = min_request_interval_seconds
        self._sleep = sleep_fn
        self._last_request_monotonic = None

        if dhan_client is not None:
            self.dhan = dhan_client
        else:
            self.dhan = self._build_client()

    def _build_client(self):
        load_dotenv(".env")
        client_id = os.getenv("DHAN_CLIENT_ID")
        access_token = os.getenv("DHAN_ACCESS_TOKEN")

        if not client_id or not access_token:
            raise DhanConnectorError(
                "DHAN_CLIENT_ID or DHAN_ACCESS_TOKEN missing from environment/.env"
            )

        context = DhanContext(client_id, access_token)
        logger.info("Dhan client initialized for client_id ending ...%s", client_id[-3:])
        return dhanhq(context)

    def reconnect(self):
        """
        Rebuilds the underlying dhanhq client from current environment
        credentials. Call after refreshing the access token.
        """
        self.dhan = self._build_client()
        logger.info("Dhan client reconnected")

    # ------------------------------------------------------------------
    # Transport with retry/backoff
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_failure(response):
        """
        Classifies a Dhan failure-response dict. Returns one of:
        'rate_limit', 'auth', 'market_or_input', 'unknown'.
        """
        remarks = response.get("remarks")
        text = str(remarks).lower() if remarks is not None else ""
        if "rate" in text or "too many" in text or "805" in text:
            return "rate_limit"
        if "token" in text or "auth" in text or "expired" in text or "unauthoriz" in text:
            return "auth"
        if "instrument" in text or "security" in text or "market" in text:
            return "market_or_input"
        return "unknown"

    def _respect_rate_limit(self):
        if self._last_request_monotonic is None:
            return
        elapsed = time.monotonic() - self._last_request_monotonic
        remaining = self.min_request_interval_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)

    def _call_with_retries(self, description, fn):
        """
        Calls fn() with rate-limit spacing and retries.

        Retried: raised exceptions (network/transport) and responses
        classified as rate_limit or unknown failures.
        Not retried: auth failures, input failures.
        """
        last_error = None
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                delay = self.backoff_base_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "%s: retry %d/%d after %.2fs (%s)",
                    description, attempt, self.max_retries, delay, last_error
                )
                self._sleep(delay)

            self._respect_rate_limit()
            try:
                response = fn()
                self._last_request_monotonic = time.monotonic()
            except Exception as e:  # dhanhq raises assorted transport errors
                self._last_request_monotonic = time.monotonic()
                last_error = f"transport_error: {type(e).__name__}"
                logger.warning("%s: transport error: %s", description, type(e).__name__)
                continue

            if isinstance(response, dict) and response.get("status") == "failure":
                classification = self._classify_failure(response)
                if classification == "auth":
                    logger.error("%s: authentication failure — token invalid or expired", description)
                    raise DhanConnectorError(
                        f"{description}: Dhan authentication failure "
                        "(token invalid or expired); not retrying"
                    )
                if classification == "market_or_input":
                    logger.error("%s: input/market failure: %s", description, response.get("remarks"))
                    return response  # caller's validation reports it
                last_error = f"api_failure: {classification}"
                logger.warning("%s: API failure (%s)", description, classification)
                continue

            return response

        raise DhanConnectorError(
            f"{description}: failed after {self.max_retries + 1} attempts ({last_error})"
        )

    # ------------------------------------------------------------------
    # Original public interface (shapes preserved)
    # ------------------------------------------------------------------

    def get_fund_limits(self):
        return self._call_with_retries(
            "get_fund_limits", lambda: self.dhan.get_fund_limits()
        )

    def get_quote(self, exchange, security_id):
        securities = {
            exchange: [security_id]
        }
        return self._call_with_retries(
            f"get_quote({exchange}:{security_id})",
            lambda: self.dhan.quote_data(securities)
        )

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
        response = self._call_with_retries(
            f"get_last_prices({exchange} x{len(security_ids)})",
            lambda: self.dhan.quote_data(securities)
        )

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

    # ------------------------------------------------------------------
    # Project-standard connector shape (docs/NEXT_BUILD.md)
    # ------------------------------------------------------------------

    @staticmethod
    def _top_of_book(quote):
        """
        Extracts (bid, ask, bid_qty, ask_qty) from a Dhan quote's depth
        block. Returns Nones where depth is absent — callers must treat
        bid/ask as optional.
        """
        depth = quote.get("depth")
        if not isinstance(depth, dict):
            return None, None, None, None

        def best(side):
            levels = depth.get(side)
            if isinstance(levels, list) and levels and isinstance(levels[0], dict):
                price = levels[0].get("price")
                quantity = levels[0].get("quantity")
                if isinstance(price, (int, float)) and price > 0:
                    return price, quantity if isinstance(quantity, (int, float)) else None
            return None, None

        bid, bid_qty = best("buy")
        ask, ask_qty = best("sell")
        return bid, ask, bid_qty, ask_qty

    def get_standard_quotes(self, exchange, security_ids, symbol_map=None):
        """
        Returns quotes in the project-standard connector shape from
        docs/NEXT_BUILD.md:

            source / asset / bid / ask / last_price / currency /
            timestamp / liquidity_score

        - asset is symbol_map[security_id] when provided, else
          "<exchange>:<security_id>".
        - bid/ask are None when Dhan returns no depth for the instrument.
        - liquidity_score is a bounded 0..1 proxy from top-of-book depth
          balance and spread tightness; 0.0 when depth is unavailable.
        """
        securities = {exchange: security_ids}
        response = self._call_with_retries(
            f"get_standard_quotes({exchange} x{len(security_ids)})",
            lambda: self.dhan.quote_data(securities)
        )

        if (
            not isinstance(response, dict)
            or response.get("status") != "success"
            or not isinstance(response.get("data"), dict)
            or not isinstance(response["data"].get("data"), dict)
            or not isinstance(response["data"]["data"].get(exchange), dict)
        ):
            raise ValueError(f"Invalid Dhan batch quote response: {response}")

        exchange_data = response["data"]["data"][exchange]
        standard_quotes = []
        errors = []

        for security_id in security_ids:
            quote = exchange_data.get(str(security_id))
            if not isinstance(quote, dict) or "last_price" not in quote:
                errors.append({
                    "security_id": security_id,
                    "error": "missing or invalid quote in response"
                })
                continue

            bid, ask, bid_qty, ask_qty = self._top_of_book(quote)

            last_price = quote["last_price"]
            liquidity_score = 0.0
            if bid is not None and ask is not None and ask >= bid > 0:
                mid = (bid + ask) / 2.0
                spread_pct = ((ask - bid) / mid) * 100.0 if mid > 0 else 100.0
                # Tight spread -> near 1.0; 1% spread -> 0.5. Depth balance
                # softens the score when one side is empty.
                tightness = 1.0 / (1.0 + spread_pct)
                if bid_qty and ask_qty:
                    balance = min(bid_qty, ask_qty) / max(bid_qty, ask_qty)
                else:
                    balance = 0.5
                liquidity_score = tightness * (0.5 + 0.5 * balance)

            asset = None
            if symbol_map:
                asset = symbol_map.get(security_id) or symbol_map.get(str(security_id))
            if not asset:
                asset = f"{exchange}:{security_id}"

            standard_quotes.append({
                "source": "dhan",
                "asset": asset,
                "bid": bid,
                "ask": ask,
                "last_price": last_price,
                "currency": "INR",
                "timestamp": quote.get("last_trade_time"),
                "liquidity_score": liquidity_score
            })

        if not standard_quotes:
            raise ValueError(f"No usable quotes in Dhan response: {response}")

        return {
            "status": "success",
            "quotes": standard_quotes,
            "errors": errors
        }
