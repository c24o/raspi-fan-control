# raspi-fan-control

A lightweight, production-quality PWM fan controller daemon for Raspberry Pi.

Monitors CPU temperature and dynamically adjusts fan speed using hardware PWM, with configurable temperature curves, hysteresis, and smoothing — designed to run as a systemd service on headless Linux systems.

## Features

- **Hardware PWM** via `pigpio` on GPIO18 at 25 kHz (4-pin fan standard)
- **Configurable step curve** mapping temperature ranges to fan speeds
- **Hysteresis** prevents rapid fan speed oscillation near threshold boundaries
- **Temperature smoothing** via moving average of recent readings
- **Fail-safe behavior** — fan runs at 100% on crash, shutdown, or fatal error
- **systemd integration** with auto-restart, journald logging, and boot startup
- **YAML configuration** with safe built-in defaults (runs without any config file)
- **Minimal footprint** — single-threaded, no dependencies beyond `pigpio` and `PyYAML`

## Architecture

```
src/
├── main.py          # Entry point, signal handling, lifecycle
├── controller.py    # Main polling loop orchestration
├── temperature.py   # CPU temperature reading + smoothing
├── pwm.py           # Hardware PWM output via pigpio
├── curve.py         # Fan speed curve + hysteresis logic
├── config.py        # Configuration loading + validation
└── logger.py        # Logging setup (stdout → journald)
```

**Data flow per tick:**

```
read temperature → smooth → evaluate curve (with hysteresis) → update PWM (if changed) → log (if changed)
```

## Hardware Requirements

- Raspberry Pi 4 Model B (or any Pi with hardware PWM support)
- 4-pin PWM fan (e.g., Noctua NF-A4x10 5V PWM)
- Fan connected to GPIO18 (BCM numbering, physical pin 12)

### GPIO Wiring

| Fan Wire | Connect To         |
|----------|--------------------|
| GND      | Pi GND (pin 6)     |
| +5V      | Pi 5V (pin 4)      |
| PWM      | Pi GPIO18 (pin 12) |
| Tach     | Not used           |

> **Note:** GPIO18 is one of the two hardware PWM-capable pins on the Raspberry Pi (the other is GPIO12/13/19). Hardware PWM is required for a stable 25 kHz signal — software PWM cannot reliably achieve this frequency.

## Installation

### Prerequisites

- Raspberry Pi OS (or any Debian-based distro)
- Python 3.9+
- `pigpio` library and daemon

### Quick Install

```bash
git clone https://github.com/carlos/raspi-fan-control.git
cd raspi-fan-control
sudo ./install.sh
```

The installer will:
1. Install `pigpio`, `python3-pigpio`, and `python3-yaml` via apt
2. Enable and start the `pigpiod` daemon
3. Copy the application to `/opt/raspifanctl/`
4. Install the default config to `/etc/raspifanctl/config.yaml` (if it doesn't already exist)
5. Install and enable the systemd service

### Start the Service

```bash
sudo systemctl start raspifanctl
```

### Manual Install

If you prefer to install manually:

```bash
# Install dependencies
sudo apt install pigpio python3-pigpio python3-yaml
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

# Copy files
sudo mkdir -p /opt/raspifanctl /etc/raspifanctl
sudo cp -r src/ /opt/raspifanctl/
sudo cp config/default.yaml /etc/raspifanctl/config.yaml
sudo cp systemd/raspifanctl.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable raspifanctl
sudo systemctl start raspifanctl
```

## Configuration

Edit `/etc/raspifanctl/config.yaml`:

```yaml
# Polling interval in seconds
poll_interval: 60

# Hysteresis margin in °C
hysteresis: 3

# PWM frequency in Hz (25 kHz = 4-pin fan standard)
pwm_frequency: 25000

# GPIO pin (BCM numbering)
gpio_pin: 18

# Moving average window size
smoothing_window: 5

# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
log_level: INFO

# Temperature warning threshold
critical_temp: 80

# Fan curve: [temperature_°C, fan_speed_%]
curve:
  - [45, 0]    # Below 45°C: fan off
  - [55, 30]   # 55°C+: 30% speed
  - [63, 50]   # 63°C+: 50% speed
  - [70, 75]   # 70°C+: 75% speed
  - [75, 100]  # 75°C+: full speed
```

The daemon works with no config file at all — all values have safe built-in defaults.

### Thermal Policy

The default curve keeps the fan off under light loads (below 45°C) and progressively increases speed as the CPU heats up. At 75°C the fan runs at full speed to prevent thermal throttling (which typically begins at 80°C on the Pi 4).

### Hysteresis Explained

Without hysteresis, a CPU hovering at exactly 55°C would cause the fan to constantly toggle between off and 30% — creating audible cycling and unnecessary wear.

With a hysteresis of 3°C:
- Fan activates at 55°C → 30%
- Temperature drops to 54°C → fan **stays** at 30%
- Temperature drops to 51°C (below 55 - 3) → fan turns off

This creates a stable dead-zone around each threshold.

### Smoothing

CPU temperatures can spike briefly during burst workloads. The smoothing window (default: 5 readings) computes a moving average, preventing the fan from reacting to transient spikes and instead responding to sustained temperature trends.

## systemd Operations

```bash
# Service management
sudo systemctl start raspifanctl
sudo systemctl stop raspifanctl
sudo systemctl restart raspifanctl
sudo systemctl status raspifanctl

# Enable/disable boot startup
sudo systemctl enable raspifanctl
sudo systemctl disable raspifanctl

# View logs
journalctl -u raspifanctl -f          # Follow live
journalctl -u raspifanctl --since today  # Today's logs
journalctl -u raspifanctl -n 50       # Last 50 lines
```

## Safety Notes

### Fail-Safe Behavior

The daemon is designed with a **fan-on-by-default** safety philosophy:

1. **On startup:** Fan runs at 100% until the first temperature reading is processed
2. **On shutdown (SIGTERM/SIGINT):** Fan is set to 100% before the process exits
3. **On crash:** The PWM shutdown handler sets the fan to 100%
4. **On control loop error:** Fan is set to 100% and the loop continues

The fan should **never** be left off due to a software failure.

### Configuration Validation

The config loader rejects dangerous values:
- PWM frequency outside 1–50 kHz
- Temperatures outside 20–100°C
- Unsorted or malformed curve entries
- Critical temp below 50°C

### pigpiod Dependency

The systemd service declares `Requires=pigpiod.service` — if `pigpiod` fails to start, the fan controller won't start either, and systemd will attempt to restart both.

## Troubleshooting

### "Failed to connect to pigpio daemon"

```bash
sudo systemctl status pigpiod
sudo systemctl start pigpiod
```

### Fan doesn't spin

1. Verify wiring — check GND, 5V, and PWM connections
2. Test manually: `pigs p 18 128` (sets GPIO18 to ~50% duty)
3. Check that GPIO18 isn't in use by another service (e.g., audio)

### Fan runs at 100% constantly

This is the fail-safe behavior. Check logs for errors:

```bash
journalctl -u raspifanctl -n 100
```

### Service won't start

```bash
sudo systemctl status raspifanctl
# Check for config validation errors in the output
```

### Disable on-board audio (if GPIO18 conflicts)

GPIO18 is shared with the PWM audio output. If you're running headless, this isn't an issue. Otherwise, add to `/boot/config.txt`:

```
dtparam=audio=off
```

## License

MIT — see [LICENSE](LICENSE).
