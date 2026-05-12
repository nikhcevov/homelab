#!/bin/bash
set -euo pipefail

ENV_FILE="/opt/homelab-monitoring/.env"

if [ ! -f "$ENV_FILE" ]; then
	echo "Missing env file: $ENV_FILE" >&2
	exit 1
fi

set -a
source "$ENV_FILE"
set +a

: "${NTFY_URL:?NTFY_URL is required}"
: "${NTFY_TOPIC:?NTFY_TOPIC is required}"

NTFY_ENDPOINT="${NTFY_URL%/}/$NTFY_TOPIC"

send_ntfy() {
	local title=$1
	local priority=$2
	local tags=$3
	local message=$4

	curl --fail --show-error --silent --max-time 10 --retry 2 \
		-H "Title: $title" \
		-H "Priority: $priority" \
		-H "Tags: $tags" \
		-d "$message" \
		"$NTFY_ENDPOINT" >/dev/null
}
