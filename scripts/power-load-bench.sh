#!/usr/bin/env bash
# Load power benchmark (docs/laptop-power-article-draft.md).
#
# Fixed-work test: encode N seconds of synthetic 1080p30 video with
# libx264 (CPU-bound, no disk dependency). Compares profiles by the only
# honest metric under load: ENERGY PER TASK (Wh), not instant watts —
# power-saver runs slower, so comparing just watts is misleading.
#
# Usage: power-load-bench.sh [video_seconds]   (default: 60)
#
# Conditions: unplug AC, same brightness, same desktop state for every
# profile run. Baseline desktop load is included in all runs equally.
set -u

BAT="${BAT:-BAT0}"
SYS="/sys/class/power_supply/$BAT"
DURATION="${1:-60}"

status="$(cat "$SYS/status")"
if [ "$status" != "Discharging" ]; then
    echo "Battery status is '$status' — unplug AC first." >&2
    exit 1
fi

echo "Workload: libx264 encode of ${DURATION}s synthetic 1080p30 (fixed work)"
ffmpeg -hide_banner -loglevel error \
    -f lavfi -i "testsrc2=size=1920x1080:rate=30:duration=$DURATION" \
    -c:v libx264 -preset medium -f null - &
pid=$!

sum=0; n=0; t0=$SECONDS
while kill -0 "$pid" 2>/dev/null; do
    v="$(cat "$SYS/power_now")"
    sum=$((sum + v)); n=$((n + 1))
    sleep 1
done
wait "$pid" || { echo "ffmpeg failed" >&2; exit 1; }
dt=$((SECONDS - t0))
avg=$((sum / n))

awk "BEGIN{
    w = $avg/1000000
    printf \"\\n== Result ==\n\"
    printf \"time:   %d s\n\", $dt
    printf \"avg:    %.2f W  (%d samples)\n\", w, $n
    printf \"energy: %.4f Wh for the task\n\", w*$dt/3600
    printf \"profile: %s\n\", \"$(powerprofilesctl get 2>/dev/null || echo n/a)\"
}"
