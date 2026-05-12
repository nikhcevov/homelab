#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

if ! apt-get update -qq >/dev/null 2>&1; then
	notify_transition "apt-update-failed" "failed" "alert" \
		"APT update failed" "warning,package" \
		"❌ apt-get update failed on $HOSTNAME"
	exit 1
fi

clear_state "apt-update-failed"

UPGRADABLE=$(apt list --upgradable 2>/dev/null | tail -n +2)
TOTAL=$(printf "%s\n" "$UPGRADABLE" | sed '/^$/d' | wc -l | tr -d ' ')
SECURITY=$(printf "%s\n" "$UPGRADABLE" | grep -ci security || true)

if [ "$TOTAL" -eq 0 ]; then
	clear_state "updates-available"
	exit 0
fi

STATE="updates-$TOTAL-$SECURITY"
EMOJI="📦"
if [ "$SECURITY" -gt 0 ]; then
	EMOJI="🚨"
fi

MESSAGE="$EMOJI Updates available

Host: $HOSTNAME
Packages: $TOTAL
Security: $SECURITY"

notify_transition "updates-available" "$STATE" "alert" \
	"Updates available" "warning,update" "$MESSAGE"
