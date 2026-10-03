# Monitoring

[Repository overview](../README.md)

Sources: [playbooks/mon.yml](../playbooks/mon.yml), [Monitoring checks](../roles/monitoring/files/scripts/), [Monitoring cron schedule](../roles/monitoring/files/homelab-monitoring.cron), [Monitoring role](../roles/monitoring/).

Run commands from the repository root.

Two complementary layers:

| Layer              | Where               | Covers                                                    |
| ------------------ | ------------------- | --------------------------------------------------------- |
| Uptime Kuma        | mon-1 (external)    | ports, HTTPS, certificates, ping — black-box, all hosts   |
| cron + ntfy checks | each VPS (internal) | systemd units, containers, disk, updates, reboot, backups |

## Internal checks

Internal checks (same `monitoring` role on `edge`, `vpn`, `mon`; per-group config in `inventory/group_vars/<group>/monitoring.yml`) push to ntfy **only on state transitions**:

The role owns the deployable checks and schedule under `roles/monitoring/files/`; root `scripts/` contains operator tools and is not deployed. Runtime paths remain `/opt/homelab-monitoring/scripts/` and `/etc/cron.d/homelab-monitoring`. The next monitoring deployment removes previously copied laptop power benchmarks without deleting unrelated local files.

| Check             | Interval | Alerts on                         | Severity |
| ----------------- | -------- | --------------------------------- | -------- |
| systemd services  | 15 min   | unit not active                   | critical |
| docker containers | 15 min   | container not running             | critical |
| disk usage        | 1 h      | usage > threshold                 | alert    |
| security updates  | daily    | apt security updates available    | alert    |
| reboot required   | daily    | `/var/run/reboot-required` exists | alert    |
| backup freshness  | daily    | no archive / newest > 25 h old    | alert    |

Empty lists disable a check. Notification channels are severity-first: `*-critical`, `*-alerts`, `*-info`. Kuma pushes to the same topics (configured once in the Kuma UI).

## Monitoring VPS

Central external watcher (`mon` group): **native Uptime Kuma + Caddy** (Kuma pinned by `kuma_version`, Node.js + systemd, `127.0.0.1:3001` behind Caddy; UFW exposes only SSH/80/443). Answers "is the service reachable from the internet" while the per-host cron checks answer "is the host healthy inside".

Deploy: [day-0](getting-started.md#first-run-new-vps) → DNS A record for the Kuma domain (`vault_kuma_domain`) → `ansible-playbook playbooks/mon.yml` → open the UI, create the admin account, add monitors and the ntfy channel.

`playbooks/mon.yml` targets only the `mon` group and reconciles Tailscale after security, before deploying Kuma; settings come from [monitoring Tailscale variables](../inventory/group_vars/mon/tailscale.yml). An edge deployment does not configure this host.

- Monitors and settings live in Kuma's SQLite DB (`/opt/uptime-kuma/data`) — managed via the UI, not Git. `kuma_backup` snapshots it nightly to `/opt/kuma-backup/archives` (same pattern as `vpn_backup`). See [Unraid backup collection](backups-unraid.md).
- Restore: stop kuma, extract archive into `/`, `chown kuma:kuma .../kuma.db`, start kuma. Caddyfile and certificates are in the same archive.
- The host watches itself via the same cron checks; there are no cron cross-checks between hosts — external watching is Kuma's job alone.
- mon-1 accepts subnet routes (`tailscale_accept_routes: true`), so Kuma can poll router LAN services (see [OpenWrt router](openwrt.md)).
