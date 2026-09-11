#!/usr/bin/env bash
# Idle power-draw benchmark + power-knob snapshot (docs/laptop-power.md).
#
# Usage: power-idle-bench.sh [samples] [interval_s]   (default: 15 x 2s)
#
# Conditions matter: unplug AC, keep the same brightness, close heavy
# apps, let the desktop settle ~1 min, then run. Compare only runs taken
# under the same conditions.
set -u

BAT="${BAT:-BAT0}"
SYS="/sys/class/power_supply/$BAT"
SAMPLES="${1:-15}"
INTERVAL="${2:-2}"

status="$(cat "$SYS/status")"
if [ "$status" != "Discharging" ]; then
    echo "Battery status is '$status' — unplug AC and wait a few seconds." >&2
    exit 1
fi

echo "Sampling $SYS/power_now: ${SAMPLES}x every ${INTERVAL}s ..."
sum=0; min=""; max=""
for i in $(seq 1 "$SAMPLES"); do
    v="$(cat "$SYS/power_now")"
    sum=$((sum + v))
    [ -z "$min" ] || [ "$v" -lt "$min" ] && min="$v"
    [ -z "$max" ] || [ "$v" -gt "$max" ] && max="$v"
    [ "$i" -lt "$SAMPLES" ] && sleep "$INTERVAL"
done
avg=$((sum / SAMPLES))

to_w() { awk "BEGIN{printf \"%.2f\", $1/1000000}"; }

echo
echo "== Result =="
printf "avg: %s W   min: %s W   max: %s W   (samples: %s)\n" \
    "$(to_w "$avg")" "$(to_w "$min")" "$(to_w "$max")" "$SAMPLES"

echo
echo "== Knob snapshot =="
printf "profile:          %s\n" "$(powerprofilesctl get 2>/dev/null || echo n/a)"
printf "epp (cpu0):       %s\n" "$(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null || echo n/a)"
printf "cpu min/max pct:  %s/%s\n" "$(cat /sys/devices/system/cpu/intel_pstate/min_perf_pct 2>/dev/null || echo n/a)" "$(cat /sys/devices/system/cpu/intel_pstate/max_perf_pct 2>/dev/null || echo n/a)"
printf "no_turbo:         %s\n" "$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || echo n/a)"
printf "gpu min/max mhz:  %s/%s\n" "$(cat /sys/class/drm/card*/gt_min_freq_mhz 2>/dev/null | head -1 || echo n/a)" "$(cat /sys/class/drm/card*/gt_max_freq_mhz 2>/dev/null | head -1 || echo n/a)"
printf "sched_ext:        %s\n" "$(cat /sys/kernel/sched_ext/state 2>/dev/null || echo n/a)/$(cat /sys/kernel/sched_ext/root/ops 2>/dev/null || true)"
printf "aspm policy:      %s\n" "$(cat /sys/module/pcie_aspm/parameters/policy 2>/dev/null || echo n/a)"
printf "pci awake (on):   %s\n" "$(grep -l '^on$' /sys/bus/pci/devices/*/power/control 2>/dev/null | wc -l) devices"
printf "audio power_save: %s\n" "$(cat /sys/module/snd_hda_intel/parameters/power_save 2>/dev/null || echo n/a)"
wifi_ps="$(iw dev wlan0 get power_save 2>/dev/null | awk -F': ' '/Power save/{print $2}')"
printf "wifi powersave:   %s\n" "${wifi_ps:-n/a}"
printf "charge end:       %s\n" "$(cat "$SYS/charge_control_end_threshold" 2>/dev/null || echo n/a)"
printf "brightness:       %s/%s\n" "$(cat /sys/class/backlight/*/brightness 2>/dev/null | head -1)" "$(cat /sys/class/backlight/*/max_brightness 2>/dev/null | head -1)"
