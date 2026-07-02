"""Input validation, independent of the exchange and of any specific
front end (CLI or Flask), so both can share identical rules and this
module can be unit-tested with zero network access.

Quantity and price use Decimal, not float. Floats introduce silent
rounding error in financial values (e.g. 0.1 + 0.2 != 0.3) -- Decimal
keeps validation and the numbers we hand to the API exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from Binance_trading_bot.trading_bot.bot.exceptions import ValidationError

VALID_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
VALID_SIDES = ["BUY", "SELL"]
VALID_ORDER_TYPES = ["MARKET", "LIMIT", "STOP_LIMIT"]


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """Validated, immutable representation of an order request."""

    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None

    def summary(self) -> str:
        parts = [
            f"symbol={self.symbol}",
            f"side={self.side}",
            f"type={self.order_type}",
            f"quantity={self.quantity}",
        ]
        if self.price is not None:
            parts.append(f"price={self.price}")
        if self.stop_price is not None:
            parts.append(f"stop_price={self.stop_price}")
        return ", ".join(parts)


def validate_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if s not in VALID_SYMBOLS:
        raise ValidationError(f"Invalid symbol '{s}'. Valid options: {', '.join(VALID_SYMBOLS)}")
    return s


def validate_side(side: str) -> str:
    s = (side or "").strip().upper()
    if s not in VALID_SIDES:
        raise ValidationError(f"Side must be BUY or SELL, got '{side}'")
    return s


def validate_order_type(order_type: str) -> str:
    t = (order_type or "").strip().upper()
    if t not in VALID_ORDER_TYPES:
        raise ValidationError(
            f"Order type must be one of {VALID_ORDER_TYPES}, got '{order_type}'"
        )
    return t


def _to_decimal(value, field_name: str) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValidationError(f"{field_name} must be a number, got '{value}'")
    if d <= 0:
        raise ValidationError(f"{field_name} must be greater than 0, got {d}")
    return d


def validate_quantity(quantity) -> Decimal:
    return _to_decimal(quantity, "Quantity")


def validate_price(price, field_name: str = "Price") -> Decimal:
    return _to_decimal(price, field_name)


def validate_order_inputs(
    symbol: str,
    side: str,
    order_type: str,
    quantity,
    price=None,
    stop_price=None,
) -> OrderRequest:
    """Validate raw input (strings or numbers, as they arrive from
    either argparse or a JSON request body) and return an OrderRequest.
    Fails on the first bad field with a specific message, and raises
    ValidationError -- never lets a bad request reach the network.
    """
    v_symbol = validate_symbol(symbol)
    v_side = validate_side(side)
    v_type = validate_order_type(order_type)
    v_quantity = validate_quantity(quantity)

    v_price = None
    v_stop_price = None

    if v_type == "LIMIT":
        if not price:
            raise ValidationError("Price is required for LIMIT orders")
        v_price = validate_price(price)
        if stop_price:
            raise ValidationError("stop_price should not be provided for LIMIT orders")

    elif v_type == "STOP_LIMIT":
        if not price:
            raise ValidationError("Price is required for STOP_LIMIT orders")
        if not stop_price:
            raise ValidationError("stop_price is required for STOP_LIMIT orders")
        v_price = validate_price(price)
        v_stop_price = validate_price(stop_price, field_name="Stop price")

    else:  # MARKET
        if price:
            raise ValidationError("Price should not be provided for MARKET orders")
        if stop_price:
            raise ValidationError("stop_price should not be provided for MARKET orders")

    return OrderRequest(
        symbol=v_symbol,
        side=v_side,
        order_type=v_type,
        quantity=v_quantity,
        price=v_price,
        stop_price=v_stop_price,
    )
