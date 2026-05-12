#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

HTTPS_ENDPOINTS="${HTTPS_ENDPOINTS:-}"

if [ -z "$HTTPS_ENDPOINTS" ]; then
	exit 0
fi

check_endpoint() {
	local url=$1
	local key
	key="https-$(echo "$url" | tr '/:?&=' '-----')"

	if curl --fail --silent --show-error --location --max-time 10 \
		--retry 1 --output /dev/null "$url"; then
		notify_transition "$key" "up" "info" \
			"Endpoint recovered" "white_check_mark,satellite" \
			"✅ $url is UP from $HOSTNAME"
	else
		notify_transition "$key" "down" "critical" \
			"Endpoint down" "rotating_light,satellite" \
			"❌ $url is UNREACHABLE from $HOSTNAME"
	fi
}

for URL in $HTTPS_ENDPOINTS; do
	check_endpoint "$URL"
done
