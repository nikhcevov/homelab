#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

if [ -f /var/run/reboot-required ]; then
	notify_transition "reboot-required" "pending" "warning" "Updates" "reboot required" \
		"Reboot required after package updates" \
		"The reboot-required marker is present." \
		"Schedule a maintenance reboot."
else
	clear_state "reboot-required"
fi
