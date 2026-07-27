#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

HOSTNAME=$(hostname)

BACKUP_DIR="${BACKUP_DIR:-}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-25}"

if [ -z "$BACKUP_DIR" ]; then
    exit 0
fi

KEY="backup-freshness"

newest=""
if [ -d "$BACKUP_DIR" ]; then
    newest=$(find "$BACKUP_DIR" -name 'vpn-backup-*.tar.gz' -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1)
fi

if [ -z "$newest" ]; then
    notify_transition "$KEY" "missing" "alert" \
        "No backups found" "warning,package" \
        "⚠️ No backup archives in $BACKUP_DIR on $HOSTNAME"
    exit 0
fi

now=$(date +%s)
age_h=$(((now - ${newest%.*}) / 3600))

if [ "$age_h" -gt "$BACKUP_MAX_AGE_HOURS" ]; then
    notify_transition "$KEY" "stale" "alert" \
        "Backup stale" "warning,package" \
        "⚠️ Latest backup is ${age_h}h old (max ${BACKUP_MAX_AGE_HOURS}h) on $HOSTNAME"
else
    notify_transition "$KEY" "ok" "info" \
        "Backup resumed" "white_check_mark,package" \
        "✅ Backups are fresh again on $HOSTNAME (latest ${age_h}h old)"
fi
