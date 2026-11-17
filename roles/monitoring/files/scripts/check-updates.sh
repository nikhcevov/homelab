#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

if ! apt-get update -qq >/dev/null 2>&1; then
	notify_transition "apt-update-failed" "failed" "warning" "Updates" "apt update failed" \
		"APT metadata refresh failed" \
		"\`apt-get update\` returned a non-zero exit code." \
		"Inspect APT sources and network reachability."
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

notify_transition "updates-available" "$STATE" "warning" "Updates" "${TOTAL} packages available" \
	"${TOTAL} package updates are available" \
	"Security updates: \`${SECURITY}\`; total: \`${TOTAL}\`." \
	"Review the list, then apply during a maintenance window."
