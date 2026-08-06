#!/bin/bash
#name=Homelab backup pull
#description=Pull homelab backups over tailnet into /mnt/user/backup/homelab
#arrayStarted=true
#
# homelab-backup-pull — central backup collector for Unraid.
#
# Install (Unraid):
#   1. Settings -> User Scripts -> Add New Script -> paste this file.
#   2. Schedule: daily (e.g. "0 5 * * *" custom cron).
#   3. Generate a key and put its .pub into this repo:
#        ssh-keygen -t ed25519 -C "great-hornbill"
#      -> files/ssh/great-hornbill.pub, referenced from ssh_authorized_keys
#      (routers) and bootstrap_root_ssh_keys (VPS groups). One key serves
#      both ansible deploys and this script: the privileges are identical
#      anyway (root SSH to the same hosts), splitting buys nothing.
#
# Pull model on purpose: hosts never get credentials for Unraid, so a
# compromised host cannot delete or encrypt its own backups.

set -uo pipefail

# --- config ---------------------------------------------------------------
SSH_KEY="/root/.ssh/id_ed25519"
DEST="/mnt/user/backup/homelab"
RETENTION_DAYS=30

# Subfolders are named explicitly: tailscale IPs can change, names must
# not. VPS hosts: rsync the archives dir produced by the *_backup roles.
# Format: "<name>|<tailscale-ip>|<remote-dir>"
RSYNC_SOURCES=(
	"vpn-nl|100.100.146.5|/opt/vpn-backup/archives/"
	"mon-1|100.107.77.74|/opt/kuma-backup/archives/"
)

# OpenWrt routers: config backup streamed via sysupgrade -b over SSH.
# Format: "<name>|<tailscale-ip>"
ROUTERS=(
	"router-alm|100.102.172.25"
	# "router-krm|100.84.111.78"
)
# --------------------------------------------------------------------------

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -i "$SSH_KEY")
DATE=$(date +%F)
LOG_TAG="homelab-backup-pull"

log() { echo "[$LOG_TAG] $*"; logger -t "$LOG_TAG" "$*"; }

mkdir -p "$DEST"

# --- VPS artifacts (rsync mirror; source-side rotation applies) ---
for entry in "${RSYNC_SOURCES[@]}"; do
	IFS='|' read -r name host dir <<<"$entry"
	target="$DEST/$name"
	mkdir -p "$target"
	if rsync -a --delete -e "ssh ${SSH_OPTS[*]}" "root@$host:$dir" "$target/" >>/dev/null 2>&1; then
		log "OK rsync $name ($host:$dir) -> $target"
	else
		log "FAIL rsync $name ($host)"
	fi
done

# --- OpenWrt routers (dated tarballs + local retention) ---
for entry in "${ROUTERS[@]}"; do
	IFS='|' read -r name host <<<"$entry"
	target="$DEST/$name"
	mkdir -p "$target"
	file="$target/sysupgrade-${DATE}.tar.gz"
	if ssh "${SSH_OPTS[@]}" "root@$host" \
		'sysupgrade -b /tmp/backup-pull.tar.gz && cat /tmp/backup-pull.tar.gz && rm -f /tmp/backup-pull.tar.gz' \
		>"$file" 2>/dev/null && [ -s "$file" ]; then
		log "OK router $name -> $file"
	else
		rm -f "$file"
		log "FAIL router $name ($host)"
	fi
	find "$target" -name 'sysupgrade-*.tar.gz' -mtime "+$RETENTION_DAYS" -delete
done

log "done"
