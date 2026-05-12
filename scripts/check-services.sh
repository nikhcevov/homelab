#!/bin/bash

source /opt/homelab-monitoring/.env

HOSTNAME=$(hostname)

check_service () {

SERVICE=$1

if ! systemctl is-active --quiet "$SERVICE"; then

curl -s \
  -H "Title: Service Down" \
  -H "Priority: urgent" \
  -H "Tags: rotating_light,server" \
  -d "❌ Service '$SERVICE' is DOWN on $HOSTNAME" \
  https://ntfy.sh/$TOPIC >/dev/null

fi
}

check_service nginx
check_service tailscaled