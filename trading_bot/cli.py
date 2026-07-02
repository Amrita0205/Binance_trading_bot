#!/usr/bin/env python3
"""CLI entry point -- place orders on Binance Futures Testnet from the terminal.

Examples
--------
  python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01
  python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.01 --price 60000
  python cli.py --symbol BTCUSDT --side BUY --type STOP_LIMIT \\
      --quantity 0.01 --price 61000 --stop-price 60900
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from Binance_trading_bot.trading_bot.bot.client import BinanceClient
from Binance_trading_bot.trading_bot.bot.exceptions import ConfigurationError, OrderExecutionError, TradingBotError, ValidationError
from Binance_trading_bot.trading_bot.bot.logging_config import setup_logger
from Binance_trading_bot.trading_bot.bot.orders import place_order
from Binance_trading_bot.trading_bot.bot.validators import validate_order_inputs

logger = setup_logger("trading_bot.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading-bot",
        description="Place MARKET, LIMIT, or STOP_LIMIT orders on Binance USDT-M Futures Testnet.",
    )
    parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT")
    parser.add_argument("--side", required=True, help="BUY or SELL")
    parser.add_argument("--type", dest="order_type", required=True, help="MARKET, LIMIT, or STOP_LIMIT")
    parser.add_argument("--quantity", required=True, help="Order quantity, e.g. 0.01")
    parser.add_argument("--price", default=None, help="Required for LIMIT and STOP_LIMIT orders")
    parser.add_argument("--stop-price", dest="stop_price", default=None, help="Required for STOP_LIMIT orders")
    return parser


def print_request_box(request) -> None:
    print("\n── Order Request " + "─" * 27)
    print(f"  Symbol      : {request.symbol}")
    print(f"  Side        : {request.side}")
    print(f"  Type        : {request.order_type}")
    print(f"  Quantity    : {request.quantity}")
    if request.price is not None:
        print(f"  Price       : {request.price}")
    if request.stop_price is not None:
        print(f"  Stop Price  : {request.stop_price}")


def print_response_box(response: dict) -> None:
    print("── Order Response " + "─" * 26)
    print(f"  Order ID    : {response.get('orderId')}")
    print(f"  Status      : {response.get('status')}")
    print(f"  Executed Qty: {response.get('executedQty')}")
    avg_price = response.get("avgPrice")
    if avg_price not in (None, "", "0", "0.00", "0.00000000"):
        print(f"  Avg Price   : {avg_price}")
    print()


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()

    logger.info("Starting trading bot CLI with args: %s", vars(args))

    try:
        validated = validate_order_inputs(
            symbol=args.symbol,
            side=args.side,
            order_type=args.order_type,
            quantity=args.quantity,
            price=args.price,
            stop_price=args.stop_price,
        )
    except ValidationError as e:
        logger.error("Validation failed: %s", e)
        print(f"\n❌ Validation error: {e}\n")
        return 1

    print_request_box(validated)

    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")

    try:
        client = BinanceClient(api_key, api_secret)
    except ConfigurationError as e:
        logger.error("Configuration error: %s", e)
        print(f"\n❌ Configuration error: {e}\n")
        return 1

    try:
        response = place_order(client, validated)
    except OrderExecutionError as e:
        logger.error("Order failed: %s", e)
        print(f"\n❌ Order failed: {e}\n")
        return 1
    except TradingBotError as e:
        logger.error("Unexpected trading bot error: %s", e)
        print(f"\n❌ {e}\n")
        return 1
    except Exception as e:  # last-resort guard so the CLI never dumps a raw traceback
        logger.exception("Unhandled exception while placing order")
        print(f"\n❌ Unexpected error: {e}\n")
        return 1

    print_response_box(response)
    print(f"✅ {validated.order_type} {validated.side} order placed for {validated.symbol} (orderId={response.get('orderId')})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
