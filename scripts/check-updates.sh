#!/bin/bash

source /opt/homelab-monitoring/.env

HOSTNAME=$(hostname)

apt update -qq >/dev/null 2>&1

TOTAL=$(apt list --upgradable 2>/dev/null | tail -n +2 | wc -l)
SECURITY=$(apt list --upgradable 2>/dev/null | grep -i security | wc -l)

if [ "$TOTAL" -eq 0 ]; then
    exit 0
fi

if [ "$SECURITY" -gt 0 ]; then
    PRIORITY="high"
    EMOJI="🚨"
else
    PRIORITY="default"
    EMOJI="📦"
fi

MESSAGE="$EMOJI VPS updates available

Host: $HOSTNAME
Packages: $TOTAL
Security: $SECURITY"

curl -s \
  -H "Title: VPS Updates" \
  -H "Priority: $PRIORITY" \
  -H "Tags: warning,update" \
  -d "$MESSAGE" \
  https://ntfy.sh/$TOPIC >/dev/null