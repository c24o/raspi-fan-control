"""Fan speed curve with hysteresis.

Implements a piecewise step curve that maps CPU temperature to fan speed.
Hysteresis prevents rapid oscillation when the temperature hovers around
a threshold boundary.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class FanCurve:
    """Determines target fan speed from temperature using a step curve.

    The curve is a sorted list of (temperature, speed%) tuples.  When the
    temperature rises *above* a threshold, the corresponding speed activates.
    When the temperature *drops*, it must fall below the threshold minus the
    hysteresis margin before the speed decreases.

    Example with hysteresis=3 and threshold at 55°C / 30%:
      - Temperature rises to 55°C → fan goes to 30%.
      - Temperature drops to 54°C → fan stays at 30% (within hysteresis).
      - Temperature drops to 51°C → fan drops to the next lower speed.
    """

    def __init__(
        self,
        curve: List[Tuple[int, int]],
        hysteresis: int = 3,
    ) -> None:
        # Curve must be sorted by temperature (enforced by config validation).
        self._curve = sorted(curve, key=lambda x: x[0])
        self._hysteresis = hysteresis
        self._current_speed: int | None = None

    @property
    def current_speed(self) -> int | None:
        """The last computed fan speed, or None before the first evaluation."""
        return self._current_speed

    def evaluate(self, temp: float) -> int:
        """Determine the target fan speed for the given temperature.

        Returns the speed percentage (0–100).
        """
        # Determine the target speed by walking the curve from highest to
        # lowest threshold, picking the first one the temperature meets.
        target_speed = 0

        for threshold, speed in reversed(self._curve):
            if temp >= threshold:
                target_speed = speed
                break

        # Apply hysteresis: resist lowering the speed unless the temperature
        # has dropped sufficiently below the threshold that justified the
        # current speed.
        if self._current_speed is not None and target_speed < self._current_speed:
            for threshold, speed in reversed(self._curve):
                if speed == self._current_speed and temp >= (threshold - self._hysteresis):
                    # Temperature hasn't dropped far enough — hold current speed.
                    return self._current_speed

        self._current_speed = target_speed
        return target_speed
