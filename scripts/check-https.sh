#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

HTTPS_ENDPOINTS="${HTTPS_ENDPOINTS:-}"

if [ -z "$HTTPS_ENDPOINTS" ]; then
    exit 0
fi

check_endpoint() {
    local url=$1
    local key
    key="https-$(echo "$url" | tr '/:?&=' '-----')"

    # "any:" prefix = chain health only: any HTTP status counts as up
    # (000 = DNS/cert/Caddy/backend broken). For endpoints where a bare
    # URL legitimately returns 4xx (e.g. 3x-ui subscription path).
    if [[ "$url" == any:* ]]; then
        url="${url#any:}"
        local code
        code=$(curl --silent --output /dev/null --write-out '%{http_code}' \
            --location --max-time 10 "$url" || echo "000")
        if [ "$code" != "000" ]; then
            notify_transition "$key" "up" "info" \
                "Endpoint recovered" "white_check_mark,satellite" \
                "✅ $url is UP from $HOSTNAME"
        else
            notify_transition "$key" "down" "critical" \
                "Endpoint down" "rotating_light,satellite" \
                "❌ $url is UNREACHABLE from $HOSTNAME"
        fi
        return
    fi

    if curl --fail --silent --show-error --location --max-time 10 \
        --retry 1 --output /dev/null "$url"; then
        notify_transition "$key" "up" "info" \
            "Endpoint recovered" "white_check_mark,satellite" \
            "✅ $url is UP from $HOSTNAME"
    else
        notify_transition "$key" "down" "critical" \
            "Endpoint down" "rotating_light,satellite" \
            "❌ $url is UNREACHABLE from $HOSTNAME"
    fi
}

for URL in $HTTPS_ENDPOINTS; do
    check_endpoint "$URL"
done
