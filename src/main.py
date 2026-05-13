"""Entry point for the raspi-fan-control daemon.

Handles argument parsing, signal setup, and graceful lifecycle management.
Designed to be invoked directly or via systemd.
"""

from __future__ import annotations

import argparse
import signal
import sys
import logging

from .config import load_config
from .controller import FanController
from .logger import setup_logging

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="raspifanctl",
        description="Raspberry Pi PWM fan controller daemon",
    )
    parser.add_argument(
        "-c", "--config",
        metavar="PATH",
        default=None,
        help="Path to YAML configuration file (default: /etc/raspifanctl/config.yaml)",
    )
    return parser.parse_args()


def main() -> None:
    """Daemon entry point."""
    args = _parse_args()

    # Bootstrap logging early with a sensible default; the level will be
    # reconfigured once the full config is loaded.
    setup_logging("INFO")

    try:
        config = load_config(args.config)
    except (ValueError, OSError) as exc:
        logger.critical("Configuration error: %s", exc)
        sys.exit(1)

    # Reconfigure logging with the level from the loaded config.
    setup_logging(config.log_level)

    logger.info("Configuration loaded: poll_interval=%ds, hysteresis=%d°C, "
                "pwm_frequency=%dHz, gpio=GPIO%d, smoothing_window=%d",
                config.poll_interval, config.hysteresis, config.pwm_frequency,
                config.gpio_pin, config.smoothing_window)

    controller = FanController(config)

    # Wire up signal handlers for graceful shutdown.
    def _handle_signal(signum: int, _frame: object) -> None:
        sig_name = signal.Signals(signum).name
        logger.info("Received %s — initiating shutdown", sig_name)
        controller.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        controller.start()
    except Exception:
        logger.critical("Fatal error — fan set to 100%% (fail-safe)", exc_info=True)
        sys.exit(1)

    logger.info("Fan controller shut down cleanly")


if __name__ == "__main__":
    main()
