# Monitoring Cleanup and Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Gatus the only external watcher, remove Kuma and Unraid monitoring remnants, and put the remaining Grafana state and alert coverage under repository control.

**Architecture:** `mon-1` runs Caddy in front of native Gatus; `docker-1` runs Prometheus, Grafana, Loki, and exporters. Gatus owns external reachability, Grafana owns resource/state alerts, and ntfy is the only delivery transport. Grafana dashboards, contact points, and alert rules must be reproducible from Git, not only from the live database.

**Tech Stack:** Ansible, systemd, Gatus, Prometheus, Grafana, Loki, ntfy, SQLite.

**Spec:** This plan; the notification envelope is defined in `docs/notifications.md`.

## Global Constraints

- Dead-man’s switch for `mon-1` is explicitly out of scope; accepted risk.
- Gatus runs natively, not in Docker.
- Unraid is being removed; do not add new Unraid sources or push monitors.
- Gatus is the only external watcher; Kuma must not remain as a managed service.
- One authority per fact: inventory for hosts, role defaults/vars for values, Git for deployable state.
- Never commit plaintext tokens; ntfy and push secrets stay in vault.
- Keep `ntfy` messages in the envelope defined by `docs/notifications.md`.

## Progress

- [x] Task 1: Kuma roles/runtime/cron, mon backup check, and Gatus push
  endpoints removed. Gatus validates 18 endpoints and 0 external endpoints.
- [x] Task 2: `vault_monitoring_domain` / `monitoring_domain` replaced the
  Kuma-named variable; DNS value unchanged.
- [ ] Task 3: Unraid backup-collector deletion is waiting for the in-flight PVE
  backup refactor to settle.
- [x] Task 4 (dashboards): six dashboards exported to
  `compose/observability/dashboards/` and provisioned from Git; live Grafana
  reports `provisioned: true`.
- [ ] Task 4 (alert rules/contact points/policies) still live in Grafana DB.
- [ ] Tasks 5-7 pending.

## Review Focus

- Removing Kuma must not break Caddy, the monitoring domain, or existing Gatus checks.
- Empty external-endpoint configuration must render valid Gatus YAML.
- Removing the mon backup check must not leave a stale cron/state notification.
- Unraid deletion must not delete the `great-hornbill` PVE host key or PVE backup state.
- Grafana GitOps must not silently drop live alert rules or contact-point templates.

---

### Task 1: Retire Kuma and remove Gatus push monitors

**Files:**

- Modify: `inventory/group_vars/mon/gatus.yml`
- Modify: `inventory/group_vars/mon/mon.yml`
- Modify: `inventory/group_vars/mon/monitoring.yml`
- Modify: `inventory/group_vars/mon/vault.yml`
- Modify: `roles/gatus/templates/config.yaml.j2`
- Modify: `playbooks/mon.yml`
- Modify: `docs/monitoring.md`
- Delete: `roles/kuma/`
- Delete: `roles/kuma_backup/`
- Test: `tests/test_ntfy_style.py` plus rendered Gatus config validation.

**Interfaces:**

- Consumes: `gatus_port`, `gatus_push_token` (only while push endpoints exist), `kuma_domain`.
- Produces: Gatus config with `external-endpoints` omitted when empty; no Kuma role or backup role.

- [ ] **Step 1: Remove Unraid push endpoint variables and the push token**

Delete `gatus_external_endpoints` and `gatus_push_token` from
`inventory/group_vars/mon/gatus.yml`. Remove `vault_gatus_push_token` from
`inventory/group_vars/mon/vault.yml`.

- [ ] **Step 2: Make Gatus external endpoints optional in the template**

Wrap the `external-endpoints:` block in
`{% if gatus_external_endpoints | length > 0 %}`. If the variable is absent,
the block is omitted entirely so Gatus validates without a null list.

- [ ] **Step 3: Remove Kuma service/backup wiring**

Remove Kuma variables from `inventory/group_vars/mon/mon.yml`, the
`kuma_backup` play from `playbooks/mon.yml`, and the mon backup-freshness
settings from `inventory/group_vars/mon/monitoring.yml`. Delete
`roles/kuma/` and `roles/kuma_backup/`.

- [ ] **Step 4: Remove Kuma from docs**

Update `docs/monitoring.md` to remove rollback language and Kuma backup
references. Keep the monitoring domain temporarily; rename it in Task 2.

- [ ] **Step 5: Verify rendered Gatus config and deploy**

Run the style tests and render the Gatus config with Ansible. Start the
binary against the rendered config with a temporary SQLite directory; expect
`Validated N endpoints`, no external-endpoint null error, and no Kuma service.

- [ ] **Step 6: Remove Kuma runtime state from mon-1**

Run `systemctl disable --now kuma` if still present, remove
`/etc/systemd/system/kuma.service`, `/opt/uptime-kuma`, `/opt/kuma-backup`.
Do not remove Caddy or its certificates.

- [ ] **Step 7: Commit**

```bash
git add inventory/group_vars/mon/gatus.yml inventory/group_vars/mon/mon.yml \
  inventory/group_vars/mon/monitoring.yml inventory/group_vars/mon/vault.yml \
  roles/gatus/templates/config.yaml.j2 playbooks/mon.yml docs/monitoring.md
git add -A roles/kuma roles/kuma_backup
git commit -m "chore: retire Kuma and remove push monitors"
```

### Task 2: Rename the monitoring domain and remove Kuma vocabulary

**Files:**

- Modify: `inventory/group_vars/mon/vault.yml`
- Modify: `inventory/group_vars/mon/mon.yml`
- Modify: `roles/gatus/defaults/main.yml`
- Modify: `docs/monitoring.md`
- Modify: `README.md`

- [ ] Add `vault_monitoring_domain` with the existing domain value, replace
  `vault_kuma_domain`, and use `monitoring_domain` everywhere.
- [ ] Keep the DNS name unchanged unless explicitly requested.
- [ ] Update docs and README to say Gatus/status, not Kuma.

### Task 3: Remove the Unraid backup-collector subsystem

**Files:**

- Delete: `playbooks/unraid.yml`
- Delete: `files/unraid/`
- Delete: `docs/backups-unraid.md`
- Modify: `inventory/hosts.ini` remove `[unraid]`
- Modify: `roles/pve_backup/defaults/main.yml` remove Unraid collector sources
- Modify: PVE backup docs and `docs/status.md`
- Preserve: `files/ssh/great-hornbill.pub` because it is the PVE host key.

- [ ] Wait for the in-flight PVE backup refactor to settle before deleting
  shared collector code.
- [ ] Remove Unraid-specific sources and `/opt/kuma-backup` references.
- [ ] Run the full gate; commit separately.

### Task 4: Put Grafana dashboards and alerting into Git

**Files:**

- Create: `compose/observability/dashboards/*.json`
- Create: `compose/observability/alerting/contact-points.json`
- Create: `compose/observability/alerting/rules.json`
- Create: `compose/observability/alerting/policies.json`
- Modify: `roles/compose_stacks` or add an Ansible provisioning role
- Test: `tests/check_compose.py`, plus a render/validate test.

- [ ] Export the live dashboards, contact points, rules, and policy.
- [ ] Store them without secrets; contact-point tokens/URLs come from vault.
- [ ] Apply them idempotently with the Grafana provisioning API.
- [ ] Verify the live IDs and labels match the repository.
- [ ] Commit.

### Task 5: Close alert-coverage gaps

- [ ] TLS certificate expiry in Gatus.
- [ ] Inode usage.
- [ ] Docker unhealthy/OOM/restart-loop.
- [ ] PVE backup freshness/failure.
- [ ] ZFS scrub/checksum errors.
- [ ] UPS battery health/charge.
- [ ] NTP/time drift.
- [ ] Tailscale daemon state.
- [ ] SMART standby proof.
- [ ] Add/verify each rule through the GitOps path from Task 4.

### Task 6: Alert quality and maintenance

- [ ] Add `runbook_url` and concrete `description` annotations.
- [ ] Define Gatus maintenance windows and Grafana mute timings.
- [ ] Verify critical vs warning routing and check for duplicate alerts.
- [ ] Add a canary notification test.
- [ ] Update `docs/notifications.md` and `docs/observability.md`.

### Task 7: Final verification

- [ ] Run the full pre-merge gate.
- [ ] Verify Gatus public status page and all enabled checks.
- [ ] Verify Kuma is absent, no push endpoints remain, and no Unraid source
  remains in the monitoring inventory.
- [ ] Record the accepted mon-1 dead-man’s-switch risk in docs.
