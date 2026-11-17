#!/bin/bash
set -euo pipefail

ENV_FILE="${NTFY_ENV_FILE:-/opt/homelab-monitoring/.env}"
STATE_DIR="${NTFY_STATE_DIR:-/var/lib/homelab-monitoring}"

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

HOSTNAME=$(hostname)
mkdir -p "$STATE_DIR"

_ntfy_endpoint_for() {
	local severity=$1
	case "$severity" in
	critical) echo "${NTFY_URL%/}/$NTFY_TOPIC_CRITICAL" ;;
	alert | warning) echo "${NTFY_URL%/}/$NTFY_TOPIC_ALERTS" ;;
	info | resolved | test) echo "${NTFY_URL%/}/$NTFY_TOPIC_INFO" ;;
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
	alert | warning) echo "high" ;;
	info | resolved | test) echo "default" ;;
	esac
}

_ntfy_emoji_for() {
	local severity=$1
	case "$severity" in
	critical) echo "🚨" ;;
	alert | warning) echo "⚠️" ;;
	resolved) echo "✅" ;;
	info) echo "ℹ️" ;;
	test) echo "🧪" ;;
	esac
}

_ntfy_tag_for() {
	local severity=$1
	case "$severity" in
	critical) echo "rotating_light" ;;
	alert | warning) echo "warning" ;;
	resolved) echo "white_check_mark" ;;
	info) echo "information_source" ;;
	test) echo "test_tube" ;;
	esac
}

send_ntfy() {
	local severity=$1
	local component=$2
	local event=$3
	local summary=$4
	local details=${5:-}
	local action=${6:-}

	local endpoint priority emoji severity_tag component_tag title message
	endpoint=$(_ntfy_endpoint_for "$severity")
	priority=$(_ntfy_priority_for "$severity")
	emoji=$(_ntfy_emoji_for "$severity")
	severity_tag=$(_ntfy_tag_for "$severity")
	component_tag=$(printf '%s' "$component" | tr '[:upper:]' '[:lower:]')

	title="$emoji Homelab · $component · $event"
	message="**$summary**

- **Host:** \`$HOSTNAME\`
- **Component:** \`$component\`
- **State:** \`$event\`"

	if [ -n "$details" ]; then
		message+=$'\n'"- **Details:** $details"
	fi
	if [ -n "$action" ]; then
		message+=$'\n'"- **Action:** $action"
	fi

	curl --fail --show-error --silent --max-time 10 --retry 2 \
		-H "Title: $title" \
		-H "Priority: $priority" \
		-H "Tags: $severity_tag,$component_tag" \
		-H "Markdown: yes" \
		-d "$message" \
		"$endpoint" >/dev/null
}

_is_healthy_state() {
	case "$1" in
	up | ok | clean | clear | recovered) return 0 ;;
	*) return 1 ;;
	esac
}

notify_transition() {
	local key=$1
	local status=$2
	local severity=$3
	local component=$4
	local event=$5
	local summary=$6
	local details=${7:-}
	local action=${8:-}

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

	send_ntfy "$severity" "$component" "$event" "$summary" "$details" "$action"
	echo "$status" >"$file"
}

clear_state() {
	local key=$1
	rm -f "$STATE_DIR/$key.state"
}
