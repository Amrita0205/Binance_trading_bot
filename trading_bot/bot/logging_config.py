"""Centralised logging setup shared by cli.py and app.py.

Two handlers:
  - RotatingFileHandler -> logs/trading_bot.log, DEBUG and above
    (every request, response, and error - the audit trail the
    assignment asks for), 2MB per file, 5 backups kept.
  - StreamHandler -> console, INFO and above, for a human watching
    the terminal.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "trading_bot.log")


def setup_logger(name: str = "trading_bot") -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger  # already configured, avoids duplicate handlers on re-import

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
