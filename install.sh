#!/bin/bash
set -e

INSTALL_DIR="/opt/homelab-monitoring"
CRON_FILE="/etc/cron.d/homelab-monitoring"

echo "[1/6] Creating install directory..."
mkdir -p "$INSTALL_DIR"

echo "[2/6] Copying scripts..."
cp -r scripts "$INSTALL_DIR/"
cp -r cron "$INSTALL_DIR/" || true

chmod +x "$INSTALL_DIR"/scripts/*.sh

echo "[3/6] Installing env config..."

if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp .env.example "$INSTALL_DIR/.env"
    echo "Created default .env"
else
    echo ".env already exists, keeping existing config"
fi

echo "[4/6] Installing dependencies..."
apt update -qq
apt install -y curl >/dev/null

echo "[5/6] Installing cron jobs..."
cp cron/homelab-monitoring.cron "$CRON_FILE"

chmod 644 "$CRON_FILE"

echo "[6/6] Reloading cron..."
systemctl reload cron || true

echo ""
echo "=================================="
echo "Homelab monitoring installed"
echo "Config file:"
echo "$INSTALL_DIR/.env"
echo "=================================="