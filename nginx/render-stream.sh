#!/bin/bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-/opt/homelab-monitoring/.env}"
OUT_DIR="${OUT_DIR:-/etc/nginx/stream.d}"

if [ -f "$ENV_FILE" ]; then
	set -a
	source "$ENV_FILE"
	set +a
fi

: "${HOMELAB_BACKEND:?HOMELAB_BACKEND is required (IP of home server, prefer Tailscale)}"
NGINX_TCP_PORTS="${NGINX_TCP_PORTS:-}"
NGINX_UDP_PORTS="${NGINX_UDP_PORTS:-}"

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/*.conf

emit_tcp() {
	local listen_port=$1
	local backend_port=$2
	local name="tcp_${listen_port}"
	cat >"$OUT_DIR/${name}.conf" <<EOF
upstream ${name} {
	server ${HOMELAB_BACKEND}:${backend_port};
}
server {
	listen ${listen_port};
	listen [::]:${listen_port};
	proxy_pass ${name};
	proxy_connect_timeout 5s;
	proxy_timeout 1h;
}
EOF
}

emit_udp() {
	local listen_port=$1
	local backend_port=$2
	local name="udp_${listen_port}"
	cat >"$OUT_DIR/${name}.conf" <<EOF
upstream ${name} {
	server ${HOMELAB_BACKEND}:${backend_port};
}
server {
	listen ${listen_port} udp reuseport;
	listen [::]:${listen_port} udp reuseport;
	proxy_pass ${name};
	proxy_timeout 30s;
	proxy_responses 0;
}
EOF
}

parse_entry() {
	local entry=$1
	local listen backend
	if [[ "$entry" == *:* ]]; then
		listen="${entry%%:*}"
		backend="${entry##*:}"
	else
		listen="$entry"
		backend="$entry"
	fi
	echo "$listen $backend"
}

for entry in $NGINX_TCP_PORTS; do
	read -r lp bp < <(parse_entry "$entry")
	emit_tcp "$lp" "$bp"
done

for entry in $NGINX_UDP_PORTS; do
	read -r lp bp < <(parse_entry "$entry")
	emit_udp "$lp" "$bp"
done

echo "Rendered stream configs to $OUT_DIR:"
ls -1 "$OUT_DIR" || true
