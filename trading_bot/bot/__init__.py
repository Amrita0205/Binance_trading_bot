"""
bot
===

Core package for the Binance USDT-M Futures Testnet trading bot.

    client.py         -> hand-signed REST client (HMAC-SHA256, no SDK)
    validators.py      -> CLI/API input -> validated OrderRequest (no network)
    orders.py           -> OrderRequest -> exchange call -> OrderResult
    logging_config.py   -> shared rotating-file + console logger
    exceptions.py        -> ValidationError / ConfigurationError / OrderExecutionError

Both `cli.py` (terminal) and `app.py` (Flask dashboard + REST API) sit on
top of this package and share it, so validation/order logic is written
and tested exactly once.
"""

__version__ = "2.0.0"
