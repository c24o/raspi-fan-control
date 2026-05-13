"""Centralized logging configuration.

Outputs to stdout for clean journald/systemd integration.
Configurable log level via the daemon configuration.
"""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger for the daemon.

    Uses a simple format compatible with journald — no timestamps, since
    journald adds its own.  When running interactively the timestamp is
    still useful, but keeping the format uniform avoids duplicate fields
    in journal output.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="%(levelname)s [%(name)s] %(message)s",
    ))

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Avoid duplicate handlers on repeated calls.
    root.handlers.clear()
    root.addHandler(handler)
