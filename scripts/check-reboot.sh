#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

if [ -f /var/run/reboot-required ]; then
	send_ntfy "Reboot Required" "high" "warning,restart" "🔄 VPS reboot required on $HOSTNAME"
fi
