#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

: "${CHECK_SERVICES:?CHECK_SERVICES is required}"

check_service() {
	local service=$1
	local key="service-$service"

	if systemctl is-active --quiet "$service"; then
		notify_transition "$key" "up" "info" \
			"Service recovered" "white_check_mark,server" \
			"✅ Service '$service' RECOVERED on $HOSTNAME"
	else
		notify_transition "$key" "down" "critical" \
			"Service down" "rotating_light,server" \
			"❌ Service '$service' is DOWN on $HOSTNAME"
	fi
}

for SERVICE in $CHECK_SERVICES; do
	check_service "$SERVICE"
done
