#!/bin/bash
set -euo pipefail

INSTALL_DIR="/opt/homelab-monitoring"
STATE_DIR="/var/lib/homelab-monitoring"
CRON_FILE="/etc/cron.d/homelab-monitoring"

if [ "$EUID" -ne 0 ]; then
	echo "Run as root: sudo ./install.sh" >&2
	exit 1
fi

echo "[1/7] Creating install directory..."
mkdir -p "$INSTALL_DIR"

echo "[2/7] Creating state directory..."
mkdir -p "$STATE_DIR"

echo "[3/7] Copying scripts..."
cp -r scripts "$INSTALL_DIR/"
cp -r cron "$INSTALL_DIR/" || true
chmod +x "$INSTALL_DIR"/scripts/*.sh

echo "[4/7] Installing env config..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
	cp .env.example "$INSTALL_DIR/.env"
	echo "Created default .env"
else
	echo ".env already exists, keeping existing config"
fi

if grep -q CHANGEME "$INSTALL_DIR/.env"; then
	echo "WARNING: $INSTALL_DIR/.env still contains CHANGEME placeholders." >&2
	echo "         Edit it before relying on notifications." >&2
fi

echo "[5/7] Installing dependencies..."
apt-get update -qq
apt-get install -y curl >/dev/null

echo "[6/7] Installing cron jobs..."
cp cron/homelab-monitoring.cron "$CRON_FILE"
chmod 644 "$CRON_FILE"

echo "[7/7] Restarting cron..."
systemctl restart cron

echo ""
echo "=================================="
echo "Homelab monitoring installed"
echo "Config file:"
echo "$INSTALL_DIR/.env"
echo "State dir:"
echo "$STATE_DIR"
echo "=================================="
