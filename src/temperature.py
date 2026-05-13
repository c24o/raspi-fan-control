"""CPU temperature reading and smoothing.

Reads from the Linux thermal subsystem and maintains a rolling buffer for
moving-average smoothing to prevent fan oscillation from transient spikes.
"""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

THERMAL_ZONE_PATH = Path("/sys/class/thermal/thermal_zone0/temp")

# Sanity bounds for raw readings (°C).
MIN_SANE_TEMP = -10.0
MAX_SANE_TEMP = 120.0


class TemperatureReader:
    """Reads CPU temperature and provides smoothed values."""

    def __init__(self, smoothing_window: int) -> None:
        self._window: deque[float] = deque(maxlen=max(1, smoothing_window))

    def read_raw(self) -> float:
        """Read the current CPU temperature in °C.

        Returns the raw value directly from the thermal subsystem.
        Raises RuntimeError on read failure or nonsensical values.
        """
        try:
            raw = THERMAL_ZONE_PATH.read_text().strip()
            temp_c = int(raw) / 1000.0
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Failed to read CPU temperature: {exc}") from exc

        if not MIN_SANE_TEMP <= temp_c <= MAX_SANE_TEMP:
            raise RuntimeError(f"CPU temperature {temp_c}°C outside sane range "
                               f"({MIN_SANE_TEMP}–{MAX_SANE_TEMP})")
        return temp_c

    def read(self) -> float:
        """Read the CPU temperature and return a smoothed value.

        Adds the latest raw reading to the rolling buffer and returns the
        moving average.  If a read fails, the buffer is not polluted — the
        previous smoothed value is returned (if available) or the error
        propagates.
        """
        temp = self.read_raw()
        self._window.append(temp)
        return sum(self._window) / len(self._window)
