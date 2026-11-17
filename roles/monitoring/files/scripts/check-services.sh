#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

: "${CHECK_SERVICES:?CHECK_SERVICES is required}"

check_service() {
	local service=$1
	local key="service-$service"

	if systemctl is-active --quiet "$service"; then
		notify_transition "$key" "up" "resolved" "Service" "$service recovered" \
			"Service \`$service\` is active again"
	else
		notify_transition "$key" "down" "critical" "Service" "$service down" \
			"Service \`$service\` is DOWN" \
			"The systemd unit is not active." \
			"Inspect \`systemctl status $service\` and its journal."
	fi
}

for SERVICE in $CHECK_SERVICES; do
	check_service "$SERVICE"
done
