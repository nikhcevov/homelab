# Monitoring

[Repository overview](../README.md)

Sources: [playbooks/mon.yml](../playbooks/mon.yml), [Monitoring checks](../roles/monitoring/files/scripts/), [Monitoring cron schedule](../roles/monitoring/files/homelab-monitoring.cron), [Monitoring role](../roles/monitoring/).

Run commands from the repository root.

Metrics and logs are documented separately in [Observability](observability.md).
All ntfy messages use the shared [notification style](notifications.md): one
title format, one Markdown body, and one severity/tag mapping.

Two complementary layers:

| Layer              | Where                | Covers                                                    |
| ------------------ | -------------------- | --------------------------------------------------------- |
| Gatus              | mon-1 (external)     | declarative HTTP/TCP/ICMP/DNS checks, status page         |
| cron + ntfy checks | each VPS (internal)  | systemd units, containers, disk, updates, reboot, backups |

Gatus intentionally has no per-application checks for the Docker VM. The app
routes are `home.arpa` only and `mon-1` does not resolve that zone; adding them
would either show false failures or send one alert per container when `docker-1`
is down. The public Immich endpoint is the single Docker-VM availability signal;
Grafana owns per-container health, restart, OOM, memory-pressure and
log-volume alerts.

## Internal checks

Internal checks (same `monitoring` role on `edge_nodes`, `vpn`, `mon`; per-group config in `inventory/group_vars/<group>/monitoring.yml`) push to ntfy **only on state transitions**:

The role owns the deployable checks and schedule under `roles/monitoring/files/`; root `scripts/` contains operator tools and is not deployed. Runtime paths remain `/opt/homelab-monitoring/scripts/` and `/etc/cron.d/homelab-monitoring`. The next monitoring deployment removes previously copied laptop power benchmarks without deleting unrelated local files.

| Check             | Interval | Alerts on                         | Severity |
| ----------------- | -------- | --------------------------------- | -------- |
| systemd services  | 15 min   | unit not active                   | critical |
| docker containers | 15 min   | container not running             | critical |
| disk usage        | 1 h      | usage > threshold                 | alert    |
| security updates  | daily    | apt security updates available    | alert    |
| reboot required   | daily    | `/var/run/reboot-required` exists | alert    |
| backup freshness  | daily    | no archive / newest > 25 h old    | alert    |

Empty lists disable a check. Notification channels are severity-first: `*-critical`, `*-alerts`, `*-info`. Gatus sends external failures to the same critical topic.

## Monitoring VPS

Central external watcher (`mon` group): **native Gatus + Caddy** on
`127.0.0.1:8080`; UFW exposes only SSH/80/443. It answers "is the service
reachable from the internet" while the per-host cron checks answer "is the host
healthy inside". The status page is the existing monitoring domain behind
Caddy.

Kuma is removed. There is no Kuma service, database, or backup path on the
monitoring host; Gatus is the only external watcher.

The declarative endpoint list lives in
[`inventory/group_vars/mon/gatus.yml`](../inventory/group_vars/mon/gatus.yml).
HTTPS checks require certificate expiry to be more than 30 days away. The
binary is a pinned local artifact, not a Docker image. Build it elsewhere:

```bash
docker run --rm -v /tmp/gatus-build:/out -e CGO_ENABLED=0 -e GOBIN=/out \
  golang:1.26 go install github.com/TwiN/gatus/v5@v5.38.0
sha256sum /tmp/gatus-build/gatus
ansible-playbook playbooks/mon.yml --limit mon-1 --tags gatus \
  -e gatus_binary_src=/tmp/gatus-build/gatus \
  -e gatus_binary_sha256=<sha256>
```

Gatus reads `/etc/gatus/config.yaml` via `GATUS_CONFIG_PATH`, writes SQLite to
`/var/lib/gatus/data.db`, and sends failures through the critical ntfy topic.
The custom alert body uses the shared [notification style](notifications.md).
The service restarts on config or binary changes; do not treat the UI as a
source of truth.

Deploy: [day-0](getting-started.md#first-run-new-vps) → DNS A record for the
monitoring domain (`vault_monitoring_domain`) → `ansible-playbook playbooks/mon.yml`.
The endpoint list, thresholds, and alert envelope are all in Git.

`playbooks/mon.yml` targets only the `mon` group and reconciles Tailscale after
security, before deploying Gatus; settings come from [monitoring Tailscale
variables](../inventory/group_vars/mon/tailscale.yml). An edge deployment does
not configure this host.

- Monitors and settings live in `inventory/group_vars/mon/gatus.yml` and the
  role templates — there is no UI-managed state.
- The host watches itself via the same cron checks; there are no cron
  cross-checks between hosts — external watching is Gatus's job alone. A
  separate dead-man's switch for `mon-1` is an accepted risk and deliberately
  out of scope.
- mon-1 accepts subnet routes (`tailscale_accept_routes: true`), so Gatus can
  poll router LAN services (see [OpenWrt router](openwrt.md)).
