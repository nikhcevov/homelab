# Observability

[Repository overview](../README.md) · [Monitoring](monitoring.md)

Sources: [observability Compose stack](../compose/observability/), [agent role](../roles/observability_agents/), [Docker stack inventory](../inventory/group_vars/docker/compose.yml), and the [implementation plan](superpowers/plans/2026-11-16-observability-stack.md).

This guide covers the local metrics and log stack. Uptime Kuma remains the external
availability watcher; it is not replaced by Grafana.

## Layers

| Layer | Where | Covers |
| --- | --- | --- |
| Grafana / Prometheus / Loki | `docker-1` | dashboards, metrics history, log search |
| node_exporter | PVE and `docker-1` | host CPU, memory, filesystems, network |
| smartctl_exporter | PVE only | disk SMART health and temperature |
| nut_exporter | PVE only | UPS status, battery charge and runtime |
| cAdvisor | `docker-1` | per-container Docker metrics |
| pve-exporter | `docker-1` | Proxmox API: nodes, guests, storage, backups |
| Grafana Alloy | PVE and `docker-1` | journald and Docker log shipping |

`docker-1` is the only Docker host. The PVE host keeps no Docker daemon.

## Addresses and ports

| Service | Bind | Exposure |
| --- | --- | --- |
| Grafana | `127.0.0.1:3000` on `docker-1` | Caddy `http://grafana.home.arpa`, tailnet only |
| Prometheus | `127.0.0.1:9090` on `docker-1` | loopback only |
| Loki | `10.77.0.2:3100` on `docker-1` | private `vmbr1` only |
| cAdvisor | Compose network | not published |
| pve-exporter | Compose network | not published |
| node_exporter PVE | `10.77.0.1:9100` | private `vmbr1` only |
| smartctl_exporter PVE | `10.77.0.1:9633` | private `vmbr1` only |
| nut_exporter PVE | `10.77.0.1:9199` | private `vmbr1` only |
| node_exporter Docker | `10.77.0.2:9100` | private `vmbr1` only |
| Alloy | host-local | pushes to Loki only |

Do not publish Prometheus, Loki, cAdvisor, pve-exporter, or the host exporters to
the LAN or internet.

## Data and retention

| Path | Contents |
| --- | --- |
| `/mnt/appdata/observability/prometheus/data` | Prometheus TSDB |
| `/mnt/appdata/observability/loki/data` | Loki chunks and index |
| `/mnt/appdata/observability/grafana/data` | Grafana SQLite/config |
| `/mnt/appdata/observability/grafana/provisioning` | datasource provisioning |
| `/mnt/appdata/observability/prometheus/prometheus.yml` | scrape config |
| `/mnt/appdata/observability/loki/loki-config.yml` | Loki config |
| `/opt/compose/observability/.env` | root-only Compose secrets, including the PVE token |

Prometheus keeps `30d` and caps the TSDB at `8GB`. Loki keeps `720h`, uses
filesystem storage, and allows `8 MB/s` with a `16 MB` burst so Alloy can absorb
the initial Docker-log tail without dropping entries. This is sized for the
current appdata headroom. Measure ingestion before extending to 90 or 365 days;
one year needs external storage.

## Resource ceilings

| Service | Limit |
| --- | ---: |
| Grafana | `512m` |
| Prometheus | `1g` |
| Loki | `512m` |
| pve-exporter | `128m` |
| cAdvisor | `384m` |
| node_exporter | `128M` systemd |
| smartctl_exporter | `128M` systemd |
| nut_exporter | `64M` systemd |
| Alloy | `256M` systemd |

These are hard caps, not reservations. Re-measure with `docker stats`,
`memory.peak`, and `free -h` after a full workload cycle before tightening.

## Proxmox access

`pve-exporter` uses user `prometheus@pve` and token `observability` with
`PVEAuditor` on `/`. The token is stored as `vault_pve_exporter_token`, passed
through the root-only Compose environment, and is read-only. `PVE_VERIFY_SSL=false`
is limited to the private tailnet path. The scrape target is the PVE tailnet address
(`observability_pve_api_target`) because the PVE management filter blocks port
8006 on the host-only bridge. Rotate it with:

```bash
pveum user token remove prometheus@pve observability
pveum user token add prometheus@pve observability --privsep 0
```

Update the vault value and redeploy the observability stack after rotation.
Do not expose the exporter.

## SMART and HDD standby

`smartctl_exporter` runs only on the PVE host with:

```text
--smartctl.powermode-check=standby
--smartctl.interval=300s
```

After a standby interval, verify that polling does not increase
`Start_Stop_Count` or wake the 10 TB disks. Do not lower the interval without
repeating that observation.

## UPS

`nut_exporter` runs only on the PVE host, reads the local NUT server at
`127.0.0.1:3493`, and exposes `network_ups_tools_*` metrics on
`10.77.0.1:9199`. The NUT password is rendered into `/etc/nut-exporter.env`
with mode `0600`; it is not in the unit file.

Current alert conditions are `OB=1` (on battery), `LB=1` (low battery), and
`OVER=1` (overload). Battery charge and runtime are scraped for dashboards and
manual inspection.

## Deploy

Agents:

```bash
ansible-playbook playbooks/pve.yml --tags observability
ansible-playbook playbooks/docker.yml --tags observability
```

Stack:

```bash
ansible-playbook playbooks/docker.yml --limit docker-1 --tags compose \
  -e '{"compose_stacks":["caddy-cloudflare","observability"],"compose_data_restored":true}'
```

The `compose_data_restored=true` override is required by the existing restore
gate; it is not a substitute for the restored-data marker.

## Verify

```bash
curl -fsS http://127.0.0.1:3000/api/health
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS http://10.77.0.2:3100/ready
curl -fsS http://10.77.0.1:9100/metrics | grep node_uname_info
curl -fsS http://10.77.0.1:9633/metrics | grep smartctl_version
curl -fsS 'http://10.77.0.1:9199/ups_metrics?ups=cyberpower' | grep network_ups_tools_ups_status
```

Open `http://grafana.home.arpa` through Caddy/Tailscale. Check Prometheus
targets: `prometheus`, `node-pve`, `node-docker`, `smartctl-pve`, `cadvisor`,
`pve`, and `nut` must be `UP`.

## Dashboards and alerts

Datasources are provisioned from
`compose/observability/grafana-datasources.yml.j2`. The daily overview is
Homelab Overview (`/d/homelab-overview/homelab-overview`). Supporting
dashboards are Node Exporter Full (`/d/rYdddlPWk/node-exporter-full`), cAdvisor
(`/d/pMEd7m0Mz/cadvisor-exporter`), PVE
(`/d/pve-via-prometheus/proxmox-via-prometheus`), Disk Health
(`/d/disk-health/disk-health`), and Logs & Errors
(`/d/logs-errors/logs-and-errors`). Docker logs carry `container`,
`compose_project`, and `service` labels; the observability containers are
excluded to prevent a log-feedback loop. The cAdvisor scrape relabels the Compose service
label to `name` and the instance to `docker-1`. Disk temperatures and SMART
health come from `smartctl_device_temperature` and `smartctl_device_smart_status`.
Disk Health also exposes raw SMART counters: reallocated, pending, offline
uncorrectable, CRC errors, power-on hours, power cycles, start/stop and load
cycles.
Export production dashboards as JSON after editing them in the UI; do not leave
the only copy in Grafana's database.

Grafana Alerting has two webhook contact points, both using
`?template=grafana`: `ntfy-alerts` for the normal alerts topic and
`ntfy-critical` for the critical topic. The default policy routes warning rules
to `ntfy-alerts`; a child route sends `severity=critical` to `ntfy-critical`
with a 10s group wait and 2h repeat interval. The normal repeat interval is 4h.

Configured rules:

| Rule | For | Severity |
| --- | ---: | --- |
| Scrape target down (includes `nut`) | 5m | critical |
| Filesystem above 85% | 15m | warning |
| Disk temperature above 50C | 10m | warning |
| SMART health failed | 5m | critical |
| SMART pending or reallocated sectors | 5m | critical |
| SMART CRC errors increasing | 10m | warning |
| PVE storage above 85% | 15m | warning |
| ZFS pool not online | 5m | critical |
| UPS on battery | 1m | critical |
| UPS low battery | 1m | critical |
| UPS overloaded | 5m | warning |

Both webhook tests returned HTTP 200. External Kuma monitoring is intentionally
deferred for a later redesign.

## Rollback

Stop the local stack while keeping data:

```bash
ansible-playbook playbooks/docker.yml --limit docker-1 --tags compose \
  -e '{"compose_stacks":["caddy-cloudflare"],"compose_data_restored":true}'
```

Then remove the observability containers and leave `/mnt/appdata/observability`
intact for inspection. Disable the agent units on both hosts if the stack will
not be restored:

```bash
systemctl disable --now node_exporter smartctl_exporter alloy
```

Do not delete data until the retention and backup decision is recorded.

## Known limits

- Loki indexes labels, not every word; queries scan chunks.
- cAdvisor is privileged because it reads Docker/cgroup data; keep it pinned and
  loopback-only.
- The stack shares the PVE failure domain with `docker-1`; external Kuma remains
  the only off-host alert path.
- The current 4C/8T host is the next bottleneck after memory; adding more
  guests does not add CPU.
