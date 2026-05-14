"""Tests for src.pwm — hardware PWM fan control via pigpio."""

from __future__ import annotations

from unittest import mock

import pytest

# pigpio may not be installed on the dev machine, so we mock the import.
pigpio_mock = mock.MagicMock()
pigpio_mock.OUTPUT = 1

with mock.patch.dict("sys.modules", {"pigpio": pigpio_mock}):
    from src.pwm import PWMController, _PIGPIO_RANGE


def _make_mock_pi(connected: bool = True) -> mock.MagicMock:
    """Create a mock pigpio.pi instance."""
    pi = mock.MagicMock()
    pi.connected = connected
    return pi


class TestPWMControllerInitialize:
    """Tests for PWM initialization."""

    def test_initialize_connects_and_sets_100_percent(self) -> None:
        mock_pi = _make_mock_pi()
        with mock.patch.object(pigpio_mock, "pi", return_value=mock_pi):
            ctrl = PWMController(gpio_pin=18, frequency=25_000)
            ctrl.initialize()

        mock_pi.set_mode.assert_called_once_with(18, pigpio_mock.OUTPUT)
        mock_pi.hardware_PWM.assert_called_once_with(18, 25_000, _PIGPIO_RANGE)

    def test_initialize_raises_when_not_connected(self) -> None:
        mock_pi = _make_mock_pi(connected=False)
        with mock.patch.object(pigpio_mock, "pi", return_value=mock_pi):
            ctrl = PWMController(gpio_pin=18, frequency=25_000)
            with pytest.raises(RuntimeError, match="pigpiod"):
                ctrl.initialize()


class TestPWMControllerSetSpeed:
    """Tests for fan speed setting."""

    def _make_initialized_ctrl(self) -> tuple[PWMController, mock.MagicMock]:
        mock_pi = _make_mock_pi()
        with mock.patch.object(pigpio_mock, "pi", return_value=mock_pi):
            ctrl = PWMController(gpio_pin=18, frequency=25_000)
            ctrl.initialize()
        mock_pi.hardware_PWM.reset_mock()
        return ctrl, mock_pi

    def test_set_speed_50_percent(self) -> None:
        ctrl, mock_pi = self._make_initialized_ctrl()
        ctrl.set_speed(50)
        expected_duty = int(50 / 100.0 * _PIGPIO_RANGE)
        mock_pi.hardware_PWM.assert_called_once_with(18, 25_000, expected_duty)

    def test_set_speed_0_percent(self) -> None:
        ctrl, mock_pi = self._make_initialized_ctrl()
        ctrl.set_speed(0)
        mock_pi.hardware_PWM.assert_called_once_with(18, 25_000, 0)

    def test_set_speed_100_percent_skipped_when_already_100(self) -> None:
        """Initialize sets 100%, so setting 100 again should be a no-op."""
        ctrl, mock_pi = self._make_initialized_ctrl()
        ctrl.set_speed(100)
        mock_pi.hardware_PWM.assert_not_called()

    def test_set_speed_clamps_above_100(self) -> None:
        ctrl, mock_pi = self._make_initialized_ctrl()
        ctrl.set_speed(150)
        # Should clamp to 100, which is already the current duty → no-op
        mock_pi.hardware_PWM.assert_not_called()

    def test_set_speed_clamps_below_0(self) -> None:
        ctrl, mock_pi = self._make_initialized_ctrl()
        ctrl.set_speed(-10)
        mock_pi.hardware_PWM.assert_called_once_with(18, 25_000, 0)

    def test_redundant_speed_skipped(self) -> None:
        ctrl, mock_pi = self._make_initialized_ctrl()
        ctrl.set_speed(50)
        mock_pi.hardware_PWM.reset_mock()
        ctrl.set_speed(50)
        mock_pi.hardware_PWM.assert_not_called()

    def test_different_speed_writes(self) -> None:
        ctrl, mock_pi = self._make_initialized_ctrl()
        ctrl.set_speed(30)
        mock_pi.hardware_PWM.reset_mock()
        ctrl.set_speed(60)
        assert mock_pi.hardware_PWM.called


class TestPWMControllerShutdown:
    """Tests for fail-safe shutdown."""

    def test_shutdown_sets_100_percent_and_stops(self) -> None:
        mock_pi = _make_mock_pi()
        with mock.patch.object(pigpio_mock, "pi", return_value=mock_pi):
            ctrl = PWMController(gpio_pin=18, frequency=25_000)
            ctrl.initialize()

        mock_pi.hardware_PWM.reset_mock()
        ctrl.shutdown()

        mock_pi.hardware_PWM.assert_called_with(18, 25_000, _PIGPIO_RANGE)
        mock_pi.stop.assert_called_once()

    def test_shutdown_clears_internal_state(self) -> None:
        mock_pi = _make_mock_pi()
        with mock.patch.object(pigpio_mock, "pi", return_value=mock_pi):
            ctrl = PWMController(gpio_pin=18, frequency=25_000)
            ctrl.initialize()
            ctrl.shutdown()

        assert ctrl._pi is None
        assert ctrl._current_duty is None

    def test_shutdown_handles_exception_gracefully(self) -> None:
        mock_pi = _make_mock_pi()
        mock_pi.hardware_PWM.side_effect = Exception("GPIO error")
        with mock.patch.object(pigpio_mock, "pi", return_value=mock_pi):
            ctrl = PWMController(gpio_pin=18, frequency=25_000)
            ctrl._pi = mock_pi
            ctrl._current_duty = 50
            # Should not raise
            ctrl.shutdown()

        assert ctrl._pi is None

    def test_shutdown_without_initialize_is_safe(self) -> None:
        ctrl = PWMController(gpio_pin=18, frequency=25_000)
        ctrl.shutdown()  # Should not raise


class TestPWMControllerDutyCycle:
    """Tests for duty cycle calculation accuracy."""

    def test_0_percent_maps_to_0_duty(self) -> None:
        mock_pi = _make_mock_pi()
        with mock.patch.object(pigpio_mock, "pi", return_value=mock_pi):
            ctrl = PWMController(gpio_pin=18, frequency=25_000)
            ctrl.initialize()
            ctrl.set_speed(0)
        calls = mock_pi.hardware_PWM.call_args_list
        # Last call should be 0 duty
        assert calls[-1] == mock.call(18, 25_000, 0)

    def test_100_percent_maps_to_full_range(self) -> None:
        mock_pi = _make_mock_pi()
        with mock.patch.object(pigpio_mock, "pi", return_value=mock_pi):
            ctrl = PWMController(gpio_pin=18, frequency=25_000)
            ctrl.initialize()
        # initialize() calls _set_duty(100)
        mock_pi.hardware_PWM.assert_called_with(18, 25_000, _PIGPIO_RANGE)

    def test_50_percent_maps_to_half_range(self) -> None:
        mock_pi = _make_mock_pi()
        with mock.patch.object(pigpio_mock, "pi", return_value=mock_pi):
            ctrl = PWMController(gpio_pin=18, frequency=25_000)
            ctrl.initialize()
            ctrl.set_speed(50)
        assert mock_pi.hardware_PWM.call_args == mock.call(18, 25_000, _PIGPIO_RANGE // 2)
