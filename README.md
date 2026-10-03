# homelab

Self-hosted homelab infrastructure. Git owns the desired infrastructure configuration: Ansible applies host configuration, and the Tailscale policy workflow applies tailnet access rules. Do not manually edit files owned by Ansible; the next deployment can overwrite them.

## Infrastructure

Playbooks target inventory groups. Active hosts and connection settings live in [inventory/hosts.ini](inventory/hosts.ini).

| Group | Playbook(s) | Responsibility |
| ----- | ----------- | -------------- |
| `vps` | [playbooks/site.yml](playbooks/site.yml) | L4 SNI proxy over Tailscale; layered deployment |
| `vpn` | [playbooks/vpn.yml](playbooks/vpn.yml), [playbooks/vpn-restore.yml](playbooks/vpn-restore.yml) | Native 3x-ui + Caddy, nightly backups |
| `mon` | [playbooks/mon.yml](playbooks/mon.yml) | Native Uptime Kuma + Caddy, external watcher |
| `routers` | [playbooks/openwrt.yml](playbooks/openwrt.yml), [playbooks/openwrt-upgrade.yml](playbooks/openwrt-upgrade.yml) | OpenWrt configuration and Tailscale exit nodes |
| `unraid` | [playbooks/unraid.yml](playbooks/unraid.yml) | Backup collection and local restic snapshots |
| `workstations` | [playbooks/workstation.yml](playbooks/workstation.yml) | Arch/CachyOS development environment |

After bootstrap, the tailnet is the management plane. [Inventory](inventory/hosts.ini) uses MagicDNS names; router day-0 temporarily uses a LAN address. The [backup collector](files/unraid/homelab-backup-pull.sh.j2) separately stores Tailscale IPs for its SSH sources.

## Principles

1. **Zero-trust edge.** The edge VPS stores no private data and forwards encrypted traffic only (L4 pass-through via `ssl_preread`, no TLS termination).
2. **Declarative.** Desired state lives in YAML; configs are generated artifacts.
3. **Idempotent.** Re-running any playbook on a converged host reports zero changes.
4. **Restorable.** Infrastructure configuration is rebuilt from this repo; application databases and user data are recovered from backups.
5. **Minimal resources.** VPS layers run on 1 vCPU / 500 MB RAM. No Docker, no Prometheus.
6. **Signal over noise.** Alerts only on state transitions, severity-based ntfy channels.

## Configuration ownership

- **Git + automation:** host configuration, service deployment, routing definitions, and [tailnet policy](files/tailscale/policy.json). The real edge routing map is local and gitignored; keep a separate protected copy.
- **Application state:** VPN clients/settings, Kuma monitors, and media-stack settings live in their applications, not Ansible. Follow each application's configuration and backup procedure.
- **Manual setup:** OS/day-0 bootstrap, DNS records, Tailscale machine tags and route approval, Unraid pool provisioning, and GUI schedules. Ansible does not recreate these steps.

## Documentation

| Guide | Scope |
| ----- | ----- |
| [Getting started](docs/getting-started.md) | Requirements, repository layout, VPS day-0, secrets |
| [Edge VPS](docs/edge.md) | Layered deployment, routing, local render, operations, troubleshooting |
| [Tailscale policy](docs/tailscale.md) | Tags, access rules, GitOps setup, apply and rollback |
| [VPN VPS](docs/vpn.md) | Deployment, application-state ownership, backups and restore |
| [Monitoring](docs/monitoring.md) | Internal cron/ntfy checks and external Kuma watcher |
| [OpenWrt routers](docs/openwrt.md) | LAN bootstrap, exit nodes, Wi-Fi, upgrades and management |
| [Unraid backups](docs/backups-unraid.md) | Collection, manual schedules, restic and recovery |
| [Workstations](docs/workstations.md) | Bootstrap, chezmoi, keyboard/KDE behavior |
| [Laptop power](docs/laptop-power.md) | Power profiles, measurements, caveats and removal |
| [Media/Arr stack](docs/arr-stack.md) | Application configuration, media layout and maintenance |

For the solo-maintainer workflow, documentation upkeep, and local checks, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Repository layout

- [playbooks/](playbooks/) entrypoints select hosts and compose roles; see the infrastructure table above.
- [inventory/](inventory/), [inventory/group_vars/](inventory/group_vars/), and [inventory/host_vars/](inventory/host_vars/) define hosts, shared settings, and per-host deltas.
- [roles/](roles/) owns host configuration and deployment behavior; [monitoring assets](roles/monitoring/files/) include the deployed checks and cron schedule.
- [vars/proxy.example.yml](vars/proxy.example.yml) documents the local, gitignored edge routing map.
- [scripts/](scripts/) holds operator tools such as laptop power benchmarks.
- [files/](files/) holds shared SSH public keys, Unraid templates, and tailnet policy.
- [tests/](tests/) holds the offline Ansible syntax and proxy validation gate.
- [docs/](docs/) holds operational guides; the detailed file layout is in [Getting started](docs/getting-started.md#repository-layout).

## Non-goals

- Prometheus / Grafana / Loki / ELK / SIEM.
- Kubernetes, Docker Swarm, Nomad.
- TLS termination on the edge VPS.
- Hosting applications on the VPS.

Stay boring. Replace any VPS in 5 minutes. Sleep at night.
