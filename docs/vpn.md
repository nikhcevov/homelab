# VPN VPS

[Repository overview](../README.md)

Sources: [playbooks/vpn.yml](../playbooks/vpn.yml), [VPN configuration](../inventory/group_vars/vpn/vpn.yml), [VPN host configuration](../inventory/host_vars/vpn-nl.yml).

Run commands from the repository root.

Independent VPN gateway (`vpn` group): **native 3x-ui + Caddy**, ufw + fail2ban, nightly backups. No Docker and no dependency on the home lab — it works when the homelab is offline. The host joins the tailnet at day-0 (manual) so Ansible can reach it and the PVE collector can pull its backups. `playbooks/vpn.yml` targets only the `vpn` group and reconciles Tailscale after security, before deploying 3x-ui; settings come from [VPN Tailscale variables](../inventory/group_vars/vpn/tailscale.yml). An edge deployment does not configure this host.

Responsibilities: 3x-ui = VPN/clients/subscriptions, Caddy = HTTPS/reverse proxy only (Reality traffic is **not** proxied), `vpn_backup` = backups, `playbooks/vpn.yml --tags restore` = explicit restores. Normal deployment and `--tags all` never restore data.

## RU entry through the edge VPS

The panel/subscription domains and the two Reality ports are reachable through
the `edge` VPS in Moscow. DNS for `panel.` and `sub.` points to `edge`; edge
forwards TLS 443 by SNI to `vpn-nl:443` over Tailscale and raw TCP 8443/9443 to
the same host. TLS termination, the panel database, and Reality keys stay on
`vpn-nl`; edge only forwards L4 traffic. The Tailscale policy grants
`tag:edge` -> `vpn-nl` on TCP 443, 8443, and 9443. Both inbounds are VLESS
Reality/TCP with Vision and `encryption=none` in the share links; do not use
xhttp with Vision. Edge routes are private in `vars/proxy.yml`; apply with
`ansible-playbook playbooks/edge.yml --tags security,proxy`.

Because DNS points at edge, Caddy uses **TLS-ALPN-01** for certificate
renewal (`caddy_acme_disable_http_challenge: true`); HTTP-01 on port 80 cannot
traverse the edge. Keep that setting while `panel.`/`sub.` resolve to edge, and
verify the certificate expiry check after the next renewal window.

```bash
ansible-playbook playbooks/vpn.yml                                                         # setup/update
ansible-playbook playbooks/vpn.yml --tags restore -e vpn_restore_archive=/path/to/archive.tar.gz # restore only
```

Config in `inventory/group_vars/vpn/vpn.yml`, per-host domains/paths in `inventory/host_vars/vpn-<cc>.yml` (a second VPN server = copy that file + one inventory line):

| Var                                       | Purpose                                                           |
| ----------------------------------------- | ----------------------------------------------------------------- |
| `xui_state`                               | `present` / `latest` (upgrade) / `absent` / `reinstalled`         |
| `xui_version`                             | pin e.g. `v2.8.11`, empty = latest                                |
| `xui_purge`                               | `absent` also removes `/etc/x-ui` (the database!)                 |
| `xui_panel_port` / `xui_sub_port`         | proxied by Caddy via localhost, not exposed in UFW                |
| `caddy_panel_domain` / `caddy_sub_domain` | from the vault                                                    |
| `xui_tunnel_ports`                        | tunnel inbounds exposed in UFW (Reality 1/2) — listen directly    |
| `vpn_backup_*`                            | backup dir, retention, cron time                                  |

**The database is authoritative.** 3x-ui config (clients, UUIDs, Reality keys, subscriptions) lives only in its SQLite DB. Ansible never rewrites it — it is snapshotted (`sqlite3 .backup`, safe on a live DB) into backups and restored byte-for-byte. Panel/sub ports in `inventory/group_vars/vpn/vpn.yml` must match the DB settings (`webPort`/`subPort`) because Caddy proxies to them.

**Backups:** nightly cron → `/opt/vpn-backup/archives/vpn-backup-*.tar.gz` with retention. Contents: `x-ui.db` snapshot, Caddyfile, `var/lib/caddy/` certificates (avoids Let's Encrypt re-issue after restore). Backups stay on the VPS; the PVE collector copies them into native PBS file backups (see [backup collection and recovery](backups-proxmox.md)).

**Restore (fresh VPS):** [day-0](getting-started.md#first-run-new-vps) → `ansible-playbook playbooks/vpn.yml` → `ansible-playbook playbooks/vpn.yml --tags restore -e vpn_restore_archive=/path/to/archive.tar.gz`. Setup must complete first; the restore tag does not install or configure the server. Restore uploads the archive, stops services, extracts into `/`, fixes ownership (`root` for the DB, `caddy` for Caddy data), starts everything, and removes the uploaded archive.
