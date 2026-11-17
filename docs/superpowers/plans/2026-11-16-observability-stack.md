# Observability Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Grafana, Prometheus, and Loki to `docker-1`, with PVE host and Docker VM metrics plus 30-day logs, without breaking the current memory or disk budget.

**Architecture:** Grafana and Prometheus run as Compose services on `docker-1`. `node_exporter`, `smartctl_exporter`, and Grafana Alloy run as pinned systemd services on the hosts they observe. Prometheus scrapes host exporters, `cadvisor`, and `pve-exporter`; Loki receives logs from Alloy. External Uptime Kuma remains the alerting path that survives the home failure domain.

**Tech Stack:** Grafana, Prometheus, Loki, Grafana Alloy, node_exporter, smartctl_exporter, cAdvisor, prometheus-pve-exporter, Ansible, Docker Compose.

**Spec:** [Docker stacks](../../docker-stacks.md), [monitoring](../../monitoring.md), and the 2026-11-16 session decisions. There is no separate design document.

## Global Constraints

- Target hosts: `docker-1` (VM100, private address `10.77.0.2`) and `great-hornbill` (PVE, private address `10.77.0.1`).
- Observability data lives under `/mnt/appdata/observability`; do not place Prometheus or Loki data on HDD/NFS.
- Start with Prometheus retention `30d` and `8GB`; Loki retention `720h`.
- Container caps: Grafana `256m`, Prometheus `1g`, Loki `512m`, pve-exporter `128m`, cAdvisor `256m`.
- Systemd caps: node_exporter `128M`, smartctl_exporter `128M`, Alloy `256M`.
- Only Grafana is reachable through Caddy. Prometheus, Loki, pve-exporter, and cAdvisor are not public.
- PVE access uses a read-only API token; never root credentials.
- No plaintext secrets in Compose files; use the vault.
- Pin every binary and image version; do not deploy `latest`.
- Keep external Kuma monitoring; the local stack is not the only alert path.
- SMART polling must not wake sleeping HDDs. Use `smartctl_exporter` with `--smartctl.powermode-check=standby` and an interval of at least `300s`.

## Review Focus

- A SMART exporter that wakes the 10 TB HDDs would defeat the standby policy.
- Prometheus or Loki retention could fill the 75 GiB free on appdata.
- cAdvisor cardinality and Grafana/Prometheus queries can exceed the memory caps.
- A PVE token with write access or guest-agent calls could interfere with backups.
- A Grafana outage must not become a silent monitoring outage; Kuma stays external.
- High-cardinality log labels can make Loki expensive; labels stay bounded.

## File Structure

Create:

- `compose/observability/compose.yaml`
- `compose/observability/.env.j2`
- `compose/observability/prometheus.yml.j2`
- `compose/observability/loki-config.yml.j2`
- `compose/observability/pve.yml.j2`
- `compose/observability/grafana-datasources.yml.j2`
- `roles/observability_agents/defaults/main.yml`
- `roles/observability_agents/tasks/main.yml`
- `roles/observability_agents/handlers/main.yml`
- `roles/observability_agents/templates/node_exporter.service.j2`
- `roles/observability_agents/templates/smartctl_exporter.service.j2`
- `roles/observability_agents/templates/alloy.service.j2`
- `roles/observability_agents/templates/alloy-pve.alloy.j2`
- `roles/observability_agents/templates/alloy-docker.alloy.j2`
- `inventory/group_vars/pve/observability.yml`
- `inventory/group_vars/docker/observability.yml`
- `docs/observability.md`

Modify:

- `playbooks/pve.yml`
- `playbooks/docker.yml`
- `inventory/group_vars/docker/compose.yml`
- `compose/caddy-cloudflare/home.caddy.j2`
- `inventory/group_vars/docker/vault.yml`
- `README.md`
- `docs/monitoring.md`
- `docs/status.md`

---

### Task 1: Confirm capacity and remove the stopped workloads

**Files:**

- Verify: `compose/minecraft/.env.j2`
- Verify: `compose/homelable/compose.yaml`
- Verify: `inventory/group_vars/docker/compose.yml`

**Interfaces:**

- Consumes: current live state from `docker-1`
- Produces: at least 5 GiB available before the observability stack starts

- [ ] **Step 1: Measure capacity**

Run:

```bash
ssh boss@docker-1.han-diatonic.ts.net 'free -h; df -h /mnt/appdata; docker ps -q | wc -l'
```

Expected: `available` at least 5 GiB, `/mnt/appdata` at least 50 GiB free, and no Frigate, LiteLLM, or Homelable MCP containers running.

- [ ] **Step 2: Remove the stopped Frigate and MCP containers**

Run only after confirming Frigate runs on the other device:

```bash
ssh boss@docker-1.han-diatonic.ts.net \
  'docker rm -f frigate-krm homelable-mcp-1'
```

Expected: both commands print the container names, and `docker ps -a` no longer lists them.

- [ ] **Step 3: Delete the old Frigate data after verification**

Run only after the other device is proven authoritative:

```bash
ssh boss@docker-1.han-diatonic.ts.net 'rm -rf /mnt/appdata/frigate /opt/compose/frigate-krm'
```

Expected: `test ! -e /mnt/appdata/frigate` succeeds.

- [ ] **Step 4: Leave LiteLLM stopped**

Do not remove LiteLLM yet. It is no longer running, but it remains in `compose_stacks` and will restart on the next full Compose reconcile. Remove it from `compose_stacks` and its Caddy routes in a separate decommission change.

- [ ] **Step 5: Commit the capacity-related repository changes**

```bash
git add compose/minecraft/.env.j2 compose/homelable/compose.yaml inventory/group_vars/docker/compose.yml
git commit -m "chore: free capacity for observability stack"
```

Do not stage unrelated worktree changes.

---

### Task 2: Create the read-only Proxmox API token

**Files:**

- Modify: `inventory/group_vars/docker/vault.yml`
- Document: `docs/observability.md`

**Interfaces:**

- Produces: `vault_pve_exporter_token` and user `prometheus@pve`

- [ ] **Step 1: Create the PVE user and token**

Run on the PVE host as root:

```bash
pveum user add prometheus@pve --comment "Prometheus read-only exporter"
pveum acl modify / --users prometheus@pve --roles PVEAuditor
pveum user token add prometheus@pve prometheus --privsep 0
```

Expected: the token command prints the token value exactly once.

- [ ] **Step 2: Prove read-only access**

Run from `docker-1` with the token value:

```bash
curl -fsS -k \
  -H 'Authorization: PVEAPIToken=prometheus@pve!prometheus=<token>' \
  https://10.77.0.1:8006/api2/json/version
```

Expected: HTTP 200 with a PVE version JSON object. A write request must return 403; do not test writes against production state.

- [ ] **Step 3: Store the token in the vault**

Add to `inventory/group_vars/docker/vault.yml`:

```yaml
vault_pve_exporter_token: !vault |
  <ansible-vault encrypt_string output>
```

Use `ansible-vault encrypt_string`; never commit the plaintext token.

- [ ] **Step 4: Document the token scope**

Create `docs/observability.md` with the user, role, token id, rotation procedure, and the fact that the token is read-only and used only by `pve-exporter`.

- [ ] **Step 5: Commit**

```bash
git add inventory/group_vars/docker/vault.yml docs/observability.md
git commit -m "feat: add read-only PVE exporter token"
```

---

### Task 3: Add host agents for metrics and SMART

**Files:**

- Create: `roles/observability_agents/*`
- Create: `inventory/group_vars/pve/observability.yml`
- Create: `inventory/group_vars/docker/observability.yml`
- Modify: `playbooks/pve.yml`
- Modify: `playbooks/docker.yml`

**Interfaces:**

- Consumes: nothing from earlier tasks
- Produces: `10.77.0.1:9100` PVE node metrics, `10.77.0.1:9633` PVE SMART, `10.77.0.2:9100` Docker VM metrics

- [ ] **Step 1: Define versions and addresses**

In `roles/observability_agents/defaults/main.yml`, pin exact versions and checksums for `node_exporter` and `smartctl_exporter`. Set host-specific values in the group vars:

```yaml
# inventory/group_vars/pve/observability.yml
observability_node_exporter_listen: "10.77.0.1:9100"
observability_smartctl_listen: "10.77.0.1:9633"
```

```yaml
# inventory/group_vars/docker/observability.yml
observability_node_exporter_listen: "10.77.0.2:9100"
```

Use the same role on both hosts with host-specific overrides.

- [ ] **Step 2: Install node_exporter**

Create `roles/observability_agents/tasks/main.yml` tasks that download the pinned archive, verify its checksum, install `/usr/local/bin/node_exporter`, render the systemd unit, and enable it. The unit must include:

```ini
[Service]
MemoryMax=128M
ExecStart=/usr/local/bin/node_exporter --web.listen-address=<host-address>:9100
```

- [ ] **Step 3: Install smartctl_exporter on PVE only**

Condition on `inventory_hostname` being the PVE host. Install the pinned binary and unit:

```ini
[Service]
MemoryMax=128M
ExecStart=/usr/local/bin/smartctl_exporter \
  --web.listen-address=10.77.0.1:9633 \
  --smartctl.powermode-check=standby \
  --smartctl.interval=300s
```

Do not enable this unit on `docker-1`; the disks are not there.

- [ ] **Step 4: Wire the role into both playbooks**

Add to `playbooks/pve.yml`:

```yaml
- { role: observability_agents, tags: [observability] }
```

Add to `playbooks/docker.yml`:

```yaml
- role: observability_agents
  tags: [observability]
```

- [ ] **Step 5: Deploy and verify the agents**

Run:

```bash
ansible-playbook playbooks/pve.yml --tags observability
ansible-playbook playbooks/docker.yml --tags observability
ssh boss@docker-1.han-diatonic.ts.net \
  'curl -fsS http://10.77.0.1:9100/metrics | head; curl -fsS http://10.77.0.1:9633/metrics | head; curl -fsS http://10.77.0.2:9100/metrics | head'
```

Expected: all three endpoints return Prometheus text metrics.

- [ ] **Step 6: Prove SMART does not wake sleeping disks**

Run on PVE after the 10 TB disks have reached standby:

```bash
sudo smartctl -n standby -a /dev/disk/by-id/ata-TOSHIBA_MG06ACA10TE_28W0A2QGFKQE
```

Expected: the command reports standby without spinning the disk up. Observe `Start_Stop_Count` and disk power state before and after an exporter interval; they must not increase because of polling.

- [ ] **Step 7: Commit**

```bash
git add roles/observability_agents inventory/group_vars/pve/observability.yml \
  inventory/group_vars/docker/observability.yml playbooks/pve.yml playbooks/docker.yml
git commit -m "feat: add pinned node and SMART exporters"
```

---

### Task 4: Add the metrics stack

**Files:**

- Create: `compose/observability/compose.yaml`
- Create: `compose/observability/.env.j2`
- Create: `compose/observability/prometheus.yml.j2`
- Create: `compose/observability/pve.yml.j2`
- Create: `compose/observability/grafana-datasources.yml.j2`
- Modify: `inventory/group_vars/docker/compose.yml`
- Modify: `compose/caddy-cloudflare/home.caddy.j2`
- Modify: `inventory/group_vars/docker/vault.yml`

**Interfaces:**

- Consumes: `10.77.0.1:9100`, `10.77.0.1:9633`, `10.77.0.2:9100`, `vault_pve_exporter_token`
- Produces: `prometheus:9090`, `grafana:3000`, `pve-exporter:9221`, `cadvisor:8080`

- [ ] **Step 1: Create the Compose stack**

Use these services, all pinned by digest:

```yaml
services:
  grafana:
    ports: ["127.0.0.1:3000:3000"]
    mem_limit: 256m
  prometheus:
    ports: ["127.0.0.1:9090:9090"]
    mem_limit: 1g
  pve-exporter:
    mem_limit: 128m
  cadvisor:
    mem_limit: 256m
    privileged: true
```

Use a dedicated `observability` bridge network. Mount appdata paths under `/mnt/appdata/observability/{grafana,prometheus}`. Add JSON-file logging rotation `50m × 1` to every service.

- [ ] **Step 2: Configure Prometheus scrapes**

Create `prometheus.yml.j2` with `scrape_interval: 60s` and these jobs:

```yaml
scrape_configs:
  - job_name: prometheus
    static_configs: [{targets: ["localhost:9090"]}]
  - job_name: node-pve
    static_configs: [{targets: ["10.77.0.1:9100"]}]
  - job_name: node-docker
    static_configs: [{targets: ["10.77.0.2:9100"]}]
  - job_name: smartctl-pve
    static_configs: [{targets: ["10.77.0.1:9633"]}]
  - job_name: cadvisor
    static_configs: [{targets: ["cadvisor:8080"]}]
  - job_name: pve
    metrics_path: /pve
    params:
      target: ["10.77.0.1"]
      cluster: ["1"]
      node: ["1"]
    static_configs: [{targets: ["pve-exporter:9221"]}]
```

Run Prometheus with:

```text
--storage.tsdb.retention.time=30d
--storage.tsdb.retention.size=8GB
```

Set `GOMEMLIMIT=800MiB`.

- [ ] **Step 3: Configure pve-exporter**

Create `pve.yml.j2`:

```yaml
default:
  user: prometheus@pve
  token_name: prometheus
  token_value: {{ vault_pve_exporter_token }}
  verify_ssl: false
```

`verify_ssl: false` is acceptable only because the exporter talks to the private `vmbr1` address and the token is read-only. Do not publish the exporter port.

- [ ] **Step 4: Configure Grafana**

Set these environment variables:

```text
GF_SECURITY_ADMIN_PASSWORD={{ vault_grafana_admin_password }}
GF_USERS_ALLOW_SIGN_UP=false
GF_AUTH_ANONYMOUS_ENABLED=false
GF_SERVER_ROOT_URL=http://grafana.home.arpa
```

Add `vault_grafana_admin_password` to the vault. Provision the Prometheus datasource at `http://prometheus:9090`.

- [ ] **Step 5: Wire Compose, Caddy, and the appdata configs**

Add `observability` to `compose_stacks`. Add `prometheus.yml.j2`, `pve.yml.j2`, and `grafana-datasources.yml.j2` to `compose_config_templates` with destinations under `/mnt/appdata/observability`. Add the home Caddy route:

```caddyfile
http://grafana.home.arpa {
    import home
    reverse_proxy 127.0.0.1:3000
}
```

- [ ] **Step 6: Validate and deploy**

Run:

```bash
.venv/bin/python tests/check_compose.py
ansible-playbook playbooks/docker.yml --limit docker-1 --tags compose \
  -e '{"compose_stacks":["caddy-cloudflare","observability"]}'
```

Expected: Compose validation passes and the two stacks start.

- [ ] **Step 7: Prove metrics**

Run from `docker-1`:

```bash
curl -fsS http://127.0.0.1:3000/api/health
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS 'http://127.0.0.1:9090/api/v1/targets?state=active'
curl -fsS http://127.0.0.1:3000/api/health
```

Expected: Grafana health is `ok`; Prometheus is ready; every target is `UP`.

- [ ] **Step 8: Commit**

```bash
git add compose/observability inventory/group_vars/docker/compose.yml \
  compose/caddy-cloudflare/home.caddy.j2 inventory/group_vars/docker/vault.yml
git commit -m "feat: add Prometheus and Grafana metrics stack"
```

---

### Task 5: Add Loki and Alloy for logs

**Files:**

- Create: `compose/observability/loki-config.yml.j2`
- Create: `roles/observability_agents/templates/alloy.service.j2`
- Create: `roles/observability_agents/templates/alloy-pve.alloy.j2`
- Create: `roles/observability_agents/templates/alloy-docker.alloy.j2`
- Modify: `compose/observability/compose.yaml`
- Modify: `roles/observability_agents/tasks/main.yml`
- Modify: `inventory/group_vars/docker/compose.yml`
- Modify: `inventory/group_vars/pve/observability.yml`
- Modify: `inventory/group_vars/docker/observability.yml`

**Interfaces:**

- Consumes: Loki push URL from Alloy
- Produces: `http://10.77.0.2:3100/loki/api/v1/push` and Grafana Loki datasource

- [ ] **Step 1: Add Loki to Compose**

Add a single-binary Loki service with filesystem storage:

```yaml
loki:
  mem_limit: 512m
  ports:
    - "10.77.0.2:3100:3100"
```

Set `retention_period: 720h`, enable compactor retention, and set `GOMEMLIMIT=400MiB`. Do not publish Loki on a public interface.

- [ ] **Step 2: Install Alloy on both hosts**

Extend `observability_agents` with a pinned Alloy binary, unit, and config. The unit must include:

```ini
[Service]
MemoryMax=256M
ExecStart=/usr/local/bin/alloy run /etc/alloy/config.alloy
```

On PVE, ship journald logs for `pveproxy`, `pvedaemon`, `pvestatd`, `pve-firewall`, `smartd`, and `zfs-zed`. On `docker-1`, ship Docker container logs with labels `host`, `container`, `compose_project`, and `stream`. Do not use unbounded labels such as request IDs or full paths.

- [ ] **Step 3: Configure Alloy output**

Both hosts write to:

```text
http://10.77.0.2:3100/loki/api/v1/push
```

Use a bounded batch and retry configuration. Drop obvious debug and health-check noise before ingestion.

- [ ] **Step 4: Deploy and verify**

Run:

```bash
ansible-playbook playbooks/pve.yml --tags observability
ansible-playbook playbooks/docker.yml --tags observability
ansible-playbook playbooks/docker.yml --limit docker-1 --tags compose \
  -e '{"compose_stacks":["caddy-cloudflare","observability"]}'
ssh boss@docker-1.han-diatonic.ts.net 'curl -fsS http://10.77.0.2:3100/ready'
```

Expected: Loki reports ready; Grafana Explore returns recent PVE and Docker logs.

- [ ] **Step 5: Prove retention and disk use**

Run:

```bash
ssh boss@docker-1.han-diatonic.ts.net 'df -h /mnt/appdata; du -sh /mnt/appdata/observability/loki'
```

Expected: disk use grows predictably and remains below the `75 GiB` headroom. Record the first-week ingestion rate before considering a 90-day retention.

- [ ] **Step 6: Commit**

```bash
git add compose/observability roles/observability_agents inventory/group_vars
git commit -m "feat: add Loki and Alloy log pipeline"
```

---

### Task 6: Add Grafana datasources and dashboards

**Files:**

- Modify: `compose/observability/grafana-datasources.yml.j2`
- Create: `compose/observability/grafana-dashboards.yml` (optional provisioning map)
- Create: `compose/observability/dashboards/*.json` (exported dashboards)
- Modify: `compose/observability/compose.yaml`
- Modify: `inventory/group_vars/docker/compose.yml`

**Interfaces:**

- Consumes: `prometheus:9090`, `loki:3100`
- Produces: working Grafana dashboards

- [ ] **Step 1: Provision datasources**

Configure Prometheus and Loki as default datasources. Verify both through Grafana's datasource health endpoint or UI.

- [ ] **Step 2: Import baseline dashboards**

Import Node Exporter Full (`1860`), a current cAdvisor dashboard, and the pve-exporter dashboard recommended by the exporter project. Record the exact dashboard IDs and source URLs in `docs/observability.md`.

- [ ] **Step 3: Create one homelab overview dashboard**

Include:

- PVE and Docker VM CPU, memory, disk, network.
- ZFS pool health/capacity and SMART temperature/health.
- Per-container CPU/memory for `docker-1`.
- PVE VM/CT status and backup freshness.
- Log volume and error rate by host/container.

- [ ] **Step 4: Export dashboards as code**

Export the finished dashboards to JSON and provision them from files. Do not leave production dashboards only in Grafana's SQLite database.

- [ ] **Step 5: Verify**

Open `http://grafana.home.arpa` through Caddy/Tailscale and confirm every panel has data. Check that the datasource test passes for both Prometheus and Loki.

- [ ] **Step 6: Commit**

```bash
git add compose/observability inventory/group_vars/docker/compose.yml
git commit -m "feat: provision observability dashboards"
```

---

### Task 7: Add alerting and external watch

**Files:**

- Modify: `compose/observability/compose.yaml`
- Modify: `docs/observability.md`
- Modify: `docs/monitoring.md`

**Interfaces:**

- Consumes: Grafana Alerting, existing ntfy topics, external Kuma
- Produces: metric/log alerts without replacing Kuma

- [ ] **Step 1: Add an ntfy contact point**

Configure Grafana Alerting with the existing ntfy URL/topic. Test the contact point from the UI.

- [ ] **Step 2: Add only high-signal rules**

Start with:

- Prometheus target down for 5 minutes.
- Node filesystem above 85% for 15 minutes.
- SMART health not `PASSED`.
- Disk temperature above the per-drive threshold.
- PVE storage above 85%.
- Prometheus/Loki data filesystem above 85%.

Do not duplicate every Kuma uptime check in Grafana.

- [ ] **Step 3: Add the external Kuma monitor**

Create a Kuma monitor for the Grafana URL. Keep the existing host and service monitors unchanged. If Grafana, Prometheus, or Loki dies, Kuma must still alert.

- [ ] **Step 4: Test one alert path**

Use Grafana's contact-point test or a temporary `vector(1)` rule. Do not stop production exporters or disks to force an alert.

- [ ] **Step 5: Commit**

```bash
git add compose/observability docs/observability.md docs/monitoring.md
git commit -m "feat: add observability alerts and external watch"
```

---

### Task 8: Document, verify, and define rollback

**Files:**

- Modify: `README.md`
- Modify: `docs/monitoring.md`
- Modify: `docs/status.md`
- Modify: `docs/observability.md`

**Interfaces:**

- Consumes: all previous tasks
- Produces: operator runbook and rollback path

- [ ] **Step 1: Update repository policy**

Remove Prometheus/Grafana from the non-goals, and refine the minimal-resources principle to say: VPS services stay Docker/Prometheus-free; home observability runs on `docker-1` under explicit memory limits.

- [ ] **Step 2: Write `docs/observability.md`**

Cover architecture, ports, data paths, retention, memory caps, PVE token rotation, dashboards, alert rules, backup/restore, and how to add a new scrape target or log source.

- [ ] **Step 3: Link the guide**

Link it from `README.md` and `docs/monitoring.md`. Update `docs/status.md` with the deployed state and current counts.

- [ ] **Step 4: Run the full offline gate**

```bash
.venv/bin/python tests/check_ansible.py
.venv/bin/python tests/check_compose.py
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
npx --yes markdownlint-cli2@0.23.3 '*.md' 'docs/**/*.md' 'files/**/*.md' '.github/**/*.md'
lychee --offline --include-fragments --no-progress '*.md' 'docs/**/*.md' 'files/**/*.md' '.github/**/*.md'
```

Expected: all checks pass.

- [ ] **Step 5: Prove live health**

```bash
ssh boss@docker-1.han-diatonic.ts.net 'free -h; df -h /mnt/appdata; docker stats --no-stream'
curl -fsS http://127.0.0.1:3000/api/health
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS http://10.77.0.2:3100/ready
```

Expected: at least 1.5 GiB available after the stack, appdata below 80%, and all health endpoints ready.

- [ ] **Step 6: Define rollback**

Rollback must be:

```bash
ansible-playbook playbooks/docker.yml --limit docker-1 --tags compose \
  -e '{"compose_stacks":["caddy-cloudflare"]}'
ssh boss@docker-1.han-diatonic.ts.net \
  'docker rm -f observability-grafana-1 observability-prometheus-1 observability-loki-1 observability-pve-exporter-1 observability-cadvisor-1'
```

Then disable/remove the observability agent units on both hosts and leave `/mnt/appdata/observability` intact for inspection. Do not delete data until the retention/backup decision is recorded.

- [ ] **Step 7: Commit**

```bash
git add README.md docs/monitoring.md docs/status.md docs/observability.md
git commit -m "docs: document observability stack and rollback"
```
