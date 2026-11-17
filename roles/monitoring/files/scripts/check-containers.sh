#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

CHECK_CONTAINERS="${CHECK_CONTAINERS:-}"

if [ -z "$CHECK_CONTAINERS" ]; then
	exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
	notify_transition "docker-missing" "down" "warning" "Docker" "CLI missing" \
		"Docker CLI is not installed" \
		"\`CHECK_CONTAINERS\` is configured but \`docker\` is unavailable." \
		"Install Docker or clear the container list for this host."
	exit 0
fi

check_container() {
	local name=$1
	local key="container-$name"

	local status
	status=$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || echo "missing")

	case "$status" in
	running)
		notify_transition "$key" "up" "resolved" "Docker" "$name running" \
			"Container \`$name\` is running again"
		;;
	missing)
		notify_transition "$key" "missing" "critical" "Docker" "$name missing" \
			"Container \`$name\` was not found" \
			"The container is absent from the Docker daemon." \
			"Inspect \`docker ps -a\` and the Compose stack."
		;;
	*)
		notify_transition "$key" "down" "critical" "Docker" "$name stopped" \
			"Container \`$name\` is not running" \
			"Current state: \`$status\`." \
			"Inspect \`docker logs $name\` and the Compose stack."
		;;
	esac
}

for CONTAINER in $CHECK_CONTAINERS; do
	check_container "$CONTAINER"
done
