# Homelab Monitoring Philosophy

## Goals

This monitoring setup is designed for a personal homelab and self-hosted environment.

Primary goals:

- minimal maintenance
- low complexity
- high signal / low noise
- reproducible setup
- easy migration to a new VPS/server
- understandable by both humans and AI agents
- no enterprise observability stack
- no monitoring for the sake of monitoring

This is intentionally **NOT**:

- Prometheus/Grafana/Loki
- ELK stack
- Kubernetes observability
- enterprise SIEM
- per-service log aggregation

The system should behave more like a reliable appliance than a DevOps project.

---

# Core Principles

## 1. Severity-first, not service-first

Notifications are grouped by importance/severity, NOT by service.

### Bad

```text id="9zwp1n"
minecraft-alerts
immich-alerts
couchdb-alerts
nginx-alerts
```

### Good

```text id="w6a0lr"
homelab-critical
homelab-alerts
homelab-info
```

Per-service channels quickly become notification chaos and are ignored.

Severity-based channels are easier for humans to process.

---

# Notification Channels

## Critical

Topic:

```text id="7r8m0d"
homelab-critical
```

Used ONLY for issues requiring immediate attention.

Examples:

- disk failure
- array degraded
- UPS low battery
- VPS unreachable
- tailscale down
- reverse proxy down
- backup failures
- repeated service crashes
- SMART errors

These notifications should be rare.

---

## Alerts

Topic:

```text id="f9r6ae"
homelab-alerts
```

Used for important but non-emergency issues.

Examples:

- updates available
- reboot required
- container stopped
- disk usage high
- certificate renewal failed
- minecraft server stopped
- VM stopped unexpectedly

These can wait until later in the day.

---

## Info

Topic:

```text id="s8n7wc"
homelab-info
```

Used for informational events.

Examples:

- backup completed
- parity completed
- startup notifications
- monthly reports
- successful maintenance tasks

These should never require immediate action.

---

# Notification Formatting

## Titles

All notifications should contain:

- severity context
- service prefix

Examples:

```text id="x1v4gb"
[VPS] Security updates available
[MC] Backup completed
[UNRAID] Disk usage warning
```

Suggested prefixes:

- [VPS]
- [MC]
- [IMMICH]
- [UNRAID]
- [VM]
- [COUCHDB]

---

# Notification Content

Notifications should be:

- short
- readable on mobile
- human-oriented
- actionable

Avoid:

- large logs
- stack traces
- spammy metrics
- verbose diagnostics

### Good

```text id="x64e2l"
Security updates: 3
Total packages: 12
```

### Bad

```text id="kr7zq0"
Full apt package listing...
```

---

# Anti-Spam Philosophy

The system MUST avoid repeated alerts.

### Bad

```text id="4t1qhy"
NGINX DOWN
NGINX DOWN
NGINX DOWN
```

### Good

```text id="n7r5jb"
NGINX DOWN
NGINX RECOVERED
```

---

# State-Based Notifications

Checks should maintain state files.

Example:

```text id="ev1r0h"
/tmp/nginx-down.state
```

Behavior:

- send DOWN notification once
- do not repeat while still failing
- send RECOVERED once
- remove state file

This is more important than dashboards or advanced metrics.

---

# What Should Be Monitored

Only monitor things that materially affect availability or data safety.

---

# VPS Monitoring

## Required

- nginx active
- tailscaled active
- disk usage
- reboot required
- security updates available
- HTTPS endpoint reachable

## Optional

- memory critically low
- abnormal load average

## Avoid

- CPU graphs
- bandwidth graphs
- Prometheus exporters
- detailed system metrics

---

# Unraid Monitoring

## Required

- array degraded
- SMART errors
- parity issues
- disk usage
- backup failures

## Optional

- VM stopped
- docker restart notifications

## Avoid

- excessive docker logging
- detailed performance metrics

---

# Minecraft Monitoring

## Required

- container alive
- backup success/failure

## Optional

- world disk usage
- restart notifications

## Avoid

- player join/leave spam
- TPS spam
- JVM metrics
- per-minute monitoring

Minecraft monitoring should focus on:

- world safety
- backups
- uptime

NOT telemetry.

---

# Logging Philosophy

This setup is NOT a centralized logging platform.

Logs should remain local unless:

- an event requires action
- the service becomes unavailable
- data integrity is at risk

Avoid:

- centralized log ingestion
- storing logs indefinitely
- shipping all logs to VPS
- creating observability infrastructure

---

# Deployment Philosophy

The monitoring system must be:

- idempotent
- git-managed
- reproducible
- migration-friendly

A new VPS setup should look like:

```bash id="sx3l9m"
git clone ...
cd homelab-monitoring

cp .env.example .env
nano .env

./install.sh
```

And nothing else.

---

# Cron Philosophy

Use:

```text id="3m1gqn"
/etc/cron.d/
```

NOT:

```text id="4mz1yr"
crontab -e
```

Reasons:

- reproducible
- no duplicate entries
- easy updates
- declarative
- safe reinstall behavior

---

# Environment Variables

All configuration should live in:

```text id="l8j4ep"
/opt/homelab-monitoring/.env
```

Scripts must source this file.

Example:

```bash id="4j1mfy"
source /opt/homelab-monitoring/.env
```

Never hardcode:

- ntfy topics
- domains
- thresholds
- API tokens

---

# Ntfy Philosophy

Use [ntfy.sh](https://ntfy.sh?utm_source=chatgpt.com) as a lightweight notification transport.

Do NOT self-host unless there is a real reason.

Use:

- long random topic names
- separate topics by severity
- mobile push notifications

Avoid:

- Telegram dependencies
- complicated chat bots
- notification middleware

---

# Overall Philosophy

The homelab should:

- stay understandable
- stay maintainable
- survive long periods without attention
- recover easily after migration

The goal is operational calmness, not observability perfection.
