# Edge VPS

[Repository overview](../README.md) · [Getting started](getting-started.md) · [Tailscale policy](tailscale.md) · [Monitoring](monitoring.md)

Sources: [playbooks/edge.yml](../playbooks/edge.yml), [routing example](../vars/proxy.example.yml), [edge variables](../inventory/group_vars/edge/), and [nginx role](../roles/nginx/).

Run commands from the repository root.

## Deployment layers

`playbooks/edge.yml` imports five layers in order; each is also a standalone playbook. Every layer, including `playbooks/edge-network.yml`, targets only the `edge` group. VPN and monitoring hosts reconcile their own Tailscale configuration through `playbooks/vpn.yml` and `playbooks/mon.yml`. Layers depend left to right (proxy needs tailnet DNS; monitoring expects nginx). Bootstrap is safe to re-run anytime.

```bash
ansible-playbook playbooks/edge.yml             # everything, in order
ansible-playbook playbooks/edge-bootstrap.yml   # base system + SSH
ansible-playbook playbooks/edge-security.yml    # firewall + fail2ban
ansible-playbook playbooks/edge-network.yml     # Tailscale
ansible-playbook playbooks/edge-proxy.yml       # re-render and reload the proxy
ansible-playbook playbooks/edge-services.yml    # monitoring
```

The inventory group is `edge`; scoped runs use `--limit edge`. This repository
namespace does not change the host `edge-proxy`, its Tailscale hostname, or the
external `tag:vps` policy identity. VPN and monitoring groups are unchanged.

### `vars/proxy.yml` — the only file you edit for routing

Adding a service = adding a block here + `ansible-playbook playbooks/edge.yml`. The nginx config and (via `ufw_open_service_ports: true`) the firewall rule are regenerated automatically.

Schema (full annotated examples in [`vars/proxy.example.yml`](../vars/proxy.example.yml)):

| Field      | Required | Purpose                                                                          |
| ---------- | -------- | -------------------------------------------------------------------------------- |
| `listen`   | yes      | Port nginx listens on.                                                           |
| `protocol` | no       | `tcp` (default) or `udp`.                                                        |
| `sni`      | no       | TLS SNI hostnames routed here (tcp only, via `ssl_preread`).                     |
| `default`  | no       | `true` = fallback backend for unknown SNI on this listener.                      |
| `upstream` | yes      | One backend or a list: `host`, `port`, optional `backup`, `weight`, `max_fails`. |

Rules (enforced by [`roles/nginx/tasks/validate.yml`](../roles/nginx/tasks/validate.yml) before anything is deployed):

- SNI hostnames must be unique across all services.
- Services sharing a listen port must **all** use SNI — or be a single plain forward.
- SNI requires `protocol: tcp`; at most one `default: true` per listener. Without an explicit default, the first service wins; multiple explicit defaults fail validation.
- Always use MagicDNS names (`host.tailnet.ts.net`), never raw `100.x` IPs.

### `inventory/group_vars/edge/` — one file per concern

| File             | Configures    | Highlights                                                                   |
| ---------------- | ------------- | ---------------------------------------------------------------------------- |
| `bootstrap.yml`  | common        | packages, timezone, locale, unattended-upgrades, extra root keys, admin user |
| `ssh.yml`        | ssh           | `sshd_port` + auth modes — defined once, consumed by sshd, ufw and fail2ban  |
| `security.yml`   | ufw, fail2ban | default policies, static rules, `ufw_open_service_ports`, ban policy         |
| `tailscale.yml`  | tailscale     | hostname, optional auth key (from vault)                                     |
| `monitoring.yml` | monitoring    | checked units, disk threshold/mounts, backup freshness, host prefix          |

Firewall rules come from three merged sources: the SSH port, the static `ufw_rules` list, and the listen ports of every service in `vars/proxy.yml`. The [`playbooks/edge-security.yml` play](../playbooks/edge-security.yml) loads that routing file only when `ufw_open_service_ports` is enabled and passes the same `services` map used by nginx to UFW as `ufw_proxy_services`. The [UFW role](../roles/ufw/tasks/main.yml) consumes this explicit mapping; it does not locate or read routing files. Enabled automatic ports require that input (a missing or non-mapping value fails instead of silently omitting proxy listeners). VPN and monitoring disable automatic proxy ports and need neither the routing file nor this input.

Proxy listeners are deduplicated by port **and** protocol; omitted protocols default to TCP. Listeners already covered by SSH or static rules are excluded, and a shared SNI listener keeps the first service's `proxy: <service>` comment. Existing rules are not purged.

Switching from root to an admin user: set `bootstrap_admin_user`(+`_ssh_keys`), run `playbooks/edge-bootstrap.yml`, switch `ansible_user` in inventory, set `sshd_permit_root_login: "no"`, re-run `playbooks/edge.yml`.

## Local render test (no VPS needed)

```bash
ansible-playbook playbooks/test-render.yml && cat /tmp/rendered-stream.conf
```

The command above uses the private `vars/proxy.yml` and the normal vault configuration. For a credential-free check using the public example, run the [offline Ansible gate](../CONTRIBUTING.md#local-ansible-checks). To select another routing file, pass `-e proxy_vars_file=/path/to/routing.yml`; `-e proxy_render_dir=/existing/output/directory` redirects both rendered files (default `/tmp`).

Routing-file overrides should be absolute, for example:

```bash
ansible-playbook playbooks/test-render.yml -e "proxy_vars_file=$PWD/vars/proxy.example.yml"
```

This override selects the public map but still uses the configured vault password file;
the offline gate supplies its own credential-free configuration. Relative override paths
are resolved from the relocated playbook, not the repository root.

## Operations

```bash
# health on the edge VPS
sudo systemctl status nginx tailscaled fail2ban ssh
sudo nginx -t && sudo ss -tlnp | grep nginx
sudo ufw status verbose && sudo fail2ban-client status sshd
tailscale status
sudo bash /opt/homelab-monitoring/scripts/check-services.sh   # trigger a monitor manually
```

**Migrate the edge VPS:** provision + day-0 with the same hostname (same MagicDNS name, no inventory change) → `ansible-playbook playbooks/edge.yml` → switch DNS A/AAAA records. Home servers are untouched.

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
| No ntfy messages arrive                | Topics: `inventory/group_vars/*/monitoring.yml` + vault; run a script manually. |
