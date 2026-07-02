"""Direct REST client for Binance USDT-M Futures Testnet -- no SDK.

Every signed request is built and signed by hand (HMAC-SHA256 over the
query string, per Binance's documented scheme) so the signing logic
is fully visible and auditable rather than hidden inside a library.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from Binance_trading_bot.trading_bot.bot.exceptions import ConfigurationError, OrderExecutionError
from Binance_trading_bot.trading_bot.bot.logging_config import setup_logger

logger = setup_logger("trading_bot.client")

BASE_URL = "https://testnet.binancefuture.com"
RECV_WINDOW = 5000  # ms -- tolerance for clock skew between this machine and Binance's server


def _build_session() -> requests.Session:
    """Session with automatic retry, scoped ONLY to transient
    infrastructure failures (5xx / connection drops) -- never to a
    rejected order. An order the exchange has already answered (bad
    symbol, insufficient margin, bad signature, ...) will not change
    its answer on retry, and retrying it just burns rate limit.
    """
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist={500, 502, 503, 504},
        allowed_methods={"GET", "POST", "DELETE"},
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


class BinanceClient:
    """Thin, hand-signed wrapper around the Futures Testnet REST API."""

    def __init__(self, api_key: str, api_secret: str):
        if not api_key or not api_secret:
            raise ConfigurationError(
                "API key and secret are required. Set BINANCE_API_KEY and "
                "BINANCE_API_SECRET (e.g. in a .env file) before running."
            )
        self._api_key = api_key
        self._api_secret = api_secret
        self.session = _build_session()
        self.session.headers.update({
            "X-MBX-APIKEY": self._api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        })
        self.time_offset = self._get_server_time_offset()

    # ---- internals -----------------------------------------------------

    def _get_server_time_offset(self) -> int:
        """Binance rejects signed requests once local and server clocks
        drift too far apart, so we measure the drift once at startup
        and correct every subsequent timestamp by it."""
        try:
            response = requests.get(f"{BASE_URL}/fapi/v1/time", timeout=5)
            server_time = response.json()["serverTime"]
        except (requests.exceptions.RequestException, KeyError, ValueError) as exc:
            logger.warning("Could not sync server time (%s); defaulting offset to 0", exc)
            return 0
        local_time = int(time.time() * 1000)
        offset = server_time - local_time
        logger.info("Server time synchronized | offset=%sms", offset)
        return offset

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000) + self.time_offset
        params["recvWindow"] = RECV_WINDOW
        query = urlencode(params)
        params["signature"] = hmac.new(
            self._api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return params

    def _request(self, method: str, path: str, params: dict | None = None, signed: bool = False) -> dict:
        params = dict(params or {})
        if signed:
            params = self._sign(params)

        url = f"{BASE_URL}{path}"
        # never log the signature itself, even to our own log file
        loggable_params = {k: v for k, v in params.items() if k != "signature"}
        logger.debug("REQUEST %s %s | params=%s", method, path, loggable_params)

        try:
            if method == "GET":
                response = self.session.get(url, params=params, timeout=10)
            elif method == "DELETE":
                response = self.session.delete(url, params=params, timeout=10)
            else:
                response = self.session.post(url, data=params, timeout=10)
        except requests.exceptions.RequestException as exc:
            logger.error("Network error on %s %s: %s", method, path, exc)
            raise OrderExecutionError(f"Network error calling {path}: {exc}", original_exception=exc)

        try:
            data = response.json()
        except ValueError as exc:
            logger.error("Non-JSON response from %s %s: %s", method, path, response.text[:200])
            raise OrderExecutionError("Received an invalid response from Binance", original_exception=exc)

        if response.status_code != 200:
            code = data.get("code")
            msg = data.get("msg", str(data))
            logger.error("API error: code=%s msg=%s | %s %s", code, msg, method, path)
            raise OrderExecutionError(f"Binance API error {code}: {msg}")

        logger.debug("RESPONSE %s %s | %s", method, path, data)
        return data

    # ---- public (unsigned) market data -----------------------------------

    def ping(self) -> dict:
        return self._request("GET", "/fapi/v1/ping")

    def get_price(self, symbol: str) -> dict:
        return self._request("GET", "/fapi/v1/ticker/price", {"symbol": symbol})

    def get_24hr_stats(self, symbol: str | None = None) -> dict | list:
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", "/fapi/v1/ticker/24hr", params)

    def get_klines(self, symbol: str, interval: str = "5m", limit: int = 24) -> list:
        return self._request(
            "GET", "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )

    # ---- signed account / trading endpoints ------------------------------

    def get_account(self) -> dict:
        return self._request("GET", "/fapi/v2/account", signed=True)

    def get_open_orders(self, symbol: str | None = None) -> list:
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", "/fapi/v1/openOrders", params, signed=True)

    def place_order(self, params: dict) -> dict:
        return self._request("POST", "/fapi/v1/order", params, signed=True)

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        return self._request(
            "DELETE", "/fapi/v1/order",
            {"symbol": symbol, "orderId": order_id}, signed=True,
        )
