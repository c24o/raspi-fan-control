#!/usr/bin/env bash
#
# install.sh — Install raspi-fan-control on a Raspberry Pi
#
# Usage:  sudo ./install.sh
#
set -euo pipefail

INSTALL_DIR="/opt/raspifanctl"
CONFIG_DIR="/etc/raspifanctl"
SERVICE_FILE="/etc/systemd/system/raspifanctl.service"

# -------------------------------------------------------
# Pre-flight checks
# -------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (sudo ./install.sh)"
    exit 1
fi

echo "==> Installing raspi-fan-control"

# -------------------------------------------------------
# Dependencies
# -------------------------------------------------------
echo "  -> Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq pigpio python3-pigpio python3-yaml > /dev/null

# Enable and start pigpiod if not already running.
if ! systemctl is-active --quiet pigpiod; then
    echo "  -> Enabling pigpiod..."
    systemctl enable pigpiod
    systemctl start pigpiod
fi

# -------------------------------------------------------
# Application files
# -------------------------------------------------------
echo "  -> Copying application to ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}/src"
cp src/*.py "${INSTALL_DIR}/src/"

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------
if [[ ! -f "${CONFIG_DIR}/config.yaml" ]]; then
    echo "  -> Installing default configuration to ${CONFIG_DIR}/config.yaml..."
    mkdir -p "${CONFIG_DIR}"
    cp config/default.yaml "${CONFIG_DIR}/config.yaml"
else
    echo "  -> Configuration already exists at ${CONFIG_DIR}/config.yaml — skipping"
fi

# -------------------------------------------------------
# Systemd service
# -------------------------------------------------------
echo "  -> Installing systemd service..."
cp systemd/raspifanctl.service "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable raspifanctl

echo ""
echo "==> Installation complete!"
echo ""
echo "  Start now:   sudo systemctl start raspifanctl"
echo "  View logs:   journalctl -u raspifanctl -f"
echo "  Edit config: sudo nano ${CONFIG_DIR}/config.yaml"
echo ""
