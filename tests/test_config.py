"""Tests for src.config — configuration loading and validation."""

from __future__ import annotations

import os
import textwrap
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.config import (
    Config,
    _validate,
    _validate_curve,
    load_config,
    MIN_PWM_FREQUENCY,
    MAX_PWM_FREQUENCY,
    MIN_TEMP_THRESHOLD,
    MAX_TEMP_THRESHOLD,
    MIN_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    MIN_SMOOTHING_WINDOW,
    MAX_SMOOTHING_WINDOW,
    MIN_CRITICAL_TEMP,
    MAX_CRITICAL_TEMP,
    MIN_HYSTERESIS,
    MAX_HYSTERESIS,
)


# ── Config dataclass defaults ────────────────────────────────────────────


class TestConfigDefaults:
    """Built-in defaults must produce a valid configuration."""

    def test_defaults_are_valid(self) -> None:
        cfg = Config()
        validated = _validate(cfg)
        assert validated is cfg

    def test_default_poll_interval(self) -> None:
        assert Config().poll_interval == 10

    def test_default_hysteresis(self) -> None:
        assert Config().hysteresis == 3

    def test_default_pwm_frequency(self) -> None:
        assert Config().pwm_frequency == 25_000

    def test_default_gpio_pin(self) -> None:
        assert Config().gpio_pin == 18

    def test_default_smoothing_window(self) -> None:
        assert Config().smoothing_window == 5

    def test_default_log_level(self) -> None:
        assert Config().log_level == "INFO"

    def test_default_critical_temp(self) -> None:
        assert Config().critical_temp == 78

    def test_default_curve_has_multiple_points(self) -> None:
        assert len(Config().curve) >= 2

    def test_default_curve_is_ascending(self) -> None:
        temps = [t for t, _ in Config().curve]
        assert temps == sorted(temps)
        assert len(set(temps)) == len(temps)  # strictly ascending


# ── _validate_curve ──────────────────────────────────────────────────────


class TestValidateCurve:
    """Tests for fan curve validation."""

    def test_valid_curve(self) -> None:
        curve = [(30, 20), (50, 50), (70, 100)]
        result = _validate_curve(curve)
        assert result == [(30, 20), (50, 50), (70, 100)]

    def test_accepts_lists_as_entries(self) -> None:
        """YAML produces lists, not tuples."""
        curve = [[40, 30], [60, 80]]
        result = _validate_curve(curve)
        assert result == [(40, 30), (60, 80)]

    def test_rejects_single_point(self) -> None:
        with pytest.raises(ValueError, match="at least 2 points"):
            _validate_curve([(50, 50)])

    def test_rejects_empty_curve(self) -> None:
        with pytest.raises(ValueError, match="at least 2 points"):
            _validate_curve([])

    def test_rejects_temp_below_minimum(self) -> None:
        with pytest.raises(ValueError, match="outside safe range"):
            _validate_curve([(MIN_TEMP_THRESHOLD - 1, 30), (50, 50)])

    def test_rejects_temp_above_maximum(self) -> None:
        with pytest.raises(ValueError, match="outside safe range"):
            _validate_curve([(50, 30), (MAX_TEMP_THRESHOLD + 1, 100)])

    def test_accepts_temp_at_boundaries(self) -> None:
        result = _validate_curve([(MIN_TEMP_THRESHOLD, 0), (MAX_TEMP_THRESHOLD, 100)])
        assert len(result) == 2

    def test_rejects_speed_below_zero(self) -> None:
        with pytest.raises(ValueError, match="outside range 0–100"):
            _validate_curve([(30, -1), (50, 50)])

    def test_rejects_speed_above_100(self) -> None:
        with pytest.raises(ValueError, match="outside range 0–100"):
            _validate_curve([(30, 50), (50, 101)])

    def test_accepts_speed_at_boundaries(self) -> None:
        result = _validate_curve([(30, 0), (50, 100)])
        assert result == [(30, 0), (50, 100)]

    def test_rejects_non_ascending_temperatures(self) -> None:
        with pytest.raises(ValueError, match="strictly ascending"):
            _validate_curve([(50, 30), (50, 60)])

    def test_rejects_descending_temperatures(self) -> None:
        with pytest.raises(ValueError, match="strictly ascending"):
            _validate_curve([(60, 30), (50, 60)])

    def test_rejects_malformed_entry_wrong_length(self) -> None:
        with pytest.raises(ValueError, match="Invalid curve entry"):
            _validate_curve([(30, 20, 10), (50, 50)])

    def test_rejects_malformed_entry_not_iterable(self) -> None:
        with pytest.raises(ValueError, match="Invalid curve entry"):
            _validate_curve([42, (50, 50)])


# ── _validate (full config) ──────────────────────────────────────────────


class TestValidate:
    """Tests for full configuration validation."""

    def _make_config(self, **overrides) -> Config:
        cfg = Config()
        for k, v in overrides.items():
            setattr(cfg, k, v)
        return cfg

    # poll_interval
    def test_rejects_poll_interval_below_min(self) -> None:
        with pytest.raises(ValueError, match="poll_interval"):
            _validate(self._make_config(poll_interval=MIN_POLL_INTERVAL - 1))

    def test_rejects_poll_interval_above_max(self) -> None:
        with pytest.raises(ValueError, match="poll_interval"):
            _validate(self._make_config(poll_interval=MAX_POLL_INTERVAL + 1))

    def test_accepts_poll_interval_at_min(self) -> None:
        cfg = _validate(self._make_config(poll_interval=MIN_POLL_INTERVAL))
        assert cfg.poll_interval == MIN_POLL_INTERVAL

    def test_accepts_poll_interval_at_max(self) -> None:
        cfg = _validate(self._make_config(poll_interval=MAX_POLL_INTERVAL))
        assert cfg.poll_interval == MAX_POLL_INTERVAL

    # hysteresis
    def test_rejects_hysteresis_below_min(self) -> None:
        with pytest.raises(ValueError, match="hysteresis"):
            _validate(self._make_config(hysteresis=MIN_HYSTERESIS - 1))

    def test_rejects_hysteresis_above_max(self) -> None:
        with pytest.raises(ValueError, match="hysteresis"):
            _validate(self._make_config(hysteresis=MAX_HYSTERESIS + 1))

    def test_accepts_hysteresis_at_boundaries(self) -> None:
        _validate(self._make_config(hysteresis=MIN_HYSTERESIS))
        _validate(self._make_config(hysteresis=MAX_HYSTERESIS))

    # pwm_frequency
    def test_rejects_pwm_frequency_below_min(self) -> None:
        with pytest.raises(ValueError, match="pwm_frequency"):
            _validate(self._make_config(pwm_frequency=MIN_PWM_FREQUENCY - 1))

    def test_rejects_pwm_frequency_above_max(self) -> None:
        with pytest.raises(ValueError, match="pwm_frequency"):
            _validate(self._make_config(pwm_frequency=MAX_PWM_FREQUENCY + 1))

    def test_accepts_pwm_frequency_at_boundaries(self) -> None:
        _validate(self._make_config(pwm_frequency=MIN_PWM_FREQUENCY))
        _validate(self._make_config(pwm_frequency=MAX_PWM_FREQUENCY))

    # smoothing_window
    def test_rejects_smoothing_window_below_min(self) -> None:
        with pytest.raises(ValueError, match="smoothing_window"):
            _validate(self._make_config(smoothing_window=MIN_SMOOTHING_WINDOW - 1))

    def test_rejects_smoothing_window_above_max(self) -> None:
        with pytest.raises(ValueError, match="smoothing_window"):
            _validate(self._make_config(smoothing_window=MAX_SMOOTHING_WINDOW + 1))

    def test_accepts_smoothing_window_at_boundaries(self) -> None:
        _validate(self._make_config(smoothing_window=MIN_SMOOTHING_WINDOW))
        _validate(self._make_config(smoothing_window=MAX_SMOOTHING_WINDOW))

    # critical_temp
    def test_rejects_critical_temp_below_min(self) -> None:
        with pytest.raises(ValueError, match="critical_temp"):
            _validate(self._make_config(critical_temp=MIN_CRITICAL_TEMP - 1))

    def test_rejects_critical_temp_above_max(self) -> None:
        with pytest.raises(ValueError, match="critical_temp"):
            _validate(self._make_config(critical_temp=MAX_CRITICAL_TEMP + 1))

    def test_accepts_critical_temp_at_boundaries(self) -> None:
        _validate(self._make_config(critical_temp=MIN_CRITICAL_TEMP))
        _validate(self._make_config(critical_temp=MAX_CRITICAL_TEMP))

    # log_level
    def test_accepts_all_valid_log_levels(self) -> None:
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            cfg = _validate(self._make_config(log_level=level))
            assert cfg.log_level == level

    def test_accepts_lowercase_log_level(self) -> None:
        cfg = _validate(self._make_config(log_level="debug"))
        assert cfg.log_level == "DEBUG"

    def test_rejects_invalid_log_level(self) -> None:
        with pytest.raises(ValueError, match="Invalid log_level"):
            _validate(self._make_config(log_level="VERBOSE"))


# ── load_config ──────────────────────────────────────────────────────────


class TestLoadConfig:
    """Tests for configuration file loading."""

    def test_loads_defaults_when_no_file_exists(self) -> None:
        cfg = load_config("/nonexistent/path/config.yaml")
        assert cfg.poll_interval == Config().poll_interval

    def test_loads_valid_yaml_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(textwrap.dedent("""\
            poll_interval: 30
            hysteresis: 5
            pwm_frequency: 25000
            smoothing_window: 3
            critical_temp: 75
            log_level: WARNING
        """))
        cfg = load_config(str(config_file))
        assert cfg.poll_interval == 30
        assert cfg.hysteresis == 5
        assert cfg.smoothing_window == 3
        assert cfg.critical_temp == 75
        assert cfg.log_level == "WARNING"

    def test_yaml_overrides_only_specified_keys(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("hysteresis: 5\n")
        cfg = load_config(str(config_file))
        # Overridden
        assert cfg.hysteresis == 5
        # Kept default
        assert cfg.poll_interval == Config().poll_interval
        assert cfg.gpio_pin == Config().gpio_pin

    def test_loads_custom_curve_from_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(textwrap.dedent("""\
            curve:
              - [40, 20]
              - [60, 60]
              - [80, 100]
        """))
        cfg = load_config(str(config_file))
        assert cfg.curve == [(40, 20), (60, 60), (80, 100)]

    def test_rejects_invalid_yaml_syntax(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("poll_interval: [invalid yaml\n")
        with pytest.raises(ValueError, match="Failed to parse"):
            load_config(str(config_file))

    def test_rejects_yaml_with_invalid_values(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("pwm_frequency: 999\n")
        with pytest.raises(ValueError, match="pwm_frequency"):
            load_config(str(config_file))

    def test_env_variable_override(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("hysteresis: 7\n")
        with mock.patch.dict(os.environ, {"RASPIFANCTL_CONFIG": str(config_file)}):
            cfg = load_config()
            assert cfg.hysteresis == 7

    def test_empty_yaml_file_uses_defaults(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        cfg = load_config(str(config_file))
        assert cfg.poll_interval == Config().poll_interval
