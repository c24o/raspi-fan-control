"""Main control loop orchestrating temperature monitoring and fan speed.

Ties together all subsystems: temperature reading, curve evaluation,
PWM output, and logging.  Designed to run as a single-threaded polling
loop — simple, deterministic, and easy to reason about.
"""

from __future__ import annotations

import logging
import time

from .config import Config
from .curve import FanCurve
from .pwm import PWMController
from .temperature import TemperatureReader

logger = logging.getLogger(__name__)


class FanController:
    """Orchestrates the temperature → fan-speed control loop."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._temp_reader = TemperatureReader(smoothing_window=config.smoothing_window)
        self._pwm = PWMController(gpio_pin=config.gpio_pin, frequency=config.pwm_frequency)
        self._curve = FanCurve(curve=config.curve, hysteresis=config.hysteresis)
        self._running = False

    def start(self) -> None:
        """Initialize hardware and enter the main control loop.

        Blocks until stop() is called (typically via a signal handler).
        """
        self._pwm.initialize()
        self._running = True
        logger.info("Fan controller started (poll_interval=%ds, hysteresis=%d°C)",
                     self._config.poll_interval, self._config.hysteresis)

        try:
            self._loop()
        finally:
            self._pwm.shutdown()

    def stop(self) -> None:
        """Signal the control loop to exit after the current iteration."""
        logger.info("Fan controller stopping")
        self._running = False

    def _loop(self) -> None:
        """Core polling loop."""
        while self._running:
            try:
                self._tick()
            except Exception:
                logger.exception("Error in control loop — setting fan to 100%% (fail-safe)")
                try:
                    self._pwm.set_speed(100)
                except Exception:
                    logger.exception("Failed to set fail-safe fan speed to 100%%")

            # Use a short-step sleep so we can respond to stop() promptly
            # while still respecting the configured poll interval.
            self._interruptible_sleep(self._config.poll_interval)

    def _tick(self) -> None:
        """Single iteration: read → evaluate → apply."""
        temp = self._temp_reader.read()
        target_speed = self._curve.evaluate(temp)

        # Log critical temperature warnings.
        if temp >= self._config.critical_temp:
            logger.warning("CPU temperature %.1f°C exceeds critical threshold (%d°C)",
                           temp, self._config.critical_temp)

        # Only log when the speed actually changes to avoid log spam.
        prev_speed = getattr(self, "_last_logged_speed", None)
        if target_speed != prev_speed:
            logger.info("Temperature %.1f°C → fan speed %d%%", temp, target_speed)
            self._last_logged_speed = target_speed

        self._pwm.set_speed(target_speed)

    def _interruptible_sleep(self, seconds: int) -> None:
        """Sleep in 1-second increments so the loop can exit promptly."""
        for _ in range(seconds):
            if not self._running:
                break
            time.sleep(1)
