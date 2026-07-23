# homelab-vps-proxy

Reproducible VPS stream proxy + lightweight monitoring for a self-hosted homelab, managed entirely by Ansible.

The VPS is a thin, replaceable edge node. It accepts inbound TCP/UDP traffic and forwards it to home servers over Tailscale. It holds no application data and never decrypts TLS — routing is done via SNI (`ssl_preread`) at L4.

---

## Principles

1. **Zero-trust oriented.** VPS stores no private data and forwards encrypted traffic only (L4 pass-through, no TLS termination).
2. **Declarative configuration.** You describe the infrastructure (services, domains, backends) in one YAML file. Nginx config is a generated artifact.
3. **Single responsibility.** Stream proxy + minimal monitoring. Nothing else runs here.
4. **Fully replaceable.** Rebuild any time from `git clone` + one `ansible-playbook` run.
5. **Minimal resources.** Runs on 1 vCPU / 500 MB RAM. Plain nginx + cron + bash. No Docker, no Prometheus.
6. **Signal over noise.** Alerts only when action is needed. Severity-based channels, state-based deduping.

---

## Architecture

```
                Internet
                   |
             Public IP (VPS)
                   |
            +-------------+
            | nginx stream|   ssl_preread: route by SNI, no TLS termination
            | (this repo) |   cron: bash health checks -> ntfy
            +-------------+
                   |
        Tailscale (MagicDNS names)
                   |
        +----------+-----------+
        |          |           |
     Unraid   Home Assistant  future hosts
```

The VPS sees only ciphertext. Certificates live on the home services (Caddy, Home Assistant, etc. issue their own).

---

## Repository layout

```
.
├── site.yml                        playbook (nginx + monitoring roles)
├── ansible.cfg
├── inventory/
│   └── hosts.ini                   your VPS
├── group_vars/
│   └── vps/
│       ├── vps.yml                 monitoring settings (checks, thresholds)
│       └── vault.yml               SECRETS: ntfy topics (ansible-vault encrypted)
├── vars/
│   └── proxy.yml                   THE single source of truth for the proxy
├── roles/
│   ├── nginx/
│   │   ├── tasks/validate.yml      declarative checks on proxy.yml
│   │   ├── tasks/main.yml          install, deploy, validate, reload
│   │   └── templates/
│   │       ├── nginx.conf.j2       main config
│   │       └── stream.conf.j2      upstreams + SNI map + servers (generated)
│   └── monitoring/                 bash checks + cron + .env (from group_vars)
├── scripts/                        monitoring checks (bash)
└── cron/
    └── homelab-monitoring.cron
```

---

## Requirements

- Control machine with Ansible (`pip install ansible-core`).
- VPS running Debian / Ubuntu (tested on 22.04+), reachable over SSH as root.
- Tailscale (or WireGuard) on the VPS with MagicDNS enabled.
- A reachable [ntfy.sh](https://ntfy.sh) topic for notifications.

---

## Configuration

### `vars/proxy.yml` — the only file you edit for routing

```yaml
services:
  unraid:
    listen: 443
    default: true # catch-all for unknown SNI on this port
    sni:
      - immich.example.com
      - jellyfin.example.com
      - paperless.example.com
      - nextcloud.example.com
    upstream:
      host: great-hornbill.tailnet-name.ts.net
      port: 443

  homeassistant:
    listen: 443
    sni:
      - ha.example.com
    upstream:
      host: ha-krm.tailnet.ts.net
      port: 443
```

Service schema:

| Field      | Required | Purpose                                                                          |
| ---------- | -------- | -------------------------------------------------------------------------------- |
| `listen`   | yes      | Port nginx listens on.                                                           |
| `protocol` | no       | `tcp` (default) or `udp`.                                                        |
| `sni`      | no       | TLS SNI hostnames routed here (tcp only, via `ssl_preread`).                     |
| `default`  | no       | `true` = fallback backend for unknown SNI on this listener.                      |
| `upstream` | yes      | One backend or a list: `host`, `port`, optional `backup`, `weight`, `max_fails`. |

Rules (enforced by `roles/nginx/tasks/validate.yml` before anything is deployed):

- SNI hostnames must be unique across all services.
- Services sharing a listen port must **all** use SNI — or be a single plain forward.
- SNI requires `protocol: tcp` (`ssl_preread` reads the TLS ClientHello).
- Every service needs `listen` and a non-empty `upstream`; every upstream entry needs `host` and `port`.
- At most one service per listener may set `default: true`. If none does, the first service on the port is the fallback.

Always use **MagicDNS names** (`host.tailnet.ts.net`), never raw `100.x` IPs.

#### Examples

Plain TCP forward (no SNI):

```yaml
minecraft:
  listen: 25565
  upstream:
    host: game.tailnet.ts.net
    port: 25565
```

UDP forward:

```yaml
voicechat:
  listen: 24454
  protocol: udp
  upstream:
    host: game.tailnet.ts.net
    port: 24454
```

Load balancing / backup (list upstream — no template changes needed):

```yaml
app:
  listen: 8443
  sni: [app.example.com]
  upstream:
    - host: server1.tailnet.ts.net
      port: 443
    - host: server2.tailnet.ts.net
      port: 443
      backup: true
```

### `group_vars/vps/` — monitoring + secrets

`vps.yml` holds plaintext settings: checked systemd units, disk threshold/mounts, HTTPS endpoints, host prefix. Deployed to `/opt/homelab-monitoring/.env`; the bash checks are unchanged.

`vault.yml` holds everything a public repo must not show:

| Vault var            | Used in                  | Why                                             |
| -------------------- | ------------------------ | ----------------------------------------------- |
| `vault_ntfy_topic_*` | `group_vars/vps/vps.yml` | ntfy topic name = password (read + post access) |
| `vault_vps_ip`       | `inventory/hosts.ini`    | keeps the VPS off scanner radars                |

Tailscale MagicDNS names and SNI domains stay plaintext in `vars/proxy.yml` — they are unreachable without tailnet auth and reveal nothing an attacker can use.

It must be encrypted with ansible-vault before committing:

```bash
# one-time setup
openssl rand -hex 16   # generate one value per topic
ansible-vault edit group_vars/vps/vault.yml

# store the vault password OUTSIDE the repo
echo 'your-vault-password' > ~/.vault_pass_homelab
chmod 600 ~/.vault_pass_homelab
# then uncomment vault_password_file in ansible.cfg
```

`vps.yml` references the secrets as `{{ vault_ntfy_topic_* }}`, so playbooks run transparently once the vault password is configured. The monitoring `.env` template uses `no_log`, so topics never appear in Ansible output.

Sanity check before pushing: `head -1 group_vars/vps/vault.yml` must start with `$ANSIBLE_VAULT;`.

### `inventory/hosts.ini`

```ini
[vps]
edge ansible_host="{{ vault_vps_ip }}" ansible_user=root
```

The VPS IP comes from the vault, so a public repo never reveals it.

---

## Usage

```bash
# first time / after any change to vars/proxy.yml or group_vars/vps.yml
ansible-playbook site.yml
```

What a run does:

1. Validates `vars/proxy.yml` declaratively (fails fast, VPS untouched).
2. Installs nginx, deploys `nginx.conf` and the generated `stream.d/proxy.conf`.
3. Removes stale stream configs, runs `nginx -t`, reloads nginx only on changes.
4. Deploys monitoring scripts, `.env`, cron jobs.

Add a new service = add a block to `vars/proxy.yml` + re-run. Everything else regenerates.

### Local render test (no VPS needed)

```bash
ansible-playbook test-render.yml
cat /tmp/rendered-stream.conf
```

---

## What gets monitored

Each check runs from cron and pushes to ntfy only on state transitions.

| Check             | Interval | Alerts on                         | Severity                    |
| ----------------- | -------- | --------------------------------- | --------------------------- |
| systemd services  | 15 min   | unit not active                   | critical → DOWN / RECOVERED |
| docker containers | 15 min   | container not running             | critical                    |
| HTTPS endpoints   | 15 min   | non-2xx/3xx response or timeout   | critical                    |
| disk usage        | 1 h      | usage > threshold                 | alert                       |
| security updates  | daily    | apt security updates available    | alert                       |
| reboot required   | daily    | `/var/run/reboot-required` exists | alert                       |

Notification channels are severity-first: `*-critical`, `*-alerts`, `*-info`. Three topics regardless of service count.

---

## Operations

```bash
# health checks on the VPS
sudo systemctl status nginx
sudo nginx -t
sudo ss -tlnp | grep nginx
cat /etc/nginx/stream.d/proxy.conf
journalctl -u nginx -n 50

# trigger a monitor manually
sudo bash /opt/homelab-monitoring/scripts/check-services.sh
```

### Migrate to a new VPS

1. Provision VPS, install Tailscale, update `inventory/hosts.ini`.
2. `ansible-playbook site.yml`.
3. Switch DNS A/AAAA records to the new VPS.

The home servers are untouched.

---

## Security notes

- **No TLS termination on the VPS.** Certificates and private keys live only on home servers.
- **Outbound to home only over Tailscale/WireGuard** — upstreams are MagicDNS names, never public IPs.
- **Port 80 returns 444.** No HTTP service is exposed.
- **server_tokens off**, stream access log disabled (no payload logging).
- Lock down SSH separately (key-only, fail2ban, non-default port). This repo does not manage SSH.

---

## Troubleshooting

| Symptom                                | Look at                                                               |
| -------------------------------------- | --------------------------------------------------------------------- |
| Playbook fails in validation tasks     | `vars/proxy.yml` — the assert message names the offending service.    |
| `nginx -t` task fails                  | Rendered `/etc/nginx/stream.d/proxy.conf` on the VPS.                 |
| Connection refused on a forwarded port | `ss -tlnp \| grep <port>`, `journalctl -u nginx`.                     |
| Wrong backend for a domain             | SNI hostname missing/duplicated in `vars/proxy.yml`; check the `map`. |
| Backend unreachable                    | `nc -vz <host>.ts.net <port>` from the VPS; check Tailscale.          |
| No ntfy messages arrive                | Topics in `group_vars/vps.yml`, run a check script manually.          |

---

## Non-goals

- Prometheus / Grafana / Loki / ELK / SIEM.
- Kubernetes, Docker Swarm, Nomad.
- TLS termination on the VPS.
- Hosting applications on the VPS.

Stay boring. Replace the VPS in 5 minutes. Sleep at night.
