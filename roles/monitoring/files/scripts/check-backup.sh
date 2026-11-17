#!/bin/bash
set -euo pipefail

source /opt/homelab-monitoring/scripts/notify.sh

BACKUP_DIR="${BACKUP_DIR:-}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-25}"

if [ -z "$BACKUP_DIR" ]; then
    exit 0
fi

KEY="backup-freshness"

newest=""
if [ -d "$BACKUP_DIR" ]; then
    newest=$(find "$BACKUP_DIR" -name '*-backup-*.tar.gz' -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1)
fi

if [ -z "$newest" ]; then
    notify_transition "$KEY" "missing" "warning" "Backup" "no archives" \
        "No backup archives found" \
        "Directory: \`$BACKUP_DIR\`" \
        "Check the backup timer and collector mount."
    exit 0
fi

now=$(date +%s)
age_h=$(((now - ${newest%.*}) / 3600))

if [ "$age_h" -gt "$BACKUP_MAX_AGE_HOURS" ]; then
    notify_transition "$KEY" "stale" "warning" "Backup" "stale ${age_h}h" \
        "Latest backup is ${age_h}h old" \
        "Directory: \`$BACKUP_DIR\`; maximum age: \`${BACKUP_MAX_AGE_HOURS}h\`" \
        "Inspect the backup timer and collector journal."
else
    notify_transition "$KEY" "ok" "resolved" "Backup" "fresh again" \
        "Backups are fresh again" \
        "Latest archive is ${age_h}h old."
fi
