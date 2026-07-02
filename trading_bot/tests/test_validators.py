"""Unit tests for input validation -- no network required.

Run with:
    python -m unittest discover tests -v
or:
    python -m pytest tests/ -v
"""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from Binance_trading_bot.trading_bot.bot.exceptions import ValidationError
from Binance_trading_bot.trading_bot.bot.validators import (
    validate_order_inputs,
    validate_quantity,
    validate_side,
    validate_symbol,
)


class TestFieldValidators(unittest.TestCase):
    """Smallest-unit tests for each individual field validator."""

    def test_symbol_uppercases_and_strips(self):
        self.assertEqual(validate_symbol(" btcusdt "), "BTCUSDT")

    def test_symbol_rejects_unsupported(self):
        with self.assertRaises(ValidationError):
            validate_symbol("DOGEUSDT")

    def test_side_uppercases(self):
        self.assertEqual(validate_side("buy"), "BUY")

    def test_side_rejects_invalid(self):
        with self.assertRaises(ValidationError):
            validate_side("HOLD")

    def test_quantity_returns_decimal(self):
        self.assertEqual(validate_quantity("0.01"), Decimal("0.01"))

    def test_quantity_rejects_zero(self):
        with self.assertRaises(ValidationError):
            validate_quantity("0")

    def test_quantity_rejects_negative(self):
        with self.assertRaises(ValidationError):
            validate_quantity("-1")

    def test_quantity_rejects_non_numeric(self):
        with self.assertRaises(ValidationError):
            validate_quantity("abc")


class TestOrderInputs(unittest.TestCase):
    """End-to-end validate_order_inputs() cases, covering all three order types."""

    def test_valid_market_order(self):
        r = validate_order_inputs(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity="0.01")
        self.assertEqual(r.order_type, "MARKET")
        self.assertIsNone(r.price)

    def test_valid_limit_order(self):
        r = validate_order_inputs(symbol="BTCUSDT", side="SELL", order_type="LIMIT", quantity="0.01", price="60000")
        self.assertEqual(r.price, Decimal("60000"))

    def test_valid_stop_limit_order(self):
        r = validate_order_inputs(
            symbol="BTCUSDT", side="BUY", order_type="STOP_LIMIT",
            quantity="0.01", price="61000", stop_price="60900",
        )
        self.assertEqual(r.stop_price, Decimal("60900"))

    def test_limit_missing_price_raises(self):
        with self.assertRaises(ValidationError):
            validate_order_inputs(symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity="0.01")

    def test_stop_limit_missing_stop_price_raises(self):
        with self.assertRaises(ValidationError):
            validate_order_inputs(
                symbol="BTCUSDT", side="BUY", order_type="STOP_LIMIT",
                quantity="0.01", price="61000",
            )

    def test_market_order_with_stray_price_raises(self):
        with self.assertRaises(ValidationError):
            validate_order_inputs(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity="0.01", price="100")

    def test_invalid_order_type_raises(self):
        with self.assertRaises(ValidationError):
            validate_order_inputs(symbol="BTCUSDT", side="BUY", order_type="ICEBERG", quantity="0.01")


if __name__ == "__main__":
    unittest.main(verbosity=2)
