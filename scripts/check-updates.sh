#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

if ! apt update -qq >/dev/null 2>&1; then
	send_ntfy "APT Update Failed" "high" "warning,package" "❌ apt update failed on $HOSTNAME"
	exit 1
fi

UPGRADABLE=$(apt list --upgradable 2>/dev/null | tail -n +2)
TOTAL=$(printf "%s\n" "$UPGRADABLE" | sed '/^$/d' | wc -l | tr -d ' ')
SECURITY=$(printf "%s\n" "$UPGRADABLE" | grep -ci security || true)

if [ "$TOTAL" -eq 0 ]; then
	exit 0
fi

if [ "$SECURITY" -gt 0 ]; then
	PRIORITY="high"
	EMOJI="🚨"
else
	PRIORITY="default"
	EMOJI="📦"
fi

MESSAGE="$EMOJI VPS updates available

Host: $HOSTNAME
Packages: $TOTAL
Security: $SECURITY"

send_ntfy "VPS Updates" "$PRIORITY" "warning,update" "$MESSAGE"
