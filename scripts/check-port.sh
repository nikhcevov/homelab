#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

CHECK_PORTS="${CHECK_PORTS:-}"

if [ -z "$CHECK_PORTS" ]; then
    exit 0
fi

check_port() {
    local port=$1
    local key="port-$port"

    if timeout 5 bash -c "exec 3<>/dev/tcp/127.0.0.1/$port" 2>/dev/null; then
        notify_transition "$key" "up" "info" \
            "Port recovered" "white_check_mark,dart" \
            "✅ Port $port is OPEN again on $HOSTNAME"
    else
        notify_transition "$key" "down" "critical" \
            "Port closed" "rotating_light,dart" \
            "❌ Port $port is CLOSED on $HOSTNAME (service down or not listening)"
    fi
}

for PORT in $CHECK_PORTS; do
    check_port "$PORT"
done
