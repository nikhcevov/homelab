#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

CHECK_CONTAINERS="${CHECK_CONTAINERS:-}"

if [ -z "$CHECK_CONTAINERS" ]; then
	exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
	notify_transition "docker-missing" "down" "alert" \
		"Docker missing" "warning,whale" \
		"⚠️ docker CLI not found on $HOSTNAME but CHECK_CONTAINERS is set"
	exit 0
fi

check_container() {
	local name=$1
	local key="container-$name"

	local status
	status=$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || echo "missing")

	case "$status" in
	running)
		notify_transition "$key" "up" "info" \
			"Container recovered" "white_check_mark,whale" \
			"✅ Container '$name' RUNNING on $HOSTNAME"
		;;
	missing)
		notify_transition "$key" "missing" "alert" \
			"Container missing" "warning,whale" \
			"⚠️ Container '$name' NOT FOUND on $HOSTNAME"
		;;
	*)
		notify_transition "$key" "down" "alert" \
			"Container stopped" "warning,whale" \
			"⚠️ Container '$name' is $status on $HOSTNAME"
		;;
	esac
}

for CONTAINER in $CHECK_CONTAINERS; do
	check_container "$CONTAINER"
done
