# homelab

Self-hosted homelab infrastructure, managed entirely by Ansible. This repository is the single source of truth — all changes go through Git + Ansible, never manual edits on servers.

Managed hosts (inventory groups):

| Group          | Hosts                               | Playbook(s)                          | What runs there                                           |
| -------------- | ----------------------------------- | ------------------------------------ | --------------------------------------------------------- |
| `vps`          | edge-proxy                          | `site.yml` (layered)                 | L4 SNI proxy (nginx stream) → home servers over Tailscale |
| `vpn`          | vpn-nl                              | `vpn.yml`, `vpn-restore.yml`         | native 3x-ui + Caddy, nightly backups                     |
| `mon`          | mon-1                               | `mon.yml`                            | native Uptime Kuma + Caddy, external watcher              |
| `routers`      | router-alm, router-krm, router-trvl | `openwrt.yml`, `openwrt-upgrade.yml` | OpenWrt routers, Tailscale exit nodes                     |
| `unraid`       | great-hornbill                      | `unraid.yml`                         | central backup collector (pull model)                     |
| `workstations` | starling                            | `workstation.yml`                    | Arch/CachyOS dev desktops                                 |

The tailnet is the only management plane: every host is addressed by its MagicDNS name, day-0 (install OS, add one SSH key, `tailscale up`, disable key expiry) is the only manual step. Host IPs are deliberately not stored in the repo.

## Principles

1. **Zero-trust edge.** The edge VPS stores no private data and forwards encrypted traffic only (L4 pass-through via `ssl_preread`, no TLS termination).
2. **Declarative.** Desired state lives in YAML; configs are generated artifacts.
3. **Idempotent.** Re-running any playbook on a converged host reports zero changes.
4. **Restorable.** If a configuration cannot be rebuilt from this repo, it is an architecture bug.
5. **Minimal resources.** VPS layers run on 1 vCPU / 500 MB RAM. No Docker, no Prometheus.
6. **Signal over noise.** Alerts only on state transitions, severity-based ntfy channels.

## Repository layout

```
├── site.yml                     edge VPS: full deployment (imports the 5 layers below)
├── bootstrap.yml                layer 1: base system + ssh        ┐
├── security.yml                 layer 2: ufw + fail2ban           │
├── network.yml                  layer 3: tailscale                ├ each also standalone
├── proxy.yml                    layer 4: nginx stream proxy       │
├── services.yml                 layer 5: monitoring               ┘
├── vpn.yml / vpn-restore.yml    VPN VPS deploy / restore
├── mon.yml                      monitoring VPS deploy
├── openwrt.yml / openwrt-upgrade.yml   routers deploy / package+firmware upgrade
├── unraid.yml                   deploy backup-pull script to Unraid
├── workstation.yml              Arch/CachyOS desktops
├── test-render.yml              local nginx render test (no VPS needed)
├── inventory/hosts.ini          all hosts, MagicDNS names only
├── group_vars/<group>/          one file per concern (bootstrap, ssh, security, ...)
├── host_vars/<host>.yml         per-host deltas and per-host vault secrets
├── vars/proxy.yml               edge routing map (gitignored; see proxy.example.yml)
├── roles/                       common, ssh, ufw, fail2ban, tailscale, nginx, monitoring,
│                                xui, caddy, vpn_backup, kuma, kuma_backup, openwrt_*,
│                                arch_common, arch_packages, docker, dotfiles, syncthing
├── scripts/  cron/              monitoring checks (bash) + cron definition
└── files/                       ssh public keys, Unraid backup-pull script
```

## Requirements

- Control machine: `ansible-core`, then `ansible-galaxy collection install -r requirements.yml`.
- Edge VPS: Debian 12, x86_64; VPN/mon VPS: Debian 13 / Ubuntu 24.04+. Python 3 is the only target requirement.
- A Tailscale tailnet with MagicDNS; `tailnet_domain` set once in `group_vars/all/tailscale.yml`.
- A reachable ntfy.sh topic for notifications.

## First run (new VPS)

**Day-0 (manual, once, on the host):**

1. Provision the VPS with your SSH public key.
2. Join the tailnet: `curl -fsSL https://tailscale.com/install.sh | sh && tailscale up --hostname=<name>`, open the login URL, then **disable key expiry** in the admin console — otherwise the node silently drops off the tailnet after 180 days.
3. Convention: inventory name = tailscale hostname, so `ansible_host` needs no change.

**On the control machine:**

```bash
ansible-galaxy collection install -r requirements.yml   # one-time
ansible-vault encrypt_string 'the-secret' --name vault_ntfy_topic_info  # add secrets to group_vars/*/vault.yml
cp vars/proxy.example.yml vars/proxy.yml && $EDITOR vars/proxy.yml      # edge routing map
ansible-playbook site.yml        # or vpn.yml / mon.yml for those hosts
```

Extra SSH keys: drop the `.pub` into `files/ssh/` and list it in `bootstrap_root_ssh_keys` (`group_vars/<group>/bootstrap.yml`). Public keys belong in Git.

## Edge VPS: layers

`site.yml` imports five layers in order; each is also a standalone playbook. Layers depend left to right (proxy needs tailnet DNS; monitoring expects nginx). Bootstrap is safe to re-run anytime.

```bash
ansible-playbook site.yml        # everything, in order
ansible-playbook proxy.yml       # just re-render and reload the proxy
ansible-playbook security.yml    # just firewall + fail2ban
```

### `vars/proxy.yml` — the only file you edit for routing

Adding a service = adding a block here + `ansible-playbook site.yml`. The nginx config and (via `ufw_open_service_ports: true`) the firewall rule are regenerated automatically.

Schema (full annotated examples in `vars/proxy.example.yml`):

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
- SNI requires `protocol: tcp`; at most one `default: true` per listener (else first service wins).
- Always use MagicDNS names (`host.tailnet.ts.net`), never raw `100.x` IPs.

### `group_vars/vps/` — one file per concern

| File             | Configures    | Highlights                                                                   |
| ---------------- | ------------- | ---------------------------------------------------------------------------- |
| `bootstrap.yml`  | common        | packages, timezone, locale, unattended-upgrades, extra root keys, admin user |
| `ssh.yml`        | ssh           | `sshd_port` + auth modes — defined once, consumed by sshd, ufw and fail2ban  |
| `security.yml`   | ufw, fail2ban | default policies, static rules, `ufw_open_service_ports`, ban policy         |
| `tailscale.yml`  | tailscale     | hostname, optional auth key (from vault)                                     |
| `monitoring.yml` | monitoring    | checked units, disk threshold/mounts, backup freshness, host prefix          |

Firewall rules come from three merged sources: the SSH port, the static `ufw_rules` list, and the listen ports of every service in `vars/proxy.yml`.

Switching from root to an admin user: set `bootstrap_admin_user`(+`_ssh_keys`), run `bootstrap.yml`, switch `ansible_user` in inventory, set `sshd_permit_root_login: "no"`, re-run `site.yml`.

## Secrets

In Git: templates, roles, inventory, playbooks, service/domain lists. **Never** plaintext: private keys, tokens, auth keys, passwords, real domains.

Secrets live as inline `!vault` blocks (`ansible-vault encrypt_string`) — shared ones in `group_vars/all/vault.yml`, per-group in `group_vars/<group>/vault.yml`, per-host in `host_vars/<host>.yml`. Keys and comments stay readable in diffs; Ansible decrypts natively. The real routing map `vars/proxy.yml` is plaintext-gitignored (config, not credentials).

The vault password lives in `.vault_pass` (gitignored, referenced by `ansible.cfg`) — keep it in your password manager; losing it means losing all secrets. Sanity check before pushing: `git grep -L '!vault' group_vars/ host_vars/` on files that should be encrypted.

| Vault var                            | Where                      | Why                                                     |
| ------------------------------------ | -------------------------- | ------------------------------------------------------- |
| `vault_ntfy_topic_*`                 | `group_vars/all/vault.yml` | ntfy topic name = password                              |
| `vault_tailscale_auth_key`           | `group_vars/all/vault.yml` | optional unattended tailnet join (empty = manual day-0) |
| `vault_kuma_domain`                  | `group_vars/mon/vault.yml` | real Kuma domain                                        |
| `vault_*_domain`, `vault_xui_*_path` | `host_vars/vpn-<cc>.yml`   | VPN domains + secret 3x-ui URL paths                    |

## Local render test (no VPS needed)

```bash
ansible-playbook test-render.yml && cat /tmp/rendered-stream.conf
```

## Monitoring

Two complementary layers:

| Layer              | Where               | Covers                                                    |
| ------------------ | ------------------- | --------------------------------------------------------- |
| Uptime Kuma        | mon-1 (external)    | ports, HTTPS, certificates, ping — black-box, all hosts   |
| cron + ntfy checks | each VPS (internal) | systemd units, containers, disk, updates, reboot, backups |

Internal checks (same `monitoring` role on `vps`, `vpn`, `mon`; per-group config in `group_vars/<group>/monitoring.yml`) push to ntfy **only on state transitions**:

| Check             | Interval | Alerts on                         | Severity |
| ----------------- | -------- | --------------------------------- | -------- |
| systemd services  | 15 min   | unit not active                   | critical |
| docker containers | 15 min   | container not running             | critical |
| disk usage        | 1 h      | usage > threshold                 | alert    |
| security updates  | daily    | apt security updates available    | alert    |
| reboot required   | daily    | `/var/run/reboot-required` exists | alert    |
| backup freshness  | daily    | no archive / newest > 25 h old    | alert    |

Empty lists disable a check. Notification channels are severity-first: `*-critical`, `*-alerts`, `*-info`. Kuma pushes to the same topics (configured once in the Kuma UI).

## Operations

```bash
# health on the edge VPS
sudo systemctl status nginx tailscaled fail2ban ssh
sudo nginx -t && sudo ss -tlnp | grep nginx
sudo ufw status verbose && sudo fail2ban-client status sshd
tailscale status
sudo bash /opt/homelab-monitoring/scripts/check-services.sh   # trigger a monitor manually
```

**Migrate the edge VPS:** provision + day-0 with the same hostname (same MagicDNS name, no inventory change) → `ansible-playbook site.yml` → switch DNS A/AAAA records. Home servers are untouched.

## Security notes

- No TLS termination on the edge VPS; certificates live only on home servers. Outbound to home only over Tailscale.
- Port 80 returns 444; `server_tokens off`; stream access log disabled.
- SSH key-only (`sshd_password_authentication: "no"`, root `prohibit-password`); sshd config validated with `sshd -t` before every apply; fail2ban watches the sshd journal.
- Default firewall policy: deny incoming, allow outgoing.

## Troubleshooting

| Symptom                                | Look at                                                                         |
| -------------------------------------- | ------------------------------------------------------------------------------- |
| Playbook fails in validation tasks     | `vars/proxy.yml` — the assert message names the offending service.              |
| `nginx -t` task fails                  | Rendered `/etc/nginx/stream.d/proxy.conf` on the VPS.                           |
| Locked out after security layer        | Rules are added before ufw is enabled; check `sshd_port` vs `ansible_port`.     |
| Tailscale auth task skips              | Node already connected, or empty auth key (day-0 manual join).                  |
| Node fell off the tailnet              | Key expiry — re-run `tailscale up`, then disable expiry in the admin console.   |
| Connection refused on a forwarded port | `ss -tlnp \| grep <port>`, `journalctl -u nginx`, `ufw status`.                 |
| Wrong backend for a domain             | SNI hostname missing/duplicated in `vars/proxy.yml`; check the generated `map`. |
| Backend unreachable                    | `nc -vz <host>.ts.net <port>` from the VPS; check Tailscale.                    |
| No ntfy messages arrive                | Topics in `group_vars/*/monitoring.yml` + vault; run a check script manually.   |

---

## VPN VPS

Independent VPN gateway (`vpn` group): **native 3x-ui + Caddy**, ufw + fail2ban, nightly backups. No Docker and no dependency on the home lab — it works when the homelab is offline. The host joins the tailnet at day-0 (manual) so Ansible can reach it and Unraid can pull its backups; the playbook itself manages no tailscale settings.

Responsibilities: 3x-ui = VPN/clients/subscriptions, Caddy = HTTPS/reverse proxy only (Reality traffic is **not** proxied), `vpn_backup` = backups, `vpn-restore.yml` = restores.

```bash
ansible-playbook vpn.yml                                                        # full deployment
ansible-playbook vpn-restore.yml -e vpn_restore_archive=/path/to/archive.tar.gz # restore
```

Config in `group_vars/vpn/vpn.yml`, per-host domains/paths in `host_vars/vpn-<cc>.yml` (a second VPN server = copy that file + one inventory line):

| Var                                       | Purpose                                                           |
| ----------------------------------------- | ----------------------------------------------------------------- |
| `xui_state`                               | `present` / `latest` (upgrade) / `absent` / `reinstalled`         |
| `xui_version`                             | pin e.g. `v2.8.11`, empty = latest                                |
| `xui_purge`                               | `absent` also removes `/etc/x-ui` (the database!)                 |
| `xui_panel_port` / `xui_sub_port`         | proxied by Caddy via localhost, not exposed in UFW                |
| `caddy_panel_domain` / `caddy_sub_domain` | from the vault                                                    |
| `xui_tunnel_ports`                        | tunnel inbounds exposed in UFW (Reality, xhttp) — listen directly |
| `vpn_backup_*`                            | backup dir, retention, cron time                                  |

**The database is authoritative.** 3x-ui config (clients, UUIDs, Reality keys, subscriptions) lives only in its SQLite DB. Ansible never rewrites it — it is snapshotted (`sqlite3 .backup`, safe on a live DB) into backups and restored byte-for-byte. Panel/sub ports in `group_vars/vpn/vpn.yml` must match the DB settings (`webPort`/`subPort`) because Caddy proxies to them.

**Backups:** nightly cron → `/opt/vpn-backup/archives/vpn-backup-*.tar.gz` with retention. Contents: `x-ui.db` snapshot, Caddyfile, `var/lib/caddy/` certificates (avoids Let's Encrypt re-issue after restore). Backups stay on the VPS; Unraid collects them (see below).

**Restore (fresh VPS):** day-0 → `ansible-playbook vpn.yml` → `ansible-playbook vpn-restore.yml -e vpn_restore_archive=...`. Restore stops services, extracts into `/`, fixes ownership (`root` for the DB, `caddy` for Caddy data), starts everything.

---

## Monitoring VPS

Central external watcher (`mon` group): **native Uptime Kuma + Caddy** (Kuma pinned by `kuma_version`, Node.js + systemd, `127.0.0.1:3001` behind Caddy; UFW exposes only SSH/80/443). Answers "is the service reachable from the internet" while the per-host cron checks answer "is the host healthy inside".

Deploy: day-0 → DNS A record for the Kuma domain (`vault_kuma_domain`) → `ansible-playbook mon.yml` → open the UI, create the admin account, add monitors and the ntfy channel.

- Monitors and settings live in Kuma's SQLite DB (`/opt/uptime-kuma/data`) — managed via the UI, not Git. `kuma_backup` snapshots it nightly to `/opt/kuma-backup/archives` (same pattern as `vpn_backup`).
- Restore: stop kuma, extract archive into `/`, `chown kuma:kuma .../kuma.db`, start kuma. Caddyfile and certificates are in the same archive.
- The host watches itself via the same cron checks; there are no cron cross-checks between hosts — external watching is Kuma's job alone.
- mon-1 accepts subnet routes (`tailscale_accept_routes: true`), so Kuma can poll router LAN services (see below).

---

## OpenWrt routers

Identical OpenWrt routers (`routers` group), managed end-to-end by `openwrt.yml` over the tailnet. Config is authoritative — roles deploy whole `/etc/config/*` files, manual `uci` edits get overwritten. Per-host deltas (LAN IP, exit-node flags) live in `host_vars/router-*.yml`.

Day-0 (manual): flash OpenWrt, set root password, add your SSH key to dropbear, then `apk add tailscale tailscaled && service tailscale enable && service tailscale start && tailscale up` → disable key expiry. Then:

1. Drop your public key into `files/ssh/` and reference it in `ssh_authorized_keys` (`group_vars/routers/ssh.yml`) — the role takes over `authorized_keys` authoritatively.
2. Check `owrt_lan_bridge_ports` (`group_vars/routers/network.yml`) against the hardware (`ip link` — DSA port names vary).
3. `ansible-playbook openwrt.yml`

A fresh router has no Python: the play starts with `gather_facts: false` and `openwrt_common` installs full `python3` via `raw` (apk), then gathers facts.

**Exit nodes:** set `tailscale_advertise_exit_node: true` in the router's `host_vars` and re-run `openwrt.yml` (role passes `--advertise-exit-node`, firewall gets `tailscale → wan` forwarding). Two one-time admin-console steps remain: approve the exit route and disable key expiry. No automatic failover — clients pick a node explicitly; place nodes at different sites for real redundancy.

**Exit-node client gateway** (inverse: a whole LAN behind an OpenWrt box exits via a chosen node): set `tailscale_exit_node: <node>` (+ `tailscale_exit_node_allow_lan_access: true`). The firewall role renders `lan → tailscale` masquerade automatically. Switch nodes by changing the var and re-running, or ad hoc: `tailscale set --exit-node=...`.

**Per-device exit node + kill switch** (router-trvl): `owrt_network_rules` slot netifd `ip rule`s in front of tailscaled's blanket `5270: from all lookup 52` — only the MacBook's /32 looks up table 52, backed by an `unreachable` rule so a dead tunnel means no internet (never a WAN fallback); the rest of the LAN preempts 5270 with a direct `main` lookup. Belt and suspenders: a firewall REJECT for the MacBook's IP into the wan zone. Requires a fixed DHCP lease (and Private Wi-Fi Address = Fixed on macOS).

**Upgrades:** daily checks are notify-only (`openwrt_upgrades` → ntfy). To apply: `ansible-playbook openwrt-upgrade.yml` (apk packages); add `-e owrt_firmware_upgrade=true` for firmware via `owut` — the router **reboots**, the play fires async and returns immediately. Re-run `openwrt.yml` afterwards if configs drifted.

**Wi-Fi:** opt-in per host via `owrt_wireless_radios` (`group_vars/routers/wireless.yml` documents the format; radio `path` values are device-specific — copy them from the stock `/etc/config/wireless`). The PSK lives in the vault (`vault_wireless_psk`). The deploy is authoritative: uplink sta interfaces added on the road (travelmate, hotel Wi-Fi) get wiped on the next run — keep those ad hoc.

| Role              | Configures                                                                                    |
| ----------------- | --------------------------------------------------------------------------------------------- |
| openwrt_common    | python3 bootstrap (via `raw`), hostname, timezone, NTP, sysctl                                |
| openwrt_packages  | extra apk packages (`owrt_packages`)                                                          |
| openwrt_ssh       | dropbear (key-only), root `authorized_keys`                                                   |
| openwrt_network   | `/etc/config/network` + `/etc/config/dhcp` (LAN bridge, WAN, DHCP, DNS)                       |
| openwrt_wireless  | `/etc/config/wireless` (radios + AP SSIDs, PSK from vault); opt-in per host                   |
| openwrt_firewall  | `/etc/config/firewall`, tailscale zone + subnet/exit forwarding, flow offloading, extra rules |
| openwrt_tailscale | tailscale via apk, tailnet auth, exit node (same var names as the Debian role)                |
| openwrt_upgrades  | daily notify-only update check (apk + owut) → ntfy                                            |

Notes: changing `owrt_lan_ip` drops a LAN-based SSH session mid-run — manage over the tailnet. For Kuma DNS monitors over the tailnet set `owrt_dns_localservice: false` (dnsmasq otherwise drops 100.64.0.0/10 queries); dropbear/dnsmasq bind to LAN only, so monitor LAN IPs (ride the advertised subnet route — approve it in the admin console).

---

## Backups → Unraid

Unraid **pulls** every host's backups over the tailnet (script `files/unraid/homelab-backup-pull.sh.j2`, deployed into the User Scripts plugin by `unraid.yml`; schedule set in the plugin GUI). Pull model on purpose — hosts hold no Unraid credentials, so a compromised host cannot delete or encrypt its own backups.

What gets pulled: `rsync` of `/opt/*-backup/archives/` from the VPS hosts (vpn/kuma, own 14-day rotation), and `sysupgrade -b` streamed over SSH from each router into dated tarballs (30-day retention). Every source is tracked in a state file: ntfy fires only on transitions (OK→FAIL alerts, FAIL→OK info).

Setup:

1. On Unraid: `ssh-keygen -t ed25519 -C "great-hornbill"` (default path, empty passphrase), put the pubkey in `files/ssh/great-hornbill.pub` — referenced by routers' `ssh_authorized_keys` and VPS `bootstrap_root_ssh_keys`.
2. One-time chicken-egg: authorize `starling.pub` on Unraid via `/boot/config/ssh/root/authorized_keys` (persists; `/root` is a ramdisk).
3. Fill in `RSYNC_SOURCES` / `ROUTERS` / `DEST` in the script template.
4. `ansible-playbook unraid.yml` (raw + base64 — Unraid has no Python), then set the schedule in Settings → User Scripts and run once manually.
5. Re-run `openwrt.yml` / `mon.yml` / `vpn.yml` so the great-hornbill key is authorized on the sources.

Restore: VPS DBs — copy the tarball back and follow the role's restore path (`vpn-restore.yml`); routers — upload in LuCI _Backup/Flash Firmware_ or `sysupgrade -r`.

---

## Workstations (Arch/CachyOS)

Desktops (`workstations` group) managed by `workstation.yml` — same model: declarative lists in `group_vars/workstations/`, deltas in `host_vars/`, management over the tailnet. Goal: **identical dev environment**, not identical systems. GUI/desktop/hardware packages are deliberately NOT managed.

| Layer                              | Tool                                        |
| ---------------------------------- | ------------------------------------------- |
| Dev packages                       | Ansible (`arch_packages`, base + dev lists) |
| User config (fish, nvim, git, ...) | chezmoi + git (`dotfiles` role)             |
| Source code (`~/Projects`)         | git + GitHub                                |
| `~/Documents`                      | Syncthing (user service, only this folder)  |
| Large/shared files                 | Unraid directly                             |

Roles: `arch_common` (optional `-Syu` via `-e arch_system_upgrade=true`, timezone/locale, NetworkManager → systemd-resolved fix for MagicDNS), `ssh`, `tailscale` (day-0 `tailscale up` is manual), `arch_packages` (yay/AUR mechanism ready but empty by design), `docker` (re-login once for the group), `dotfiles` (chezmoi init + update every run; set `dotfiles_chezmoi_repo`), `syncthing` (one-time GUI pairing at `http://127.0.0.1:8384`).

**Bootstrap a fresh machine:** install OS + user → `sudo pacman -S git ansible openssh tailscale` → `tailscale up` (disable key expiry) → add to `[workstations]` + optional `host_vars/<name>.yml` → `ansible-playbook workstation.yml --limit <name> --ask-become-pass`. Day-0 on the machine hosting this repo: `ansible-playbook workstation.yml -c local --limit starling --ask-become-pass`. Partial runs: `--tags packages|docker|dotfiles|syncthing|tailscale`.

---

## Non-goals

- Prometheus / Grafana / Loki / ELK / SIEM.
- Kubernetes, Docker Swarm, Nomad.
- TLS termination on the edge VPS.
- Hosting applications on the VPS.

Stay boring. Replace any VPS in 5 minutes. Sleep at night.
