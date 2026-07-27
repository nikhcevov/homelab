#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

CHECK_PORTS="${CHECK_PORTS:-}"

if [ -z "$CHECK_PORTS" ]; then
    exit 0
fi

check_port() {
    local target=$1
    local host port

    # "host:port" = remote check, bare "port" = localhost
    if [[ "$target" == *:* ]]; then
        host="${target%:*}"
        port="${target##*:}"
    else
        host="127.0.0.1"
        port="$target"
    fi

    local key="port-$host-$port"

    if timeout 5 bash -c "exec 3<>/dev/tcp/$host/$port" 2>/dev/null; then
        notify_transition "$key" "up" "info" \
            "Port recovered" "white_check_mark,dart" \
            "✅ $host:$port is OPEN again (checked from $HOSTNAME)"
    else
        notify_transition "$key" "down" "critical" \
            "Port closed" "rotating_light,dart" \
            "❌ $host:$port is CLOSED (checked from $HOSTNAME)"
    fi
}

for TARGET in $CHECK_PORTS; do
    check_port "$TARGET"
done
