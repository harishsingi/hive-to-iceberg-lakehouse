"""Logging setup for the package.

One place configures the format and level so every module logs the same
way. Modules obtain a logger with ``logging.getLogger(__name__)`` and never
call ``print`` for operational output.
"""

from __future__ import annotations

import logging
import sys

DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure the root logger once and return the package logger.

    Safe to call repeatedly: handlers are only added the first time.
    ``level`` accepts any standard logging level name (``"DEBUG"``,
    ``"INFO"``, ``"WARNING"``, ...); an unknown name raises ``ValueError``.
    """
    numeric = getattr(logging, level.upper(), None)
    if not isinstance(numeric, int):
        raise ValueError(f"unknown log level: {level!r}")
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
        root.addHandler(handler)
    root.setLevel(numeric)
    return logging.getLogger("hive_to_iceberg")
