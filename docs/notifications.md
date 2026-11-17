# Notifications

[Repository overview](../README.md)

All homelab notifications use one ntfy envelope. The sender owns the facts;
this guide owns the presentation.

## Title

```text
<emoji> Homelab · <Component> · <Event>
```

Examples:

```text
🚨 Homelab · Service · caddy down
⚠️ Homelab · Disk · /mnt/appdata at 91%
✅ Homelab · Backup · collector recovered
ℹ️ Homelab · Updates · 7 packages available
```

Rules:

- The emoji is the severity marker.
- `Homelab` is literal; do not put the hostname or `[PVE]` brackets in the title.
- `Component` is one of the stable names below.
- `Event` is a short state, not a sentence. Keep the title under 64 characters.
- Put the hostname, measurements, and remediation in the body.

## Body

Markdown is enabled. Use this order and omit fields that do not apply:

```markdown
**<summary>**

- **Host:** `great-hornbill`
- **Component:** `Disk`
- **State:** `warning`
- **Details:** `/mnt/appdata` is 91% full; threshold is 85%.
- **Action:** Free space or lower the threshold deliberately.
```

The summary is the one line visible when the notification is collapsed. Details
must be concrete: mount, service, container, package count, age, temperature,
battery charge, or command to inspect.

## Severity

| Severity | Emoji | ntfy priority | Topic | Use |
| --- | --- | --- | --- | --- |
| `critical` | 🚨 | `urgent` | critical | Service down, SMART failure, UPS on battery/low, scrape target down |
| `warning` | ⚠️ | `high` | alerts | Disk usage, temperature, stale backup, updates, UPS overload, CRC increase |
| `resolved` | ✅ | `default` | info | A previously failing check recovered |
| `info` | ℹ️ | `default` | info | Informational, no action required |
| `test` | 🧪 | `default` | info | Explicit delivery test only |

The sender picks the severity; the transport does not infer it.

## Tags

Every message carries two tags:

1. severity tag: `rotating_light`, `warning`, `white_check_mark`,
   `information_source`, or `test_tube`;
2. component tag: `pve`, `docker`, `backup`, `updates`, `disk`, `ups`,
   `network`, `monitor`, `pbs`, or `service`.

Do not use `package` for every backup or update message. It hides the component.

Gatus uses one fixed tag set (`external,monitor`) because its custom alert
payload cannot vary tags between firing and resolved. Its title emoji carries
the state instead.

## Components

| Component | Scope |
| --- | --- |
| `PVE` | Proxmox host, VM/LXC, storage, ZFS |
| `Docker` | Docker VM, containers, Compose stacks |
| `Backup` | PVE/PBS/Unraid/VPN backup and restore checks |
| `Updates` | APT, APK, firmware, reboot-required |
| `Disk` | Filesystem usage, SMART, temperature |
| `UPS` | NUT/UPS state |
| `Network` | Routers, DNS, Tailscale reachability |
| `Monitor` | Prometheus/Grafana/Loki/Gatus health |
| `PBS` | PBS-native maintenance notifications |
| `Service` | systemd units and user-facing services |

## Sender mapping

| Sender | Component | Notes |
| --- | --- | --- |
| `roles/monitoring/files/scripts/notify.sh` | per check | internal VPS checks |
| `roles/openwrt_upgrades` | `Updates` | APK + owut check |
| `roles/pve_backup` | `Backup` | PVE/PBS file backup |
| `roles/pve_pbs` | `PBS` | native PBS warning/error webhook |
| `files/unraid/*` | `Backup` | Unraid pull/restic checks |
| Grafana Alerting | per rule label | `component` label is required |
| Gatus | `Monitor` / endpoint group | external availability |

## Transport rules

- Send on state transitions only; do not repeat an unchanged warning.
- Use `Markdown: yes` for script senders and `markdown=yes` for the Grafana
  webhook URL.
- Never put vault values, tokens, passwords, or full private URLs in the title
  or body.
- Keep `critical` for conditions that need action now. Use `warning` for
  degradation and `info` for recovery.
- A recovery message uses `resolved` and the `info` topic, even if the original
  failure was critical.
