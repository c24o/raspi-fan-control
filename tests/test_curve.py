"""Tests for src.curve — fan speed curve with hysteresis."""

from __future__ import annotations

import pytest

from src.curve import FanCurve

# Standard test curve matching the project defaults.
DEFAULT_CURVE = [(45, 10), (55, 30), (63, 50), (70, 75), (75, 100)]
DEFAULT_HYSTERESIS = 3


class TestFanCurveEvaluate:
    """Basic curve evaluation without hysteresis effects."""

    def _make_curve(self, hysteresis: int = DEFAULT_HYSTERESIS) -> FanCurve:
        return FanCurve(curve=DEFAULT_CURVE, hysteresis=hysteresis)

    def test_below_lowest_threshold_returns_zero(self) -> None:
        curve = self._make_curve()
        assert curve.evaluate(30.0) == 0

    def test_at_lowest_threshold(self) -> None:
        curve = self._make_curve()
        assert curve.evaluate(45.0) == 10

    def test_between_thresholds_uses_lower(self) -> None:
        curve = self._make_curve()
        assert curve.evaluate(50.0) == 10

    def test_at_second_threshold(self) -> None:
        curve = self._make_curve()
        assert curve.evaluate(55.0) == 30

    def test_at_highest_threshold(self) -> None:
        curve = self._make_curve()
        assert curve.evaluate(75.0) == 100

    def test_above_highest_threshold(self) -> None:
        curve = self._make_curve()
        assert curve.evaluate(90.0) == 100

    def test_at_each_threshold(self) -> None:
        for temp, expected_speed in DEFAULT_CURVE:
            # Fresh curve for each to avoid hysteresis effects
            c = self._make_curve()
            assert c.evaluate(float(temp)) == expected_speed

    def test_current_speed_is_none_before_evaluation(self) -> None:
        curve = self._make_curve()
        assert curve.current_speed is None

    def test_current_speed_updated_after_evaluation(self) -> None:
        curve = self._make_curve()
        curve.evaluate(60.0)
        assert curve.current_speed == 30


class TestFanCurveHysteresis:
    """Hysteresis prevents rapid fan speed oscillation."""

    def _make_curve(self, hysteresis: int = DEFAULT_HYSTERESIS) -> FanCurve:
        return FanCurve(curve=DEFAULT_CURVE, hysteresis=hysteresis)

    def test_speed_holds_when_temp_drops_within_hysteresis(self) -> None:
        """Fan at 30% (threshold 55°C) should hold when temp drops to 53°C
        (within 55 - 3 = 52°C boundary)."""
        curve = self._make_curve()
        curve.evaluate(55.0)  # → 30%
        assert curve.evaluate(53.0) == 30  # Still within hysteresis

    def test_speed_drops_when_temp_drops_below_hysteresis(self) -> None:
        """Fan should drop when temp goes below threshold - hysteresis."""
        curve = self._make_curve()
        curve.evaluate(55.0)  # → 30%
        assert curve.evaluate(51.0) == 10  # Below 55 - 3 = 52, drops to 10%

    def test_speed_drops_to_zero_below_all_thresholds(self) -> None:
        curve = self._make_curve()
        curve.evaluate(55.0)  # → 30%
        result = curve.evaluate(30.0)  # Way below everything
        assert result == 0

    def test_hysteresis_at_exact_boundary(self) -> None:
        """At exactly threshold - hysteresis, speed should hold."""
        curve = self._make_curve()
        curve.evaluate(55.0)  # → 30%
        # 55 - 3 = 52, temp is exactly at the boundary
        assert curve.evaluate(52.0) == 30  # Holds (>= threshold - hysteresis)

    def test_hysteresis_one_below_boundary(self) -> None:
        """One degree below the hysteresis boundary should drop."""
        curve = self._make_curve()
        curve.evaluate(55.0)  # → 30%
        assert curve.evaluate(51.9) == 10  # Below 52, drops

    def test_speed_increases_immediately_no_hysteresis_delay(self) -> None:
        """Rising temperature should increase speed without hysteresis delay."""
        curve = self._make_curve()
        curve.evaluate(45.0)  # → 10%
        assert curve.evaluate(55.0) == 30  # Immediate increase
        assert curve.evaluate(70.0) == 75  # Immediate increase

    def test_hysteresis_across_multiple_levels(self) -> None:
        """Temperature rising to max then gradually dropping."""
        curve = self._make_curve()
        curve.evaluate(75.0)  # → 100%
        assert curve.current_speed == 100

        # Drop slightly — should hold at 100%
        assert curve.evaluate(73.0) == 100  # Within 75 - 3 = 72

        # Drop below 72 — should go to 75%
        assert curve.evaluate(71.0) == 75  # Below 72, but >= 70

        # Drop slightly from 70 threshold — hold at 75%
        assert curve.evaluate(68.0) == 75  # Within 70 - 3 = 67

        # Drop below 67 — should go to 50%
        assert curve.evaluate(66.0) == 50  # Below 67, but >= 63

    def test_oscillating_temperature(self) -> None:
        """Rapid temperature changes should not cause fan flutter."""
        curve = self._make_curve()
        curve.evaluate(56.0)  # → 30%

        # Oscillate around 55°C threshold
        speeds = []
        for temp in [54.0, 56.0, 54.0, 56.0, 54.0]:
            speeds.append(curve.evaluate(temp))

        # With hysteresis=3, 54°C is within the hold zone (55-3=52)
        # so speed should stay at 30% throughout
        assert all(s == 30 for s in speeds)

    def test_hysteresis_of_1(self) -> None:
        curve = FanCurve(curve=[(50, 30), (60, 70)], hysteresis=1)
        curve.evaluate(60.0)  # → 70%
        assert curve.evaluate(59.5) == 70  # Within 60-1=59
        assert curve.evaluate(58.0) == 30  # Below 59, drops


class TestFanCurveEdgeCases:
    """Edge cases and unusual inputs."""

    def test_two_point_curve(self) -> None:
        curve = FanCurve(curve=[(40, 20), (80, 100)], hysteresis=3)
        assert curve.evaluate(30.0) == 0
        assert curve.evaluate(40.0) == 20
        assert curve.evaluate(60.0) == 20
        assert curve.evaluate(80.0) == 100

    def test_curve_sorted_internally(self) -> None:
        """Curve should be sorted even if provided unsorted."""
        curve = FanCurve(curve=[(80, 100), (40, 20)], hysteresis=3)
        assert curve.evaluate(40.0) == 20
        assert curve.evaluate(80.0) == 100

    def test_fractional_temperature(self) -> None:
        curve = FanCurve(curve=DEFAULT_CURVE, hysteresis=DEFAULT_HYSTERESIS)
        result = curve.evaluate(54.999)
        assert result == 10  # Just below 55 threshold

    def test_evaluate_returns_int(self) -> None:
        curve = FanCurve(curve=DEFAULT_CURVE, hysteresis=DEFAULT_HYSTERESIS)
        result = curve.evaluate(60.5)
        assert isinstance(result, int)
