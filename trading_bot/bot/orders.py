"""Translates a validated OrderRequest into Binance's order params, and
logs the outcome. Keeping this mapping in one place means client.py
never has to know about our internal types, and validators.py never
has to know about Binance's parameter names (side/type/quantity/
price/stopPrice/...).
"""

from __future__ import annotations

from decimal import Decimal

from Binance_trading_bot.trading_bot.bot.client import BinanceClient
from Binance_trading_bot.trading_bot.bot.logging_config import setup_logger
from Binance_trading_bot.trading_bot.bot.validators import OrderRequest

logger = setup_logger("trading_bot.orders")


def build_order_params(
    symbol: str,
    side: str,
    order_type: str,
    quantity: Decimal,
    price: Decimal | None = None,
    stop_price: Decimal | None = None,
) -> dict:
    """Map validated order fields to Binance futures order params.
    Decimal values are converted with str(), never float() -- passing
    a Python float through urlencode() can introduce trailing
    precision noise (e.g. 0.1 -> '0.1000000000000000055...') that a
    naive implementation would silently send to the exchange.
    """
    params = {
        "symbol": symbol,
        "side": side,
        "quantity": str(quantity),
    }

    if order_type == "MARKET":
        params["type"] = "MARKET"
    elif order_type == "LIMIT":
        params["type"] = "LIMIT"
        params["price"] = str(price)
        params["timeInForce"] = "GTC"  # Good Till Cancelled
    elif order_type == "STOP_LIMIT":
        # Binance futures calls this order type STOP: it needs both a
        # trigger (stopPrice) and the limit price to fill once triggered.
        params["type"] = "STOP"
        params["price"] = str(price)
        params["stopPrice"] = str(stop_price)
        params["timeInForce"] = "GTC"
    else:
        raise ValueError(f"Unsupported order type: {order_type}")

    return params


def place_order(client: BinanceClient, request: OrderRequest) -> dict:
    """End-to-end: validated OrderRequest in, raw exchange response out."""
    params = build_order_params(
        symbol=request.symbol,
        side=request.side,
        order_type=request.order_type,
        quantity=request.quantity,
        price=request.price,
        stop_price=request.stop_price,
    )

    logger.info(
        "Placing %s %s order | symbol=%s qty=%s price=%s",
        request.side, request.order_type, request.symbol,
        request.quantity, request.price or request.stop_price or "MARKET",
    )

    response = client.place_order(params)

    logger.info(
        "Order placed | orderId=%s status=%s executedQty=%s avgPrice=%s",
        response.get("orderId"),
        response.get("status"),
        response.get("executedQty"),
        response.get("avgPrice"),
    )

    return response
