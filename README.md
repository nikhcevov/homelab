# homelab-vps-proxy

Reproducible VPS edge node for a self-hosted homelab, managed entirely by Ansible.

The VPS is a thin, replaceable edge node. It accepts inbound TCP/UDP traffic and forwards it to home servers over Tailscale. It holds no application data and never decrypts TLS — routing is done via SNI (`ssl_preread`) at L4.

The repository also manages two more fully independent hosts: a **VPN VPS** (`vpn.yml`, hosts group `vpn`) running native 3x-ui + Caddy — see [VPN VPS](#vpn-vps), and a **monitoring VPS** (`mon.yml`, hosts group `mon`) running native Uptime Kuma + Caddy — see [Monitoring VPS](#monitoring-vps).

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
8. **The tailnet is the management plane.** Every host is managed via its MagicDNS name; day-0 (install OS, add one SSH key, `tailscale up`) is the only manual step, everything after it is Ansible-only. Break-glass addresses (public IPs, LAN) are deliberately not stored in the repo.

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
| network   | `network.yml`   | tailscale     | tailnet membership (install, auth, autostart) — vps for proxy upstreams, mon for Kuma pull    |
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
│   └── hosts.ini                   all hosts, addressed by MagicDNS names
├── group_vars/
│   └── vps/
│       ├── bootstrap.yml           packages, timezone, locale, admin user
│       ├── ssh.yml                 sshd settings (port, auth modes)
│       ├── security.yml            ufw rules, fail2ban policy
│       ├── tailscale.yml           tailscale hostname, auth key ref
│       └── monitoring.yml          monitoring settings (checks, thresholds)
├── vars/
│   └── proxy.yml                   routing map (gitignored; ship proxy.example.yml)
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
- VPS: **Debian 12 (Bookworm), x86_64**, reachable over SSH as root **via the tailnet** (day-0 below). **Python 3 is the only requirement** — everything else is installed by Ansible.
- A Tailscale tailnet with MagicDNS enabled; `tailnet_domain` set in `group_vars/all/tailscale.yml`.
- A reachable [ntfy.sh](https://ntfy.sh) topic for notifications.

---

## First run (new VPS)

**Day-0 (manual, once, on the VPS):**

1. Provision the VPS (Debian 12) with your SSH public key injected by the provider (or add it via the provider console / web terminal).
2. Join the tailnet:

   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   tailscale up --hostname=edge-proxy
   ```

   Open the login URL, then **disable key expiry** for the node in the Tailscale admin console (Machines → node → Disable key expiry) — otherwise the node silently drops off the tailnet after 180 days and Ansible loses access.

3. Set `tailnet_domain` in `group_vars/all/tailscale.yml` (once, for the whole repo).

From here on the host is `edge-proxy.<tailnet>.ts.net` and everything is Ansible-only. Convention: the inventory name always matches the tailnet name.

**On the control machine:**

```bash
# 1. one-time: collections
ansible-galaxy collection install -r requirements.yml

# 2. add secrets (see "Secrets" below)
$EDITOR group_vars/all/vault.yml
# encrypt each secret value inline:
ansible-vault encrypt_string 'the-secret' --name vault_ntfy_topic_info   # paste block into vault.yml

# 3. review group_vars/vps/*.yml, then create the routing config
cp vars/proxy.example.yml vars/proxy.yml
$EDITOR vars/proxy.yml

# 4. deploy
ansible-playbook site.yml
```

**Extra SSH keys.** Drop the `.pub` into `files/ssh/` and list its filename in `bootstrap_root_ssh_keys` in `group_vars/vps/bootstrap.yml` — the common role authorizes them idempotently on every run. Public keys are not secrets — they belong in Git.

What a full run does:

1. **bootstrap** — upgrades apt, installs base packages, sets timezone/locale, enables unattended security upgrades, hardens sshd (validated by `sshd -t` before apply).
2. **security** — opens SSH + base ports + every listen port from `vars/proxy.yml` in ufw, enables the firewall (rules are added _before_ enabling, so the SSH session survives), configures fail2ban.
3. **network** — installs Tailscale from the official repo and reconciles settings on the already-joined node (day-0 join is manual; an auth key from the vault is an optional unattended path).
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
      host: unraid.tailnet-name.ts.net
      port: 443

  homeassistant:
    listen: 443
    sni:
      - ha.example.com
    upstream:
      host: homeassistant.tailnet-name.ts.net
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

| File             | Configures    | Highlights                                                                                                              |
| ---------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `bootstrap.yml`  | common        | apt upgrade mode, package list, timezone, locale, unattended-upgrades, optional sudo admin user                         |
| `ssh.yml`        | ssh           | `sshd_port`, `sshd_password_authentication`, `sshd_permit_root_login`, `sshd_pubkey_authentication`, `sshd_allow_users` |
| `security.yml`   | ufw, fail2ban | default policies, static rules, `ufw_open_service_ports`, ban policy                                                    |
| `tailscale.yml`  | tailscale     | `tailscale_hostname`, auth key (from vault)                                                                             |
| `monitoring.yml` | monitoring    | checked units, disk threshold/mounts, backup freshness, host prefix                                                     |

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
edge-proxy ansible_host=edge-proxy.{{ tailnet_domain }} ansible_user=root

[vps:vars]
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_private_key_file=~/.ssh/starling
```

Every host is addressed by its MagicDNS name — the tailnet is the only management plane. The domain is set once in `group_vars/all/tailscale.yml`, the per-host tailnet names in `group_vars/*/tailscale.yml`. Host IPs are not stored in the repo at all (not even in the vault): if tailscale is down, SSH in manually using the public IP or LAN address.

---

## Secrets

In Git: templates, roles, inventory, playbooks, service/domain lists.

**Never** in Git as plaintext: SSH private keys, API tokens, Tailscale auth keys, passwords, real domains. Secrets live in `group_vars/*/vault.yml` (shared ones in `group_vars/all/vault.yml`) as inline `!vault` blocks (`ansible-vault encrypt_string`) — keys and comments stay readable in diffs, values are ciphertext, and Ansible decrypts natively (no plugins). The real routing map `vars/proxy.yml` stays plaintext-gitignored (config, not credentials; copy `vars/proxy.example.yml`). To add or change a secret value:

```bash
ansible-vault encrypt_string 'the-secret' --name vault_kuma_domain
# paste the printed block into group_vars/mon/vault.yml, replacing the old one
```

The vault password lives in `.vault_pass` in the repo dir (gitignored, referenced by `vault_password_file` in `ansible.cfg`) — back it up into your password manager; losing it means losing all secrets.

| Vault var                  | Used in                         | Why                                                     |
| -------------------------- | ------------------------------- | ------------------------------------------------------- |
| `vault_*_domain`           | `group_vars/mon, vpn`           | keeps real domains out of the public repo               |
| `vault_ntfy_topic_*`       | `group_vars/all/monitoring.yml` | ntfy topic name = password (read + post access)         |
| `vault_xui_*_path`         | `host_vars/vpn-<cc>.yml`        | secret URL paths of the 3x-ui panel (Kuma monitor URLs) |
| `vault_tailscale_auth_key` | `group_vars/all/vault.yml`      | optional unattended tailnet join (shared reusable key)  |

Plaintext files reference them as `{{ vault_* }}`, so playbooks run transparently. Secret-bearing tasks use `no_log`, so values never appear in Ansible output.

The encrypted vaults travel with the repo, so no separate secret backup is needed — just keep the vault password (`.vault_pass`, gitignored) in your password manager.

Sanity check before pushing: `git grep -c '!vault' group_vars/` must show every secret value encrypted.

The Tailscale auth key can be left empty (the default flow) — nodes then join manually at day-0 and the role only reconciles settings. Set it only if you want a fully unattended VPS rebuild.

---

## Local render test (no VPS needed)

```bash
ansible-playbook test-render.yml
cat /tmp/rendered-stream.conf
```

---

## What gets monitored

Both hosts (`vps` and `vpn` groups) run the same monitoring role; each group has its own env config. Each check runs from cron and pushes to ntfy only on state transitions.

| Check             | Interval | Alerts on                         | Severity                    |
| ----------------- | -------- | --------------------------------- | --------------------------- |
| systemd services  | 15 min   | unit not active                   | critical → DOWN / RECOVERED |
| docker containers | 15 min   | container not running             | critical                    |
| disk usage        | 1 h      | usage > threshold                 | alert                       |
| security updates  | daily    | apt security updates available    | alert                       |
| reboot required   | daily    | `/var/run/reboot-required` exists | alert                       |
| backup freshness  | daily    | no archive / newest > 25 h old    | alert                       |

External health (HTTPS endpoints, TCP/UDP ports, certificates) is deliberately NOT checked here — that is Uptime Kuma's job on the central monitoring VPS. Empty lists disable a check (e.g. no docker on the VPN host). The VPN host monitors `x-ui caddy fail2ban cron ssh` and `/opt/vpn-backup/archives` freshness.

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

1. Provision VPS (Debian 12) with your SSH key, then day-0: install Tailscale, `tailscale up --hostname=edge-proxy`, disable key expiry. Same hostname = same MagicDNS name, no inventory change.
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

| Symptom                                | Look at                                                                                   |
| -------------------------------------- | ----------------------------------------------------------------------------------------- |
| Playbook fails in validation tasks     | `vars/proxy.yml` — the assert message names the offending service.                        |
| `nginx -t` task fails                  | Rendered `/etc/nginx/stream.d/proxy.conf` on the VPS.                                     |
| Locked out after security layer        | Rules are added before ufw is enabled; check `sshd_port` vs `ansible_port` in inventory.  |
| Tailscale auth task skips              | Node already connected (`tailscale status`), or empty auth key (day-0 manual join).       |
| Node fell off the tailnet              | Key expiry — re-run `tailscale up` on the host, then disable expiry in the admin console. |
| Connection refused on a forwarded port | `ss -tlnp \| grep <port>`, `journalctl -u nginx`, `ufw status`.                           |
| Wrong backend for a domain             | SNI hostname missing/duplicated in `vars/proxy.yml`; check the `map`.                     |
| Backend unreachable                    | `nc -vz <host>.ts.net <port>` from the VPS; check Tailscale.                              |
| No ntfy messages arrive                | Topics in `group_vars/*/monitoring.yml`, run a check script manually.                     |

---

## VPN VPS

A second, fully independent host (`vpn` inventory group): a VPN gateway running **native 3x-ui + Caddy**. No Docker, no Tailscale, no dependency on the home lab — it works even when the homelab is offline. Target OS: Debian 13 / Ubuntu 24.04+.

```
Internet
   |
 VPN VPS (vpn-nl)
   |-- Caddy        HTTPS + Let's Encrypt + reverse proxy (panel, subscriptions)
   |-- 3x-ui (native)  VPN panel + Xray; VLESS Reality listens directly on :8443
   |-- ufw + fail2ban  firewall, sshd + caddy jails
   |-- vpn-backup   nightly archive, stays on the VPS
```

Responsibilities are split: 3x-ui = VPN/clients/subscriptions, Caddy = HTTPS/proxy only (Reality traffic is **not** proxied), UFW = firewall, fail2ban = intrusion prevention, `vpn_backup` = backups, `vpn-restore.yml` = restores.

### Playbooks

```bash
ansible-playbook vpn.yml                                                       # full deployment
ansible-playbook vpn-restore.yml -e vpn_restore_archive=/path/to/archive.tar.gz # restore
```

### Configuration

All in `group_vars/vpn/`: `bootstrap.yml`, `ssh.yml`, `security.yml` mirror the `vps` group; `vpn.yml` holds the service config:

| Var                  | Purpose                                                                 |
| -------------------- | ----------------------------------------------------------------------- |
| `xui_state`          | `present` / `latest` (upgrade) / `absent` / `reinstalled`               |
| `xui_version`        | pin e.g. `v2.8.11`, empty = latest                                      |
| `xui_purge`          | `absent` also removes `/etc/x-ui` (the database!)                       |
| `xui_panel_port`     | panel port (54321) — proxied by Caddy via localhost, not exposed in UFW |
| `xui_sub_port`       | subscription port (2096) — same                                         |
| `caddy_panel_domain` | panel hostname                                                          |
| `caddy_sub_domain`   | subscription hostname                                                   |
| `vpn_backup_*`       | backup dir, retention, cron time                                        |

UFW exposes only SSH, 80, 443 and the tunnel ports (`xui_tunnel_ports`, currently Reality :8443 + xhttp :9443). Fail2ban runs the sshd jail plus a `caddy-4xx` jail over the Caddy access log. The built-in 3x-ui fail2ban integration stays disabled.

### The database is authoritative

3x-ui config (clients, UUIDs, Reality keys, subscriptions, stats) lives only in the SQLite database. Ansible never rewrites it: it is snapshotted into backups (`sqlite3 .backup`, safe on a live DB) and restored byte-for-byte. Panel/sub ports in `group_vars/vpn/vpn.yml` must match the DB settings (`webPort`/`subPort`) because Caddy proxies to them.

### Backups

Nightly cron runs `/opt/vpn-backup/backup.sh`, producing `vpn-backup-YYYYMMDD-HHMMSS.tar.gz` in `/opt/vpn-backup/archives/` with retention (`vpn_backup_retention_days`). Contents:

- `etc/x-ui/x-ui.db` — safe SQLite snapshot
- `etc/caddy/` — Caddyfile
- `var/lib/caddy/` — certificates (avoids Let's Encrypt re-issue after restore)

Backups stay on the VPS; another machine collects them.

### Restore (fresh VPS)

1. Provision VPS with your SSH key, then day-0: install Tailscale, `tailscale up --hostname=vpn-nl`, disable key expiry (see "First run").
2. `ansible-playbook vpn.yml`
3. `ansible-playbook vpn-restore.yml -e vpn_restore_archive=/path/to/vpn-backup-*.tar.gz`

Restore stops the services, extracts the archive into `/`, fixes ownership/permissions (`root` for the DB, `caddy` for Caddy data) and starts everything again.

### Migrating from the old Docker-based server

The old server kept its DB at `/opt/x-ui/db/x-ui.db` (Docker volume). Build a seed archive from it, then restore:

```bash
# on the old server (or anywhere with the DB file)
apt install -y sqlite3
mkdir -p /tmp/seed/etc/x-ui
sqlite3 /opt/x-ui/db/x-ui.db ".backup '/tmp/seed/etc/x-ui/x-ui.db'"
tar -czf vpn-backup-seed.tar.gz -C /tmp/seed etc
```

Then steps 1–3 from the restore section with `vpn_restore_archive=vpn-backup-seed.tar.gz`. Native 3x-ui reads the same schema — nothing is regenerated. After cutover, Docker/Traefik on the old host can be decommissioned (not managed by this repo).

---

## Monitoring VPS

A third, fully independent host (`mon` inventory group): the central external watcher, running **native Uptime Kuma + Caddy**. Its job is black-box monitoring of everything else (edge VPS, VPN VPS; later unraid and OpenWrt routers) — it answers "is the service reachable from the internet", while the per-host cron checks answer "is the host healthy inside".

### Division of responsibility

| Layer              | Where                | Covers                                                  |
| ------------------ | -------------------- | ------------------------------------------------------- |
| Uptime Kuma        | mon-1 (external)     | ports, HTTPS, certificates, ping — for all hosts        |
| cron + ntfy checks | each host (internal) | systemd units, disk, backup freshness, security updates |

Kuma pushes alerts to the same ntfy topics (configured once in the Kuma UI).

### Deploy

1. Provision VPS (Debian 13 / Ubuntu 24.04) with your SSH key, then day-0: install Tailscale, `tailscale up --hostname=mon-1`, disable key expiry (see "First run").
2. DNS: A record for your Kuma domain (`vault_kuma_domain` in `group_vars/mon/vault.yml`).
3. `ansible-playbook mon.yml`
4. Open `https://<kuma-domain>`, create the admin account, add monitors (edge :443/:25565, vpn panel/sub URLs, tunnel ports) and the ntfy notification channel (topics are in the vault).

### Notes

- Kuma is native (Node.js + systemd unit, pinned by `kuma_version`), listens on `127.0.0.1:3001` behind Caddy. UFW exposes only SSH/80/443.
- Kuma's monitors and settings live in its SQLite DB (`/opt/uptime-kuma/data`) — managed via the UI, not from Git. The `kuma_backup` role snapshots it nightly to `/opt/kuma-backup/archives` (same pattern as `vpn_backup`, cron at 04:00); the freshness check watches that dir.
- Restore: stop kuma, extract the archive into `/`, `chown kuma:kuma /opt/uptime-kuma/data/kuma.db`, start kuma. The Caddyfile and LE certificates are in the same archive.
- The host also watches itself via the cron checks (`caddy kuma fail2ban cron ssh`, backup freshness). No cron cross-checks between hosts — external watching of every host is Uptime Kuma's job alone (single watcher, minimal coupling).

---

## OpenWrt routers

Multiple OpenWrt routers (`routers` inventory group), identical config, managed end-to-end by `openwrt.yml` over the tailnet. Day-0 is manual: flash OpenWrt, set a root password, add your SSH key to dropbear (LuCI → System → Administration, or `ssh-copy-id` after `passwd`), then `apk add tailscale tailscaled && service tailscale enable && service tailscale start && tailscale up` — open the login URL and disable key expiry in the admin console. Everything after that is Ansible-only.

### Deploy

1. Do the day-0 steps above; the router appears as `router-<name>.<tailnet>.ts.net` — the inventory entry is already a MagicDNS name.
2. Drop your public key into `files/ssh/` (bird-named, e.g. `starling.pub`) and reference it from `ssh_authorized_keys` in `group_vars/routers/ssh.yml` — the role takes over `authorized_keys` authoritatively.
3. Check `owrt_lan_bridge_ports` in `group_vars/routers/network.yml` against the hardware (`ip link` on the router — DSA port names vary).
4. `ansible-playbook openwrt.yml`

### Exit nodes

Any router can double as a Tailscale exit node (full-tunnel internet access via its WAN — e.g. to keep a residential IP of your home country while abroad). Set `tailscale_advertise_exit_node: true` in the router's `host_vars/router-*.yml` and re-run `openwrt.yml`. The tailscale role passes `--advertise-exit-node`, the firewall role adds the `tailscale -> wan` forwarding (masquerade on the wan zone is already on; IP forwarding is set by openwrt_common sysctl). Two one-time steps remain in the Tailscale admin console: approve the exit route (Machines → node → Edit route settings, or `autoApprovers.exitNode` in the tailnet ACLs) and disable key expiry. Note there is no automatic failover between exit nodes — clients pick one explicitly (`tailscale set --exit-node=...` or the client GUI), so multiple nodes mean "somewhere to switch to", not seamless switching. Place them at different sites (different ISP/power) for real redundancy.

### Exit-node client gateway

The inverse role: an OpenWrt box (e.g. a VM on Unraid) that routes its whole LAN through a chosen exit node — every device behind it gets the home country IP without installing Tailscale anywhere. Same playbook, same group; the difference is two host_vars (see the ready-made `host_vars/router-gw.yml`):

- `tailscale_exit_node: router-krm` — the tailscale role runs `tailscale set --exit-node=...`; the firewall role adds masquerade on the tailscale zone and a `lan -> tailscale` forwarding (SNAT is required: the exit node drops packets with foreign LAN sources).
- `tailscale_exit_node_allow_lan_access: true` — the gateway itself keeps LAN reachability while the exit node is selected.

Switching to a backup exit node: change `tailscale_exit_node` and re-run `openwrt.yml`, or ad hoc on the device (`tailscale set --exit-node=router-alm`). VM notes: use the OpenWrt x86_64 image (generic combined, EFI or not to match the Unraid VM firmware), two virtio NICs — first is WAN (bridged to the local LAN), second is LAN towards the AP/switch; recent x86_64 images ship virtio drivers, verify with `ip link` after first boot.

### Upgrades

Daily checks are notify-only (role `openwrt_upgrades` -> ntfy). To apply:

- `ansible-playbook openwrt-upgrade.yml` — upgrade all apk packages
- `ansible-playbook openwrt-upgrade.yml -e owrt_firmware_upgrade=true` — plus firmware via `owut` (ASU image with your packages baked in). The router **reboots**; the play fires the upgrade async and returns immediately. Re-run `openwrt.yml` afterwards if configs drifted.

### Roles

| Role              | Configures                                                                                             |
| ----------------- | ------------------------------------------------------------------------------------------------------ |
| openwrt_common    | python3 bootstrap (via `raw`), hostname, timezone, NTP, sysctl                                         |
| openwrt_packages  | extra apk packages (`owrt_packages`)                                                                   |
| openwrt_ssh       | dropbear (key-only auth), root `authorized_keys`                                                       |
| openwrt_network   | `/etc/config/network` (LAN bridge, WAN) and `/etc/config/dhcp` (DHCP + DNS)                            |
| openwrt_firewall  | `/etc/config/firewall`, tailscale zone + subnet/exit forwarding, software flow offloading, extra rules |
| openwrt_tailscale | tailscale via apk, tailnet auth, exit node (same var names as the Debian role)                         |
| openwrt_upgrades  | daily notify-only update check (apk + owut firmware) -> ntfy                                           |

Notes:

- The play starts with `gather_facts: false` because a fresh router has no Python; `openwrt_common` installs full `python3` via `raw` (apk, OpenWrt 25.12+; `python3-light` is too stripped for ansible) and then gathers facts explicitly.
- Config is authoritative: the roles deploy whole `/etc/config/*` files, so manual `uci` edits on the router get overwritten.
- Per-host differences (LAN IP, hostname override) live in `host_vars/router-*.yml`; hostname and tailscale name default to the inventory name.
- Changing `owrt_lan_ip` reloads the network and drops a LAN-based SSH session mid-run — manage over the tailnet when changing addressing.
- Monitoring: mon-1 is on the tailnet (network layer, `tailscale_accept_routes: true`), so Uptime Kuma pulls the routers — no inbound access or push hacks needed. Suggested monitors (create in the Kuma UI): Ping `100.102.172.25`; DNS with resolver `192.168.101.1` querying a public A record (exercises dnsmasq end-to-end); TCP `192.168.101.1:22` (dropbear). LAN-side targets ride the advertised subnet route — approve it in the Tailscale admin console. Ping works on the tailscale IP too (firewall zone input), but dropbear/dnsmasq bind to the LAN interface only, so use the LAN IP for those. DNS over the tailnet additionally needs `owrt_dns_localservice: false` (set in `group_vars/routers/network.yml`): dnsmasq otherwise drops queries from 100.64.0.0/10 at application level.

---

## Backups → Unraid

Central collector: Unraid **pulls** every host's backups over tailnet (script: `files/unraid/homelab-backup-pull.sh.j2`, deployed into the User Scripts plugin by `unraid.yml`; schedule is set in the plugin GUI). Pull model on purpose — hosts hold no Unraid credentials, so a compromised host cannot delete or encrypt its own backups.

Every pull source is tracked in a state file next to the script (persists on the flash drive): ntfy fires only on transitions — OK→FAIL to the alerts topic, FAIL→OK (recovery) to info. Repeated failures stay silent. Host-side freshness (`check-backup.sh`, >25 h) covers the VPS archive producers; this covers the collector itself — router tarballs and the rsync mirrors.

What gets pulled:

- VPS artifacts: `rsync` of the `/opt/*-backup/archives/` dirs produced by the `vpn_backup` / `kuma_backup` roles (SQLite snapshots with their own 14-day rotation).
- OpenWrt routers: `sysupgrade -b` streamed over SSH into dated tarballs (`sysupgrade-<date>.tar.gz`, 30-day retention on the Unraid side). Nothing is installed on the routers for this.

Setup:

1. On Unraid: `ssh-keygen -t ed25519 -C "great-hornbill"` (default path, empty passphrase for cron), then drop the public key into `files/ssh/great-hornbill.pub` — it is referenced by `ssh_authorized_keys` (`group_vars/routers/ssh.yml`) and `bootstrap_root_ssh_keys` (VPS groups) — same flow as `starling.pub`.
2. One-time chicken-egg: authorize `starling.pub` ON Unraid so `unraid.yml` can reach it — append it to `/boot/config/ssh/root/authorized_keys` (persists across reboots; `/root` is a ramdisk) via the web terminal.
3. Fill in `RSYNC_SOURCES` / `ROUTERS` in the script (tailscale IPs) and adjust `DEST` to your share.
4. `ansible-playbook unraid.yml` — deploys the script into `/boot/config/plugins/user.scripts/scripts/homelab-backup-pull/` (raw + base64, Unraid has no python).
5. In Settings → User Scripts set the schedule (Schedule → Custom → `0 5 * * *`), run once manually and check the log.
6. Re-run `openwrt.yml` / `mon.yml` so the great-hornbill key is authorized on the backup sources.

Restore: VPS DBs — copy the tarball back and follow the role's restore path (`vpn-restore.yml` for 3x-ui); routers — upload the tarball in LuCI _Backup/Flash Firmware_ or `sysupgrade -r`.

---

## Non-goals

- Prometheus / Grafana / Loki / ELK / SIEM.
- Kubernetes, Docker Swarm, Nomad.
- TLS termination on the VPS.
- Hosting applications on the VPS.

Stay boring. Replace the VPS in 5 minutes. Sleep at night.
