#!/bin/bash
set -euo pipefail

INSTALL_DIR="/opt/homelab-monitoring"
STATE_DIR="/var/lib/homelab-monitoring"
CRON_FILE="/etc/cron.d/homelab-monitoring"
NGINX_CONF="/etc/nginx/nginx.conf"
NGINX_STREAM_DIR="/etc/nginx/stream.d"

if [ "$EUID" -ne 0 ]; then
	echo "Run as root: sudo ./install.sh" >&2
	exit 1
fi

step() {
	echo ""
	echo "[$1] $2"
}

step 1/9 "Creating install directory..."
mkdir -p "$INSTALL_DIR"

step 2/9 "Creating state directory..."
mkdir -p "$STATE_DIR"

step 3/9 "Copying scripts and configs..."
cp -r scripts "$INSTALL_DIR/"
cp -r cron "$INSTALL_DIR/" || true
cp -r nginx "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR"/scripts/*.sh
chmod +x "$INSTALL_DIR"/nginx/render-stream.sh

step 4/9 "Installing env config..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
	cp .env.example "$INSTALL_DIR/.env"
	echo "Created default .env"
else
	echo ".env already exists, keeping existing config"
fi

if grep -q CHANGEME "$INSTALL_DIR/.env"; then
	echo "WARNING: $INSTALL_DIR/.env still contains CHANGEME placeholders." >&2
	echo "         Edit it before relying on the deployment." >&2
fi

step 5/9 "Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y curl nginx >/dev/null

step 6/9 "Deploying nginx config..."
install -m 0644 "$INSTALL_DIR/nginx/nginx.conf" "$NGINX_CONF"
mkdir -p "$NGINX_STREAM_DIR"
ENV_FILE="$INSTALL_DIR/.env" OUT_DIR="$NGINX_STREAM_DIR" \
	"$INSTALL_DIR/nginx/render-stream.sh"

step 7/9 "Validating and reloading nginx..."
nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl reload nginx 2>/dev/null || systemctl restart nginx

step 8/9 "Installing cron jobs..."
install -m 0644 cron/homelab-monitoring.cron "$CRON_FILE"

step 9/9 "Restarting cron..."
systemctl restart cron

echo ""
echo "=================================="
echo "homelab-vps-proxy installed"
echo "Config:     $INSTALL_DIR/.env"
echo "Nginx:      $NGINX_CONF"
echo "Streams:    $NGINX_STREAM_DIR"
echo "State:      $STATE_DIR"
echo "=================================="
