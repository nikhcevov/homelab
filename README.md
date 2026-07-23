# homelab-vps-proxy

Reproducible VPS edge node for a self-hosted homelab, managed entirely by Ansible.

The VPS is a thin, replaceable edge node. It accepts inbound TCP/UDP traffic and forwards it to home servers over Tailscale. It holds no application data and never decrypts TLS — routing is done via SNI (`ssl_preread`) at L4.

A fresh VPS becomes fully operational with three steps:

1. Install Debian 12 (Bookworm), x86_64.
2. Set up SSH access as root (only Python 3 is required on the target).
3. Run `ansible-playbook site.yml`.

This repository is the single source of truth. All infrastructure changes go through Git + Ansible — never manual edits on the server.

---

## Principles

1. **Zero-trust oriented.** VPS stores no private data and forwards encrypted traffic only (L4 pass-through, no TLS termination).
2. **Declarative configuration.** You describe the desired state (services, domains, firewall rules, sshd settings) in YAML. Configs are generated artifacts.
3. **Idempotent.** Re-running any playbook changes nothing if the server is already in the desired state. Standard Ansible modules everywhere; shell/command only as a last resort.
4. **Single source of truth.** If a configuration cannot be restored from this repo, it is an architecture bug.
5. **Layered.** Full deployment via `site.yml`, or any single layer via its own playbook.
6. **Minimal resources.** Runs on 1 vCPU / 500 MB RAM. No Docker, no Prometheus.
7. **Signal over noise.** Alerts only when action is needed. Severity-based channels, state-based deduping.

---

## Architecture

```
                Internet
                   |
             Public IP (VPS)
                   |
            +-------------+
            | nginx stream|   ssl_preread: route by SNI, no TLS termination
            | ufw/fail2ban|   cron: bash health checks -> ntfy
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

## Layers

Deployment is split into independent layers. `site.yml` runs them all in order; each layer is also a standalone playbook.

| Layer     | Playbook        | Roles         | What it does                                                                                  |
| --------- | --------------- | ------------- | --------------------------------------------------------------------------------------------- |
| bootstrap | `bootstrap.yml` | common, ssh   | apt upgrade, base packages, timezone, locale, unattended-upgrades, admin user, sshd hardening |
| security  | `security.yml`  | ufw, fail2ban | declarative firewall, sshd jail                                                               |
| network   | `network.yml`   | tailscale     | tailnet membership (install, auth, autostart)                                                 |
| proxy     | `proxy.yml`     | nginx         | L4 stream proxy generated from `vars/proxy.yml`                                               |
| services  | `services.yml`  | monitoring    | bash health checks + cron + ntfy (future services land here)                                  |

```bash
ansible-playbook site.yml        # everything, in order
ansible-playbook proxy.yml       # just re-render and reload the proxy
ansible-playbook security.yml    # just firewall + fail2ban
```

Layers depend on each other left to right (proxy needs tailnet DNS; monitoring expects nginx). Bootstrap is safe to re-run at any time.

---

## Repository layout

```
.
├── site.yml                        full deployment (imports all layers)
├── bootstrap.yml                   layer 1: base system + ssh
├── security.yml                    layer 2: ufw + fail2ban
├── network.yml                     layer 3: tailscale
├── proxy.yml                       layer 4: nginx stream proxy
├── services.yml                    layer 5: monitoring (+ future services)
├── test-render.yml                 local render test (no VPS needed)
├── requirements.yml                ansible collections
├── ansible.cfg
├── inventory/
│   └── hosts.ini                   your VPS (IP from the vault)
├── group_vars/
│   └── vps/
│       ├── bootstrap.yml           packages, timezone, locale, admin user
│       ├── ssh.yml                 sshd settings (port, auth modes)
│       ├── security.yml            ufw rules, fail2ban policy
│       ├── tailscale.yml           tailscale hostname, auth key ref
│       ├── vps.yml                 monitoring settings (checks, thresholds)
│       └── vault.yml               SECRETS (ansible-vault encrypted)
├── vars/
│   └── proxy.yml                   THE single source of truth for routing
├── roles/
│   ├── common/                     base system bootstrap
│   ├── ssh/                        sshd drop-in hardening (validated by sshd -t)
│   ├── ufw/                        declarative firewall
│   ├── fail2ban/                   sshd jail (systemd backend)
│   ├── tailscale/                  tailnet install + auth
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

- Control machine: `pip install ansible-core` (or `brew install ansible`), then:
  ```bash
  ansible-galaxy collection install -r requirements.yml
  ```
- VPS: **Debian 12 (Bookworm), x86_64**, reachable over SSH as root. **Python 3 is the only requirement** — everything else is installed by Ansible.
- A Tailscale tailnet with MagicDNS enabled.
- A reachable [ntfy.sh](https://ntfy.sh) topic for notifications.

---

## First run (new VPS)

```bash
# 1. one-time: collections + vault password (store it OUTSIDE the repo)
ansible-galaxy collection install -r requirements.yml
echo 'your-vault-password' > ~/.vault_pass_homelab && chmod 600 ~/.vault_pass_homelab
#    then point vault_password_file in ansible.cfg at it

# 2. add secrets (see "Secrets" below)
ansible-vault edit group_vars/vps/vault.yml

# 3. review group_vars/vps/*.yml and vars/proxy.yml

# 4. deploy
ansible-playbook site.yml
```

**SSH key on a brand-new VPS.** If the provider injected your public key at provisioning, nothing to do. If you only have a root password, put your public key into `bootstrap_root_ssh_keys` in `group_vars/vps/bootstrap.yml` (public keys are not secrets — they belong in Git), then run the first pass with password auth:

```bash
ansible-playbook bootstrap.yml -k   # asks for the root SSH password once
ansible-playbook site.yml           # key-only from here on
```

What a full run does:

1. **bootstrap** — upgrades apt, installs base packages, sets timezone/locale, enables unattended security upgrades, hardens sshd (validated by `sshd -t` before apply).
2. **security** — opens SSH + base ports + every listen port from `vars/proxy.yml` in ufw, enables the firewall (rules are added _before_ enabling, so the SSH session survives), configures fail2ban.
3. **network** — installs Tailscale from the official repo, authenticates with the vault auth key (skipped if the node is already connected), enables `tailscaled`.
4. **proxy** — validates `vars/proxy.yml` declaratively (fails fast, VPS untouched), installs nginx, deploys the generated stream config, runs `nginx -t`, reloads only on changes.
5. **services** — deploys monitoring scripts, `.env`, cron jobs.

Re-running `site.yml` on a configured server should report zero changes (idempotent).

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
      host: ha-krm.tailnet-name.ts.net
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

**Adding a service = adding a block here + `ansible-playbook site.yml`.** The nginx config, and (via `ufw_open_service_ports: true`) the firewall rule, are regenerated automatically — no template or ufw edits needed.

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

### `group_vars/vps/` — one file per concern

| File            | Configures    | Highlights                                                                                                              |
| --------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `bootstrap.yml` | common        | apt upgrade mode, package list, timezone, locale, unattended-upgrades, optional sudo admin user                         |
| `ssh.yml`       | ssh           | `sshd_port`, `sshd_password_authentication`, `sshd_permit_root_login`, `sshd_pubkey_authentication`, `sshd_allow_users` |
| `security.yml`  | ufw, fail2ban | default policies, static rules, `ufw_open_service_ports`, ban policy                                                    |
| `tailscale.yml` | tailscale     | `tailscale_hostname`, auth key (from vault)                                                                             |
| `vps.yml`       | monitoring    | checked units, disk threshold/mounts, HTTPS endpoints, host prefix                                                      |

The SSH port is defined once in `ssh.yml` and consumed by sshd, ufw and fail2ban — they can never drift apart.

Firewall rules come from three merged sources: the SSH port, the static `ufw_rules` list, and the listen ports of every service in `vars/proxy.yml`.

### Switching from root to an admin user

Bootstrap runs as root. To move daily management to a sudo user:

1. Set `bootstrap_admin_user` and `bootstrap_admin_user_ssh_keys` in `group_vars/vps/bootstrap.yml`.
2. Run `ansible-playbook bootstrap.yml`.
3. Switch `inventory/hosts.ini` to `ansible_user=<name>` and set `sshd_permit_root_login: "no"` in `group_vars/vps/ssh.yml`.
4. Re-run `ansible-playbook site.yml`.

### `inventory/hosts.ini`

```ini
[vps]
edge ansible_host="{{ vault_vps_ip }}" ansible_user=root

[vps:vars]
ansible_python_interpreter=/usr/bin/python3
```

The VPS IP comes from the vault, so a public repo never reveals it.

---

## Secrets

In Git: templates, roles, inventory, playbooks, service/domain lists.

**Never** in Git: SSH private keys, API tokens, Tailscale auth keys, passwords. All secrets live in `group_vars/vps/vault.yml`, encrypted with ansible-vault.

| Vault var                  | Used in                        | Why                                             |
| -------------------------- | ------------------------------ | ----------------------------------------------- |
| `vault_ntfy_topic_*`       | `group_vars/vps/vps.yml`       | ntfy topic name = password (read + post access) |
| `vault_vps_ip`             | `inventory/hosts.ini`          | keeps the VPS off scanner radars                |
| `vault_tailscale_auth_key` | `group_vars/vps/tailscale.yml` | tailnet join credential                         |

Plaintext files reference them as `{{ vault_* }}`, so playbooks run transparently once the vault password is configured. Secret-bearing tasks use `no_log`, so values never appear in Ansible output.

```bash
ansible-vault edit group_vars/vps/vault.yml
```

Sanity check before pushing: `head -1 group_vars/vps/vault.yml` must start with `$ANSIBLE_VAULT;`.

The Tailscale auth key can be left empty — authentication is then skipped (useful if the node was joined manually or uses an ephemeral-key-free flow).

---

## Local render test (no VPS needed)

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
sudo systemctl status nginx tailscaled fail2ban ssh
sudo nginx -t
sudo ss -tlnp | grep nginx
cat /etc/nginx/stream.d/proxy.conf
journalctl -u nginx -n 50

# firewall / jail state
sudo ufw status verbose
sudo fail2ban-client status sshd

# tailnet state
tailscale status

# trigger a monitor manually
sudo bash /opt/homelab-monitoring/scripts/check-services.sh
```

### Migrate to a new VPS

1. Provision VPS (Debian 12), set up root SSH access, put the new IP into the vault.
2. `ansible-playbook site.yml`.
3. Switch DNS A/AAAA records to the new VPS.

The home servers are untouched.

---

## Security notes

- **No TLS termination on the VPS.** Certificates and private keys live only on home servers.
- **Outbound to home only over Tailscale** — upstreams are MagicDNS names, never public IPs.
- **Port 80 returns 444.** No HTTP service is exposed.
- **server_tokens off**, stream access log disabled (no payload logging).
- SSH is key-only by default (`sshd_password_authentication: "no"`), root login is key-only (`prohibit-password`), sshd config is validated with `sshd -t` before every apply, and fail2ban watches the sshd journal.
- Default firewall policy: deny incoming, allow outgoing.

---

## Troubleshooting

| Symptom                                | Look at                                                                                  |
| -------------------------------------- | ---------------------------------------------------------------------------------------- |
| Playbook fails in validation tasks     | `vars/proxy.yml` — the assert message names the offending service.                       |
| `nginx -t` task fails                  | Rendered `/etc/nginx/stream.d/proxy.conf` on the VPS.                                    |
| Locked out after security layer        | Rules are added before ufw is enabled; check `sshd_port` vs `ansible_port` in inventory. |
| Tailscale auth task skips              | Node already connected (`tailscale status`), or empty auth key.                          |
| `sudo tailscale up` prompts for login  | Auth key expired — rotate it in the vault and re-run `network.yml`.                      |
| Connection refused on a forwarded port | `ss -tlnp \| grep <port>`, `journalctl -u nginx`, `ufw status`.                          |
| Wrong backend for a domain             | SNI hostname missing/duplicated in `vars/proxy.yml`; check the `map`.                    |
| Backend unreachable                    | `nc -vz <host>.ts.net <port>` from the VPS; check Tailscale.                             |
| No ntfy messages arrive                | Topics in `group_vars/vps/vps.yml`, run a check script manually.                         |

---

## Non-goals

- Prometheus / Grafana / Loki / ELK / SIEM.
- Kubernetes, Docker Swarm, Nomad.
- TLS termination on the VPS.
- Hosting applications on the VPS.

Stay boring. Replace the VPS in 5 minutes. Sleep at night.
