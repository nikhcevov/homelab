# homelab-vps-proxy

Reproducible VPS reverse-proxy + lightweight monitoring for a self-hosted homelab.

The VPS is a thin, replaceable edge node. It terminates inbound traffic and forwards it to the home server over a private network (Tailscale / WireGuard / LAN). It holds no application data and never decrypts user traffic.

---

## Principles

1. **Zero-trust oriented.** VPS stores no private data and has no access to home service content. It forwards encrypted traffic only (L4 TCP/UDP pass-through, no TLS termination).
2. **Single responsibility.** Reverse proxy + minimal monitoring. Nothing else runs here.
3. **Fully replaceable.** Rebuild any time from `git clone`, `.env`, one install command.
4. **Minimal resources.** Runs on 1 vCPU / 500 MB RAM. Plain nginx + cron + bash. No Docker, no Prometheus, no agent runtime.
5. **Operational simplicity.** No service mesh, no observability stack, no dashboards.
6. **Signal over noise.** Alerts only when action is needed. Severity-based channels, state-based deduping.

---

## Architecture

```
                Internet
                   |
                   v
            +-------------+
            |     VPS     |   nginx stream{}: L4 TCP/UDP forwarder
            | (this repo) |   cron: bash health checks → ntfy
            +-------------+
                   |
            Tailscale / WG / LAN
                   |
                   v
            +-------------+
            | Home server |   real services live here
            +-------------+
```

The VPS sees only ciphertext for HTTPS and game traffic. Certificates, application logic and data all live on the home server.

---

## Repository layout

```
.
├── install.sh                       one-command installer (idempotent)
├── .env.example                     all configuration
├── nginx/
│   ├── nginx.conf                   main nginx config, deployed verbatim
│   └── render-stream.sh             generates per-port stream snippets from .env
├── scripts/                         monitoring checks (bash)
│   ├── notify.sh                    ntfy transport + state-based dedup
│   ├── check-services.sh            systemd units
│   ├── check-containers.sh          docker containers (optional)
│   ├── check-disk.sh                disk usage
│   ├── check-https.sh               HTTPS endpoint reachability
│   ├── check-reboot.sh              reboot-required flag
│   └── check-updates.sh             apt security updates
└── cron/
    └── homelab-monitoring.cron      schedules all checks
```

---

## Requirements

- VPS running Debian / Ubuntu (tested on 22.04+).
- Outbound network to the home server over a private network. **Use [Tailscale](https://tailscale.com) or WireGuard**, do not expose home LAN directly.
- A reachable [ntfy.sh](https://ntfy.sh) topic for notifications (public ntfy.sh is fine; pick long random topic names).
- Root access on the VPS.

---

## Install

```bash
git clone https://github.com/<you>/homelab-vps-proxy.git
cd homelab-vps-proxy

cp .env.example .env
nano .env                 # set HOMELAB_BACKEND + topics

sudo ./install.sh
```

That is the full setup. The installer is idempotent — re-run it whenever you change `.env` or pull updates.

What `install.sh` does:

1. Creates `/opt/homelab-monitoring/` (scripts, nginx config, env).
2. Creates `/var/lib/homelab-monitoring/` (state files for dedup).
3. Installs `nginx` + `curl` via apt.
4. Deploys `nginx/nginx.conf` to `/etc/nginx/nginx.conf`.
5. Renders one stream snippet per `NGINX_TCP_PORTS` / `NGINX_UDP_PORTS` entry into `/etc/nginx/stream.d/`.
6. Validates with `nginx -t` and reloads nginx.
7. Installs `/etc/cron.d/homelab-monitoring` and restarts cron.

---

## Configuration

All settings live in `/opt/homelab-monitoring/.env`. The installer copies `.env.example` on first run and leaves an existing `.env` untouched on re-runs.

### Reverse proxy

| Variable          | Purpose                                                             | Example       |
| ----------------- | ------------------------------------------------------------------- | ------------- |
| `HOMELAB_BACKEND` | IP of the home server. **Prefer the Tailscale IP** (`100.x.x.x`).   | `100.64.0.2`  |
| `NGINX_TCP_PORTS` | Space-separated TCP ports to forward. `listen` or `listen:backend`. | `"443 25565"` |
| `NGINX_UDP_PORTS` | Space-separated UDP ports to forward.                               | `"24454"`     |

Port mapping syntax:

- `443` — listen on VPS:443, forward to `HOMELAB_BACKEND:443`.
- `8443:443` — listen on VPS:8443, forward to `HOMELAB_BACKEND:443`.

Each entry produces one file in `/etc/nginx/stream.d/` (e.g. `tcp_443.conf`, `udp_24454.conf`). The renderer wipes that directory on each install run, so removing a port from `.env` and re-running `install.sh` removes the listener.

The proxy operates at L4 — nginx never reads payloads. TLS certificates live on the home server (typically via Caddy / nginx / Traefik behind this VPS).

### Monitoring

| Variable              | Purpose                                          |
| --------------------- | ------------------------------------------------ |
| `NTFY_URL`            | ntfy base URL (default `https://ntfy.sh`).       |
| `NTFY_TOPIC_CRITICAL` | Topic for critical alerts (action required now). |
| `NTFY_TOPIC_ALERTS`   | Topic for non-emergency alerts (action soon).    |
| `NTFY_TOPIC_INFO`     | Topic for informational events.                  |
| `HOST_PREFIX`         | Tag prepended to messages, e.g. `[VPS]`.         |
| `CHECK_SERVICES`      | systemd units to check (`nginx tailscaled`).     |
| `CHECK_CONTAINERS`    | Docker container names to check (usually empty). |
| `DISK_THRESHOLD`      | Disk usage % triggering alert (default `85`).    |
| `DISK_MOUNTS`         | Mount points to inspect (`"/"`).                 |
| `HTTPS_ENDPOINTS`     | HTTPS URLs to ping (usually empty — see below).  |

Notes:

- `HTTPS_ENDPOINTS` checks that an endpoint returns 2xx/3xx. Useful for testing the full edge → home path. Leave empty to skip.
- All checks dedupe via state files in `/var/lib/homelab-monitoring/`. You get one DOWN message and one RECOVERED message, not a flood.

---

## What gets monitored

Each check runs from cron and pushes to ntfy only on state transitions.

| Check             | Interval | Alerts on                         | Severity                    |
| ----------------- | -------- | --------------------------------- | --------------------------- |
| systemd services  | 15 min   | unit not active                   | critical → DOWN / RECOVERED |
| docker containers | 15 min   | container not running             | critical                    |
| HTTPS endpoints   | 15 min   | non-2xx/3xx response or timeout   | critical                    |
| disk usage        | 1 h      | usage > `DISK_THRESHOLD`          | alert                       |
| security updates  | daily    | apt security updates available    | alert                       |
| reboot required   | daily    | `/var/run/reboot-required` exists | alert                       |

What is intentionally **not** monitored: CPU graphs, memory graphs, network throughput, per-process metrics, container logs. Add them yourself if you really need them; the philosophy here is operational calmness.

---

## Notification channels

Severity-first, not service-first. Three topics total, regardless of how many services you run:

- `homelab-critical` — drop-everything events (proxy down, VPS unreachable, backups failed).
- `homelab-alerts` — non-urgent but actionable (updates available, disk high, reboot required).
- `homelab-info` — informational only (backup completed, monthly report).

Per-service topics get muted. Severity topics stay readable.

---

## Operations

### Update from git

```bash
cd homelab-vps-proxy
git pull
sudo ./install.sh
```

Same command. Idempotent. Re-runs the renderer, validates with `nginx -t`, reloads nginx, refreshes cron.

### Add or remove a forwarded port

1. Edit `NGINX_TCP_PORTS` / `NGINX_UDP_PORTS` in `/opt/homelab-monitoring/.env`.
2. `sudo /opt/homelab-monitoring/nginx/render-stream.sh`
3. `sudo nginx -t && sudo systemctl reload nginx`

Or just re-run `sudo ./install.sh` from the repo.

### Change the home server IP

Update `HOMELAB_BACKEND` in `.env` and re-run `install.sh` (or the render script + reload).

### Quick health checks

```bash
sudo systemctl status nginx
sudo nginx -t
sudo ss -tlnp | grep nginx
ls /etc/nginx/stream.d/
journalctl -u nginx -n 50
```

### Trigger a check manually

```bash
sudo bash /opt/homelab-monitoring/scripts/check-services.sh
sudo bash /opt/homelab-monitoring/scripts/check-https.sh
```

### Migrate to a new VPS

1. Provision new VPS, install Tailscale (or your tunnel).
2. `git clone` this repo, copy your existing `.env`.
3. `sudo ./install.sh`.
4. Switch DNS A/AAAA records to the new VPS.

Done. The home server is untouched.

---

## Security notes

- **No TLS termination on the VPS.** Certificates and private keys live only on the home server.
- **Outbound to home only over a private network.** Do not point `HOMELAB_BACKEND` at a public WAN IP; use Tailscale, WireGuard or a private interconnect.
- **Port 80 returns 444.** No HTTP service is exposed; redirect to HTTPS at the application layer behind the proxy.
- **server_tokens off.** No nginx version advertised.
- **No logging of stream payloads.** Stream access log is disabled; only nginx errors are kept.
- Lock down SSH separately (key-only, fail2ban, non-default port). This repo does not manage SSH.

---

## Troubleshooting

| Symptom                                | Look at                                                                  |
| -------------------------------------- | ------------------------------------------------------------------------ |
| `nginx -t` fails after install         | `/etc/nginx/stream.d/` — bad port number or unset `HOMELAB_BACKEND`.     |
| Connection refused on a forwarded port | `ss -tlnp \| grep <port>`, `journalctl -u nginx`.                        |
| Forwarded service unreachable          | Test `nc -vz $HOMELAB_BACKEND <port>` from the VPS.                      |
| No ntfy messages arrive                | Check topic names in `.env`, run a script manually, check `curl` output. |
| Alert never clears                     | Inspect `/var/lib/homelab-monitoring/*.state` and remove stale files.    |
| Repeated DOWN/RECOVERED flapping       | Underlying service is unstable — fix it, not the monitor.                |

---

## Non-goals

- Prometheus / Grafana / Loki / ELK / SIEM.
- Kubernetes, Docker Swarm, Nomad.
- Centralized log aggregation.
- TLS termination on the VPS.
- Hosting applications on the VPS.
- Self-hosted ntfy unless there is a specific reason.

Stay boring. Replace the VPS in 5 minutes. Sleep at night.
