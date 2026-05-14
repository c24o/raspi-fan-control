"""Tests for src.temperature — CPU temperature reading and smoothing."""

from __future__ import annotations

from unittest import mock

import pytest

from src.temperature import TemperatureReader, THERMAL_ZONE_PATH, MIN_SANE_TEMP, MAX_SANE_TEMP


def _patch_thermal(value: str):
    """Patch Path.read_text so THERMAL_ZONE_PATH.read_text() returns *value*."""
    return mock.patch("pathlib.Path.read_text", return_value=value)


def _patch_thermal_error(exc):
    """Patch Path.read_text to raise *exc*."""
    return mock.patch("pathlib.Path.read_text", side_effect=exc)


class TestTemperatureReaderReadRaw:
    """Tests for raw sysfs temperature reads."""

    def test_reads_normal_temperature(self) -> None:
        reader = TemperatureReader(smoothing_window=1)
        with _patch_thermal("58200\n"):
            assert reader.read_raw() == 58.2

    def test_reads_integer_temperature(self) -> None:
        reader = TemperatureReader(smoothing_window=1)
        with _patch_thermal("45000"):
            assert reader.read_raw() == 45.0

    def test_reads_low_temperature(self) -> None:
        reader = TemperatureReader(smoothing_window=1)
        with _patch_thermal("0"):
            assert reader.read_raw() == 0.0

    def test_strips_whitespace(self) -> None:
        reader = TemperatureReader(smoothing_window=1)
        with _patch_thermal("  55000  \n"):
            assert reader.read_raw() == 55.0

    def test_raises_on_read_failure(self) -> None:
        reader = TemperatureReader(smoothing_window=1)
        with _patch_thermal_error(OSError("No such file")):
            with pytest.raises(RuntimeError, match="Failed to read CPU temperature"):
                reader.read_raw()

    def test_raises_on_non_numeric_content(self) -> None:
        reader = TemperatureReader(smoothing_window=1)
        with _patch_thermal("not_a_number"):
            with pytest.raises(RuntimeError, match="Failed to read CPU temperature"):
                reader.read_raw()

    def test_raises_on_temp_above_sane_max(self) -> None:
        reader = TemperatureReader(smoothing_window=1)
        with _patch_thermal("121000"):
            with pytest.raises(RuntimeError, match="outside sane range"):
                reader.read_raw()

    def test_raises_on_temp_below_sane_min(self) -> None:
        reader = TemperatureReader(smoothing_window=1)
        with _patch_thermal("-11000"):
            with pytest.raises(RuntimeError, match="outside sane range"):
                reader.read_raw()

    def test_accepts_temp_at_sane_boundaries(self) -> None:
        reader = TemperatureReader(smoothing_window=1)
        with _patch_thermal(str(int(MIN_SANE_TEMP * 1000))):
            assert reader.read_raw() == MIN_SANE_TEMP
        with _patch_thermal(str(int(MAX_SANE_TEMP * 1000))):
            assert reader.read_raw() == MAX_SANE_TEMP


class TestTemperatureReaderSmoothing:
    """Tests for the moving average smoothing."""

    def test_single_reading_returns_that_value(self) -> None:
        reader = TemperatureReader(smoothing_window=3)
        with _patch_thermal("50000"):
            assert reader.read() == 50.0

    def test_moving_average_of_multiple_readings(self) -> None:
        reader = TemperatureReader(smoothing_window=3)
        temps = ["50000", "60000", "70000"]
        for t in temps:
            with _patch_thermal(t):
                result = reader.read()
        assert result == 60.0

    def test_window_rolls_over(self) -> None:
        reader = TemperatureReader(smoothing_window=2)
        readings = ["50000", "60000", "70000"]
        for t in readings:
            with _patch_thermal(t):
                result = reader.read()
        assert result == 65.0

    def test_smoothing_window_of_1_returns_raw(self) -> None:
        reader = TemperatureReader(smoothing_window=1)
        with _patch_thermal("55000"):
            reader.read()
        with _patch_thermal("65000"):
            result = reader.read()
        assert result == 65.0

    def test_failed_read_does_not_pollute_buffer(self) -> None:
        reader = TemperatureReader(smoothing_window=3)
        with _patch_thermal("50000"):
            reader.read()
        with _patch_thermal_error(OSError):
            with pytest.raises(RuntimeError):
                reader.read()
        with _patch_thermal("60000"):
            result = reader.read()
        assert result == 55.0

    def test_smoothing_dampens_spike(self) -> None:
        reader = TemperatureReader(smoothing_window=5)
        for _ in range(4):
            with _patch_thermal("50000"):
                reader.read()
        with _patch_thermal("80000"):
            result = reader.read()
        assert result == 56.0
