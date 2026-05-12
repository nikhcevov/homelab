#!/bin/bash

source /opt/homelab-monitoring/.env

HOSTNAME=$(hostname)

if [ -f /var/run/reboot-required ]; then

curl -s \
  -H "Title: Reboot Required" \
  -H "Priority: high" \
  -H "Tags: warning,restart" \
  -d "🔄 VPS reboot required on $HOSTNAME" \
  https://ntfy.sh/$TOPIC >/dev/null

fi