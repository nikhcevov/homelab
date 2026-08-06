#!/bin/bash
#name=Homelab backup pull
#description=Pull homelab backups over tailnet into /mnt/user/backups/homelab
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
DEST="/mnt/user/backups/homelab"
RETENTION_DAYS=30

# VPS hosts: rsync the archives dir produced by the *_backup roles.
# Format: "<tailscale-ip-or-name>:<remote-dir>"
RSYNC_SOURCES=(
	# "100.x.x.x:/opt/vpn-backup/archives/"   # vpn-nl (fill after network.yml)
	"100.107.77.74:/opt/kuma-backup/archives/" # mon-1
)

# OpenWrt routers: config backup streamed via sysupgrade -b over SSH.
ROUTERS=(
	"100.102.172.25" # router-alm
	# "100.84.111.78" # router-krm
)
# --------------------------------------------------------------------------

SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -i "$SSH_KEY")
DATE=$(date +%F)
LOG_TAG="homelab-backup-pull"

log() { echo "[$LOG_TAG] $*"; logger -t "$LOG_TAG" "$*"; }

mkdir -p "$DEST"

# --- VPS artifacts (rsync mirror; source-side rotation applies) ---
for src in "${RSYNC_SOURCES[@]}"; do
	host="${src%%:*}"
	name=$(echo "$host" | tr '.' '-')
	target="$DEST/$name"
	mkdir -p "$target"
	if rsync -a --delete -e "ssh ${SSH_OPTS[*]}" "root@$src" "$target/" >>/dev/null 2>&1; then
		log "OK rsync $src -> $target"
	else
		log "FAIL rsync $src (host down? key authorized?)"
	fi
done

# --- OpenWrt routers (dated tarballs + local retention) ---
for router in "${ROUTERS[@]}"; do
	name=$(echo "$router" | tr '.' '-')
	target="$DEST/$name"
	mkdir -p "$target"
	file="$target/sysupgrade-${DATE}.tar.gz"
	if ssh "${SSH_OPTS[@]}" "root@$router" \
		'sysupgrade -b /tmp/backup-pull.tar.gz && cat /tmp/backup-pull.tar.gz && rm -f /tmp/backup-pull.tar.gz' \
		>"$file" 2>/dev/null && [ -s "$file" ]; then
		log "OK router $router -> $file"
	else
		rm -f "$file"
		log "FAIL router $router"
	fi
	find "$target" -name 'sysupgrade-*.tar.gz' -mtime "+$RETENTION_DAYS" -delete
done

log "done"
