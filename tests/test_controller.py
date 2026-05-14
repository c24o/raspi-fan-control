"""Tests for src.controller — main control loop orchestration."""

from __future__ import annotations

from unittest import mock

import pytest

# Mock pigpio before importing controller (which imports pwm).
pigpio_mock = mock.MagicMock()
pigpio_mock.OUTPUT = 1
with mock.patch.dict("sys.modules", {"pigpio": pigpio_mock}):
    from src.config import Config
    from src.controller import FanController
    from src.temperature import THERMAL_ZONE_PATH


def _make_config(**overrides) -> Config:
    """Create a Config with short poll for fast tests."""
    defaults = dict(poll_interval=2, hysteresis=3, smoothing_window=1)
    defaults.update(overrides)
    cfg = Config()
    for k, v in defaults.items():
        setattr(cfg, k, v)
    return cfg


def _patch_thermal(value: str):
    return mock.patch("pathlib.Path.read_text", return_value=value)


def _make_mock_pi(connected: bool = True) -> mock.MagicMock:
    pi = mock.MagicMock()
    pi.connected = connected
    return pi


class TestFanControllerInit:
    """Tests for controller initialization."""

    def test_creates_subsystems(self) -> None:
        cfg = _make_config()
        ctrl = FanController(cfg)
        assert ctrl._temp_reader is not None
        assert ctrl._pwm is not None
        assert ctrl._curve is not None
        assert ctrl._running is False


class TestFanControllerStartStop:
    """Tests for start/stop lifecycle."""

    def test_stop_sets_running_false(self) -> None:
        cfg = _make_config()
        ctrl = FanController(cfg)
        ctrl._running = True
        ctrl.stop()
        assert ctrl._running is False

    def test_start_initializes_pwm_and_runs_loop(self) -> None:
        cfg = _make_config()
        ctrl = FanController(cfg)

        mock_pi = _make_mock_pi()
        with mock.patch.object(pigpio_mock, "pi", return_value=mock_pi):
            # Stop after first iteration
            with mock.patch.object(ctrl, "_loop") as mock_loop:
                ctrl.start()
                mock_loop.assert_called_once()

        # PWM should be shut down (finally block)
        mock_pi.stop.assert_called()

    def test_start_shuts_down_pwm_even_on_exception(self) -> None:
        cfg = _make_config()
        ctrl = FanController(cfg)

        mock_pi = _make_mock_pi()
        with mock.patch.object(pigpio_mock, "pi", return_value=mock_pi):
            with mock.patch.object(ctrl, "_loop", side_effect=RuntimeError("test")):
                with pytest.raises(RuntimeError):
                    ctrl.start()

        # Shutdown still called via finally
        mock_pi.stop.assert_called()


class TestFanControllerTick:
    """Tests for the single-tick control cycle."""

    def _make_controller_with_mock_pwm(self, temp_str: str, **cfg_overrides):
        """Build a controller with mocked temperature and PWM."""
        cfg = _make_config(**cfg_overrides)
        ctrl = FanController(cfg)

        # Mock the PWM controller
        ctrl._pwm = mock.MagicMock()
        ctrl._pwm._current_duty = None

        return ctrl

    def test_tick_reads_temp_and_sets_speed(self) -> None:
        ctrl = self._make_controller_with_mock_pwm("55000")
        with _patch_thermal("55000"):
            ctrl._tick()
        ctrl._pwm.set_speed.assert_called_once()

    def test_tick_sets_correct_speed_for_temp(self) -> None:
        ctrl = self._make_controller_with_mock_pwm("70000")
        with _patch_thermal("70000"):
            ctrl._tick()
        ctrl._pwm.set_speed.assert_called_with(75)

    def test_tick_below_all_thresholds_sets_zero(self) -> None:
        ctrl = self._make_controller_with_mock_pwm("30000")
        with _patch_thermal("30000"):
            ctrl._tick()
        ctrl._pwm.set_speed.assert_called_with(0)

    def test_tick_logs_on_speed_change(self) -> None:
        ctrl = self._make_controller_with_mock_pwm("55000")
        with _patch_thermal("55000"):
            ctrl._tick()
        assert ctrl._last_logged_speed == 30

    def test_tick_does_not_relog_same_speed(self) -> None:
        ctrl = self._make_controller_with_mock_pwm("55000")
        ctrl._last_logged_speed = 30

        with _patch_thermal("55000"), mock.patch("src.controller.logger") as mock_logger:
            ctrl._tick()
            # info should not be called for speed change (same speed)
            for call in mock_logger.info.call_args_list:
                assert "fan speed" not in str(call)


class TestFanControllerFailSafe:
    """Tests for fail-safe behavior in the control loop."""

    def test_loop_sets_100_on_tick_exception(self) -> None:
        cfg = _make_config()
        ctrl = FanController(cfg)
        ctrl._pwm = mock.MagicMock()
        ctrl._running = True

        # Make _tick raise, and stop after one iteration
        call_count = 0

        def tick_then_stop():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("sensor failure")
            ctrl._running = False

        ctrl._tick = tick_then_stop
        ctrl._interruptible_sleep = mock.MagicMock()
        ctrl._loop()

        ctrl._pwm.set_speed.assert_called_with(100)

    def test_loop_continues_after_tick_exception(self) -> None:
        cfg = _make_config()
        ctrl = FanController(cfg)
        ctrl._pwm = mock.MagicMock()
        ctrl._running = True

        call_count = 0

        def tick_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            ctrl._running = False # this makes the loop to stop in the 2nd iteration.

        ctrl._tick = tick_side_effect
        ctrl._interruptible_sleep = mock.MagicMock()
        ctrl._loop()

        # Should have been called twice (error + successful stop)
        assert call_count == 2


class TestFanControllerCriticalTemp:
    """Tests for critical temperature warning."""

    def test_warning_logged_at_critical_temp(self) -> None:
        cfg = _make_config(critical_temp=78)
        ctrl = FanController(cfg)
        ctrl._pwm = mock.MagicMock()

        with _patch_thermal("78000"), mock.patch("src.controller.logger") as mock_logger:
            ctrl._tick()
            mock_logger.warning.assert_called_once()
            assert "78.0" in str(mock_logger.warning.call_args)

    def test_no_warning_below_critical_temp(self) -> None:
        cfg = _make_config(critical_temp=78)
        ctrl = FanController(cfg)
        ctrl._pwm = mock.MagicMock()

        with _patch_thermal("50000"), mock.patch("src.controller.logger") as mock_logger:
            ctrl._tick()
            mock_logger.warning.assert_not_called()


class TestFanControllerInterruptibleSleep:
    """Tests for the interruptible sleep mechanism."""

    def test_sleep_exits_early_when_stopped(self) -> None:
        cfg = _make_config()
        ctrl = FanController(cfg)
        ctrl._running = False

        with mock.patch("src.controller.time.sleep") as mock_sleep:
            ctrl._interruptible_sleep(10)
            mock_sleep.assert_not_called()

    def test_sleep_calls_sleep_correct_number_of_times(self) -> None:
        cfg = _make_config()
        ctrl = FanController(cfg)
        ctrl._running = True

        # Stop after 3 iterations
        call_count = 0

        def stop_after_3(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                ctrl._running = False

        with mock.patch("src.controller.time.sleep", side_effect=stop_after_3):
            ctrl._interruptible_sleep(10)

        assert call_count == 3
