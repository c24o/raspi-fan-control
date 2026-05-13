"""Hardware PWM fan control via pigpio.

Manages the GPIO PWM output for a 4-pin fan.  The fail-safe policy is to
drive the fan at 100% on any fatal error or during shutdown so the CPU is
never left without cooling.
"""

from __future__ import annotations

import logging

import pigpio

logger = logging.getLogger(__name__)

# PWM duty-cycle range used by pigpio: 0–1_000_000.
_PIGPIO_RANGE = 1_000_000


class PWMController:
    """Controls a 4-pin PWM fan via hardware PWM on a Raspberry Pi."""

    def __init__(self, gpio_pin: int, frequency: int) -> None:
        self._pin = gpio_pin
        self._frequency = frequency
        self._pi: pigpio.pi | None = None
        self._current_duty: int | None = None  # Track to avoid redundant writes

    def initialize(self) -> None:
        """Connect to the pigpio daemon and configure the PWM output."""
        self._pi = pigpio.pi()
        if not self._pi.connected:
            raise RuntimeError("Failed to connect to pigpio daemon — is pigpiod running?")

        self._pi.set_mode(self._pin, pigpio.OUTPUT)
        # Start with fan at 100% as a safe default until the controller
        # loop takes over.
        self._set_duty(100)
        logger.info("PWM initialized on GPIO%d at %d Hz", self._pin, self._frequency)

    def set_speed(self, percent: int) -> None:
        """Set fan speed as a percentage (0–100).

        Values are clamped to the valid range.  Redundant writes are skipped
        to reduce unnecessary GPIO traffic.
        """
        percent = max(0, min(100, percent))

        if percent == self._current_duty:
            return

        self._set_duty(percent)

    def shutdown(self) -> None:
        """Set fan to 100% (fail-safe) and release GPIO resources."""
        logger.info("PWM shutting down — setting fan to 100%% (fail-safe)")
        try:
            if self._pi and self._pi.connected:
                self._set_duty(100)
                self._pi.stop()
        except Exception:
            # Best-effort cleanup; nothing more we can do.
            logger.exception("Error during PWM shutdown")
        finally:
            self._pi = None
            self._current_duty = None

    def _set_duty(self, percent: int) -> None:
        """Write the duty cycle to the hardware PWM output."""
        if not self._pi or not self._pi.connected:
            raise RuntimeError("pigpio not connected")

        duty = int(percent / 100.0 * _PIGPIO_RANGE)
        self._pi.hardware_PWM(self._pin, self._frequency, duty)
        self._current_duty = percent
