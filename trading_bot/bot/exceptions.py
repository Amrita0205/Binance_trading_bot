"""Custom exception hierarchy.

ValidationError also inherits from ValueError so it can be caught
either specifically (`except ValidationError`) or generically by code
that only knows about standard input-validation errors.
"""

from __future__ import annotations


class TradingBotError(Exception):
    """Base class for all errors raised intentionally by this bot."""


class ValidationError(TradingBotError, ValueError):
    """Raised when input fails validation before any network call is
    made. Kept separate from OrderExecutionError so callers can react
    fast (no need to touch the exchange) and give a precise message."""


class ConfigurationError(TradingBotError):
    """Raised when required configuration (e.g. API credentials) is
    missing or malformed."""


class OrderExecutionError(TradingBotError):
    """Raised when the exchange rejects a request, or it could not be
    completed after retries. Wraps the underlying exception/response
    so the original detail is not lost."""

    def __init__(self, message: str, original_exception: Exception | None = None):
        super().__init__(message)
        self.original_exception = original_exception
