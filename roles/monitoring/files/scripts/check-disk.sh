#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

: "${DISK_THRESHOLD:?DISK_THRESHOLD is required}"
: "${DISK_MOUNTS:?DISK_MOUNTS is required}"

check_mount() {
	local mount=$1
	local key
	key="disk$(echo "$mount" | tr '/' '-')"

	local usage
	usage=$(df -P "$mount" 2>/dev/null | awk 'NR==2 {gsub("%",""); print $5}')

	if [ -z "$usage" ]; then
		return 0
	fi

	if [ "$usage" -ge "$DISK_THRESHOLD" ]; then
		notify_transition "$key" "high" "warning" "Disk" "$mount at ${usage}%" \
			"Disk usage is high on \`$mount\`" \
			"Usage: \`${usage}%\`; threshold: \`${DISK_THRESHOLD}%\`." \
			"Free space or lower the threshold deliberately."
	else
		clear_state "$key"
	fi
}

for MOUNT in $DISK_MOUNTS; do
	check_mount "$MOUNT"
done
