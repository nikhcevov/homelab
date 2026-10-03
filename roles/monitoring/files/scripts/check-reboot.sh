#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

if [ -f /var/run/reboot-required ]; then
	notify_transition "reboot-required" "pending" "alert" \
		"Reboot required" "warning,restart" \
		"🔄 VPS reboot required on $HOSTNAME"
else
	clear_state "reboot-required"
fi
