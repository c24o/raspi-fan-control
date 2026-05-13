"""Configuration management for the fan controller daemon.

Provides built-in defaults that allow the daemon to run without any external
configuration file. A YAML override at /etc/raspifanctl/config.yaml (or a
path supplied via --config) is merged on top of the defaults.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "/etc/raspifanctl/config.yaml"

# Hardware-safe PWM frequency bounds (Hz).
# Intel 4-pin spec recommends 25 kHz; allow a reasonable range.
MIN_PWM_FREQUENCY = 15_000
MAX_PWM_FREQUENCY = 50_000

# Sane temperature bounds (°C) for validation.
MIN_TEMP_THRESHOLD = 20
MAX_TEMP_THRESHOLD = 100

# Sane poll interval bounds (seconds). Temperature doesn't change that fast, so
# a very low poll interval is not necessary. In the other hand, a very high poll
# interval will make the fan less responsive to temperature changes.
MIN_POLL_INTERVAL = 2
MAX_POLL_INTERVAL = 60

# Sane smoothing window bounds (number of readings). Higher reduces fan flutter but increases latency.
MIN_SMOOTHING_WINDOW = 1
MAX_SMOOTHING_WINDOW = 10

# Temperature (°C) at which a warning is logged every poll cycle. Thermal
# throttling of rasberry pi starts at 80°C.
MIN_CRITICAL_TEMP = 70
MAX_CRITICAL_TEMP = 82

# Hysteresis bounds (°C). Larger hysteresis reduces fan flutter but increases
# latency.
MIN_HYSTERESIS = 1
MAX_HYSTERESIS = 10


@dataclass
class Config:
    """Runtime configuration for the fan controller."""

    poll_interval: int = 10
    hysteresis: int = 3
    pwm_frequency: int = 25_000
    gpio_pin: int = 18
    smoothing_window: int = 5
    log_level: str = "INFO"
    critical_temp: int = 78

    # Default fan curve: list of (temperature °C, fan speed %).
    # Below the lowest threshold the fan is off.
    curve: List[Tuple[int, int]] = field(default_factory=lambda: [
        (45, 10),
        (55, 30),
        (63, 50),
        (70, 75),
        (75, 100),
    ])


def _validate_curve(curve: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Validate and return a sanitised fan curve.

    Raises ValueError on invalid data so the daemon refuses to start with a
    broken configuration rather than silently misbehaving.
    """
    if not curve or len(curve) < 2:
        raise ValueError("Fan curve must contain at least 2 points")

    validated: List[Tuple[int, int]] = []
    prev_temp = -1

    for entry in curve:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError(f"Invalid curve entry: {entry!r} — expected [temp, speed]")

        temp, speed = int(entry[0]), int(entry[1])

        if not MIN_TEMP_THRESHOLD <= temp <= MAX_TEMP_THRESHOLD:
            raise ValueError(f"Curve temperature {temp}°C outside safe range "
                             f"({MIN_TEMP_THRESHOLD}–{MAX_TEMP_THRESHOLD})")
        if not 0 <= speed <= 100:
            raise ValueError(f"Curve speed {speed}% outside range 0–100")
        if temp <= prev_temp:
            raise ValueError(f"Curve temperatures must be strictly ascending "
                             f"(got {temp} after {prev_temp})")
        prev_temp = temp
        validated.append((temp, speed))

    return validated


def _validate(cfg: Config) -> Config:
    """Validate the full configuration, raising on fatal problems."""
    if cfg.poll_interval < 1:
        raise ValueError(f"poll_interval must be ≥ 1, got {cfg.poll_interval}")

    if not MIN_HYSTERESIS <= cfg.hysteresis <= MAX_HYSTERESIS:
        raise ValueError(f"hysteresis {cfg.hysteresis}°C outside safe range "
                         f"({MIN_HYSTERESIS}–{MAX_HYSTERESIS})")

    if not MIN_PWM_FREQUENCY <= cfg.pwm_frequency <= MAX_PWM_FREQUENCY:
        raise ValueError(f"pwm_frequency {cfg.pwm_frequency} Hz outside safe range "
                         f"({MIN_PWM_FREQUENCY}–{MAX_PWM_FREQUENCY})")

    if not MIN_SMOOTHING_WINDOW <= cfg.smoothing_window <= MAX_SMOOTHING_WINDOW:
        raise ValueError(f"smoothing_window {cfg.smoothing_window} outside safe range "
                         f"({MIN_SMOOTHING_WINDOW}–{MAX_SMOOTHING_WINDOW})")

    if not MIN_CRITICAL_TEMP <= cfg.critical_temp <= MAX_CRITICAL_TEMP:
        raise ValueError(f"critical_temp {cfg.critical_temp}°C outside safe range "
                         f"({MIN_CRITICAL_TEMP}–{MAX_CRITICAL_TEMP})")

    cfg.curve = _validate_curve(cfg.curve)
    cfg.log_level = cfg.log_level.upper()

    if cfg.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ValueError(f"Invalid log_level: {cfg.log_level}")

    return cfg


def load_config(path: str | None = None) -> Config:
    """Load configuration from defaults, optionally overlaid with a YAML file.

    Resolution order:
      1. Built-in defaults (Config dataclass)
      2. YAML file at *path* (or DEFAULT_CONFIG_PATH / $RASPIFANCTL_CONFIG)
      3. Validation pass

    The daemon is fully functional with no external file.
    """
    cfg = Config()
    config_path = path or os.environ.get("RASPIFANCTL_CONFIG", DEFAULT_CONFIG_PATH)

    if Path(config_path).is_file():
        logger.info("Loading config from %s", config_path)
        try:
            with open(config_path, "r") as fh:
                data = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse config file {config_path}: {exc}") from exc

        # Overlay each known key onto the defaults.
        for key in ("poll_interval", "hysteresis", "pwm_frequency", "gpio_pin",
                     "smoothing_window", "log_level", "critical_temp"):
            if key in data:
                setattr(cfg, key, data[key])

        if "curve" in data:
            cfg.curve = [(int(t), int(s)) for t, s in data["curve"]]
    else:
        logger.info("No config file at %s — using built-in defaults", config_path)

    return _validate(cfg)
