# homelab

Self-hosted homelab infrastructure. Git owns the desired infrastructure configuration: Ansible applies host configuration, and the Tailscale policy workflow applies tailnet access rules. Do not manually edit files owned by Ansible; the next deployment can overwrite them.

## Infrastructure

Playbooks target inventory groups. Active hosts and connection settings live in [inventory/hosts.ini](inventory/hosts.ini).

| Group | Deployment playbook | Responsibility |
| ----- | ------------------- | -------------- |
| `edge_nodes` | [playbooks/edge.yml](playbooks/edge.yml) | L4 SNI proxy over Tailscale; five ordered stages |
| `vpn` | [playbooks/vpn.yml](playbooks/vpn.yml) | Native 3x-ui + Caddy, nightly backups; explicit restore tag |
| `mon` | [playbooks/mon.yml](playbooks/mon.yml) | Native Gatus + Caddy, declarative external watcher |
| `routers` | [playbooks/openwrt.yml](playbooks/openwrt.yml) | OpenWrt configuration, Tailscale exit nodes and the gateway VM; explicit upgrade tag |
| `pve` | [playbooks/pve.yml](playbooks/pve.yml) | Proxmox: ZFS managed disks, private media NFS, VM/GPU/UPS, native PBS backups |
| `docker` | [playbooks/docker.yml](playbooks/docker.yml) | Debian VM: local appdata/photos/files, private media mount, LAN SMB share, NVIDIA, restore-gated stacks |
| `workstations` | [playbooks/workstation.yml](playbooks/workstation.yml) | Arch/CachyOS development environment |

Each host type has one setup/update playbook. Normal runs reconcile configuration;
destructive maintenance is opt-in: VPN restore uses `--tags restore -e vpn_restore_archive=/path/to/archive.tar.gz`
after setup, and router upgrades are image-based: `--tags upgrade`
builds a full image via `owut`/ASU. [playbooks/proxy-render.yml](playbooks/proxy-render.yml) is a local-only
verification utility, not another deployment entrypoint.

After bootstrap, the tailnet is the management plane. [Inventory](inventory/hosts.ini) uses MagicDNS names; router day-0 temporarily uses a LAN address. The [PVE backup collector](roles/pve_backup/) separately stores Tailscale IPs for its SSH sources.

The desired edge identity is host `edge` in group `edge_nodes`, with Tailscale
name `edge` and restricted `tag:edge`. The operator confirmed the legacy
`tag:vps` is unused; the repository policy is now edge-only. This does not prove
policy apply, machine-name or OS-hostname changes, or deployment health.
Follow the [existing-node cutover](docs/edge.md#existing-node-identity-cutover)
before deployment.

OS/appdata live on SSD; photos/files use managed ext4 VM disks on the HDD ZFS
mirror. Native PBS protects those disks without stopping containers. Backup
schedules are active on the temporary B-only primary; A is quarantined and no
second/off-site copy is currently accepted. See [current acceptance](docs/status.md)
and the [backup/recovery guide](docs/backups-proxmox.md).

## Principles

1. **Zero-trust edge.** The edge VPS stores no private data and forwards encrypted traffic only (L4 pass-through via `ssl_preread`, no TLS termination).
2. **Declarative.** Desired state lives in YAML; configs are generated artifacts.
3. **Idempotent reconciliation.** Re-running setup/update preserves credentials and application data; configuration changes use existing reload/restart handlers. Package upgrades or cache refreshes can still report changes.
4. **Restorable.** Infrastructure configuration is rebuilt from this repo; application databases and user data are recovered from backups.
5. **Minimal resources.** VPS services run on 1 vCPU / 500 MB RAM and stay Docker/Prometheus-free. Home observability runs on `docker-1` under explicit memory and retention caps.
6. **Signal over noise.** Alerts only on state transitions, severity-based ntfy channels.

## Configuration ownership

- **Git + automation:** host configuration, service deployment, routing definitions, and [tailnet policy](files/tailscale/policy.json). The real edge routing map is local and gitignored; keep a separate protected copy.
- **Application state:** VPN clients/settings and media-stack settings live in their applications, not Ansible. Gatus checks are declarative in Git.
- **Manual setup:** OS/day-0 bootstrap, DNS records, Tailscale machine tags/route approval, and explicit blank-disk approval. Ansible manages opted-in PVE storage/VM configuration and PBS schedules; follow the host and backup guides.

## Documentation

| Guide | Scope |
| ----- | ----- |
| [Current status](docs/status.md) | Snapshot: implemented, decided, open, verified |
| [HA KRM audit](docs/ha-krm-audit.md) | Pi/HA audit, applied fixes, open weekend/physical checklist |
| [Getting started](docs/getting-started.md) | Requirements, repository layout, VPS day-0, secrets |
| [Edge VPS](docs/edge.md) | Setup/update stages and tags, routing, local render, operations, troubleshooting |
| [Tailscale policy](docs/tailscale.md) | Tags, access rules, GitOps setup, apply and rollback |
| [VPN VPS](docs/vpn.md) | Deployment, application-state ownership, backups and restore |
| [Monitoring](docs/monitoring.md) | Internal cron/ntfy checks and external Gatus watcher |
| [Notifications](docs/notifications.md) | Shared ntfy title, body, severity and tag style |
| [Observability](docs/observability.md) | Local Grafana/Prometheus/Loki stack and host agents |
| [OpenWrt routers](docs/openwrt.md) | LAN bootstrap, exit nodes, gateway VM, Wi-Fi, upgrades and management |
| [Docker stacks](docs/docker-stacks.md) | Compose layout, secrets, deploy and verification |
| [Proxmox host](docs/pve-host.md) | Host tuning, ZFS pools, NFS exports, UPS |
| [Proxmox backups](docs/backups-proxmox.md) | Native PBS operation, B-primary recovery and retained legacy Restic access |
| [HDD price research](docs/hdd-price-research.md) | Price-per-TB method, snapshots and reproduction |
| [Workstations](docs/workstations.md) | Bootstrap, chezmoi, keyboard/KDE behavior |
| [Laptop power](docs/laptop-power.md) | Power profiles, measurements, caveats and removal |
| [Media/Arr stack](docs/arr-stack.md) | Application configuration, media layout and maintenance |

For the solo-maintainer workflow, documentation upkeep, and local checks, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Migration archive

These dated records are evidence, not current deployment instructions.

| Record | Scope |
| --- | --- |
| [Migration checkpoints](docs/archive/migration-checkpoints.md) | Original audit, cutover, failures and acceptance evidence |
| [Unraid-to-PVE runbook](docs/archive/proxmox-migration.md) | Historical architecture, disk identities and one-time cutover approvals |
| [Backup cutover](docs/archive/backup-cutover.md) | Superseded backup workflows, recovery proofs and cancelled cloud seed |
| [Unraid backups](docs/archive/backups-unraid.md) | Historical collection/Restic setup and recovery context |

## Repository layout

- [playbooks/](playbooks/) entrypoints select hosts and compose roles; see the infrastructure table above.
- [inventory/](inventory/), [inventory/group_vars/](inventory/group_vars/), and [inventory/host_vars/](inventory/host_vars/) define hosts, shared settings, and per-host deltas.
- [roles/](roles/) owns host configuration and deployment behavior; [monitoring assets](roles/monitoring/files/) include the deployed checks and cron schedule.
- [compose/](compose/) holds the Docker VM's compose stacks and their `.env.j2` templates; secrets live in the vault.
- [vars/proxy.example.yml](vars/proxy.example.yml) documents the local, gitignored edge routing map.
- [scripts/](scripts/) holds operator tools such as laptop power benchmarks.
- [files/](files/) holds shared SSH public keys and tailnet policy.
- [tests/](tests/) holds the offline Ansible syntax and proxy validation gate.
- [docs/](docs/) holds operational guides; the detailed file layout is in [Getting started](docs/getting-started.md#repository-layout).

## Non-goals

- ELK / SIEM.
- Kubernetes, Docker Swarm, Nomad.
- TLS termination on the edge VPS.
- Hosting applications on the VPS.

Stay boring. Replace any VPS in 5 minutes. Sleep at night.
