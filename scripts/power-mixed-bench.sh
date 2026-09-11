#!/usr/bin/env bash
# Mixed fixed-TIME power benchmark (docs/laptop-power-article-draft.md).
#
# Simulates bursty real-world work: every 60 s cycle = one load burst
# (encode ~20 s of synthetic 1080p30 via libx264) + idle for the rest of
# the cycle. All profiles run the SAME wall-clock duration, so the
# comparison metric is plain average watts — faster profiles finish each
# burst sooner and fall back to idle longer (race-to-idle), slower ones
# spend more of the window under load. That tension is exactly what this
# bench measures.
#
# Usage: power-mixed-bench.sh [total_seconds]   (default: 600)
#
# Conditions: unplug AC, same brightness and desktop state across runs.
set -u

BAT="${BAT:-BAT0}"
SYS="/sys/class/power_supply/$BAT"
TOTAL="${1:-600}"
CYCLE=60            # burst + idle per cycle, seconds
BURST_VIDEO_S=20    # burst workload size (encode N seconds of video)
POWER_NOW_FILE="${POWER_NOW_FILE:-$SYS/power_now}"

if [ -z "${POWER_NOW_FILE:-}" ] || [ "$POWER_NOW_FILE" = "$SYS/power_now" ]; then
    status="$(cat "$SYS/status")"
    if [ "$status" != "Discharging" ]; then
        echo "Battery status is '$status' — unplug AC first." >&2
        exit 1
    fi
fi

echo "Mixed bench: ${TOTAL}s total, 60s cycles (burst ~${BURST_VIDEO_S}s video + idle)"
echo "Profile: $(powerprofilesctl get 2>/dev/null || echo n/a)"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

# Background sampler: one power_now reading per second for TOTAL seconds.
(
    end=$((SECONDS + TOTAL))
    while [ "$SECONDS" -lt "$end" ]; do
        cat "$POWER_NOW_FILE"
        sleep 1
    done
) > "$tmp" &
sampler=$!

end=$((SECONDS + TOTAL))
while [ "$SECONDS" -lt "$end" ]; do
    cycle_start=$SECONDS
    ffmpeg -hide_banner -loglevel error \
        -f lavfi -i "testsrc2=size=1920x1080:rate=30:duration=$BURST_VIDEO_S" \
        -c:v libx264 -preset medium -f null -
    rest=$((CYCLE - (SECONDS - cycle_start)))
    [ "$rest" -gt 0 ] && [ $((SECONDS + rest)) -le "$end" ] && sleep "$rest"
done
wait "$sampler"

awk -v total="$TOTAL" '
    { sum += $1; n++ }
    END {
        w = sum/n/1000000
        printf "\n== Result ==\n"
        printf "elapsed: %d s, samples: %d\n", total, n
        printf "avg:     %.2f W\n", w
        printf "energy:  %.4f Wh over the window\n", w*total/3600
    }
' "$tmp"
