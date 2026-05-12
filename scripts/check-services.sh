#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

: "${CHECK_SERVICES:?CHECK_SERVICES is required}"

check_service() {
	local SERVICE=$1
	if ! systemctl is-active --quiet "$SERVICE"; then
		send_ntfy "Service Down" "urgent" "rotating_light,server" "❌ Service '$SERVICE' is DOWN on $HOSTNAME"
	fi
}

for SERVICE in $CHECK_SERVICES; do
	check_service "$SERVICE"
done
