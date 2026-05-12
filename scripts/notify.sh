#!/bin/bash
set -euo pipefail

ENV_FILE="/opt/homelab-monitoring/.env"
STATE_DIR="/var/lib/homelab-monitoring"

if [ ! -f "$ENV_FILE" ]; then
	echo "Missing env file: $ENV_FILE" >&2
	exit 1
fi

set -a
source "$ENV_FILE"
set +a

: "${NTFY_URL:?NTFY_URL is required}"
: "${NTFY_TOPIC_CRITICAL:?NTFY_TOPIC_CRITICAL is required}"
: "${NTFY_TOPIC_ALERTS:?NTFY_TOPIC_ALERTS is required}"
: "${NTFY_TOPIC_INFO:?NTFY_TOPIC_INFO is required}"

HOST_PREFIX="${HOST_PREFIX:-[VPS]}"

mkdir -p "$STATE_DIR"

_ntfy_endpoint_for() {
	local severity=$1
	case "$severity" in
	critical) echo "${NTFY_URL%/}/$NTFY_TOPIC_CRITICAL" ;;
	alert) echo "${NTFY_URL%/}/$NTFY_TOPIC_ALERTS" ;;
	info) echo "${NTFY_URL%/}/$NTFY_TOPIC_INFO" ;;
	*)
		echo "Unknown severity: $severity" >&2
		return 1
		;;
	esac
}

_ntfy_priority_for() {
	local severity=$1
	case "$severity" in
	critical) echo "urgent" ;;
	alert) echo "high" ;;
	info) echo "default" ;;
	esac
}

send_ntfy() {
	local severity=$1
	local title=$2
	local tags=$3
	local message=$4

	local endpoint priority
	endpoint=$(_ntfy_endpoint_for "$severity")
	priority=$(_ntfy_priority_for "$severity")

	curl --fail --show-error --silent --max-time 10 --retry 2 \
		-H "Title: $HOST_PREFIX $title" \
		-H "Priority: $priority" \
		-H "Tags: $tags" \
		-d "$message" \
		"$endpoint" >/dev/null
}

_is_healthy_state() {
	case "$1" in
	up | ok | clean | clear) return 0 ;;
	*) return 1 ;;
	esac
}

notify_transition() {
	local key=$1
	local status=$2
	local severity=$3
	local title=$4
	local tags=$5
	local message=$6

	local file="$STATE_DIR/$key.state"
	local prev=""
	[ -f "$file" ] && prev=$(cat "$file")

	if [ "$prev" = "$status" ]; then
		return 0
	fi

	if [ -z "$prev" ] && _is_healthy_state "$status"; then
		echo "$status" >"$file"
		return 0
	fi

	send_ntfy "$severity" "$title" "$tags" "$message"
	echo "$status" >"$file"
}

clear_state() {
	local key=$1
	rm -f "$STATE_DIR/$key.state"
}
