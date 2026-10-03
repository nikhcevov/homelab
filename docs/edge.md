# Edge VPS

[Repository overview](../README.md) · [Getting started](getting-started.md) · [Tailscale policy](tailscale.md) · [Monitoring](monitoring.md)

Sources: [playbooks/edge.yml](../playbooks/edge.yml), [routing example](../vars/proxy.example.yml), [edge variables](../inventory/group_vars/edge_nodes/), and [nginx role](../roles/nginx/).

Run commands from the repository root.

## Setup and updates

`playbooks/edge.yml` is the single Edge deployment entrypoint. It runs five plays
in order: bootstrap, security, network, proxy, services. Each targets only
`edge_nodes` and retains its own handler flush boundary. VPN and monitoring hosts
reconcile Tailscale through `playbooks/vpn.yml` and `playbooks/mon.yml`. Stages
depend left to right (proxy needs tailnet DNS; monitoring expects nginx).
Bootstrap reconciles the edge OS hostname to `inventory_hostname`; no other
group's OS hostname is managed by this task.

```bash
ansible-playbook playbooks/edge.yml                    # setup or update, all stages
ansible-playbook playbooks/edge.yml --tags bootstrap   # OS hostname + base system + SSH
ansible-playbook playbooks/edge.yml --tags security    # firewall + fail2ban
ansible-playbook playbooks/edge.yml --tags network     # Tailscale
ansible-playbook playbooks/edge.yml --tags proxy       # nginx only
ansible-playbook playbooks/edge.yml --tags services    # monitoring
```

Tags are optional focused reconciliation, not separate setup modes. Select several
with `--tags network,services`; order remains fixed. For routing changes, run the
full default command so both firewall listeners and proxy configuration update.
Bootstrap, network, and services runs do not load the routing file. Security loads
it only when `ufw_open_service_ports` is enabled; proxy loads it when selected.
Both controller loads accept `-e proxy_vars_file=/absolute/path/to/routing.yml`
(default `vars/proxy.yml`), and extra variables retain precedence over that file.

The inventory group is `edge_nodes`; scoped runs use `--limit edge_nodes`.
Its one host is `edge`, reached at `edge.{{ tailnet_domain }}` after the console
rename. Tailscale hostname follows `inventory_hostname`; monitoring derives
`[EDGE]` from that same authority. VPN and monitoring groups are unchanged.

## Existing-node identity cutover

This is **repository preparation**, not evidence of live changes. The previous
identity was `edge-proxy` / `tag:vps`; the desired identity is `edge` / `tag:edge`.
The policy keeps the old tag temporarily with identical restricted grants.
No Ansible task advertises tags or re-authenticates the existing node.

The operator owns these external steps, in order:

1. Open the policy PR and require **Validate policy** (including provider policy
   tests) to pass. Merge/apply through the [policy runbook](tailscale.md#normal-policy-changes)
   and wait for a successful **Apply policy** job before assigning `tag:edge`.
   Local JSON/equivalence checks do not replace these credentialed checks.
2. In [Machines](https://console.tailscale.com/admin/machines), identify the
   **existing** node by its device details and Tailscale IP; record the current
   name, tags, IP, and OS hostname for rollback. Use **Edit tags** to replace
   `tag:vps` with `tag:edge`, keeping at least one tag throughout. Do not add
   `tag:home`, `tag:homeassistant`, or another privileged tag: tag permissions
   are additive. Console tag replacement needs no re-authentication.
3. Verify the same restrictions: home/homeassistant TCP 443 and home TCP 25565 /
   UDP 24454 work; backend 4743, SSH 22, SMB 445, management 18080/18443,
   homeassistant 8123, routed-LAN SSH, and unrelated internet access stay denied
   from the edge. Trusted-home native SSH to the edge must still work.
4. Check that no other node owns `edge`, then use **Edit machine name** on this
   same node to set `edge` (disable **Auto-generate from OS hostname** for the
   explicit console name). Verify `edge.<tailnet>.ts.net` resolves to the
   recorded IP and same node, not a suffixed or replacement device.
5. Only after the rename and reachability checks, run
   `ansible-playbook playbooks/edge.yml --limit edge_nodes`. Bootstrap reconciles
   the OS hostname to `edge`; network reconciles Tailscale's hostname without
   re-authentication; services render the derived `[EDGE]` alert prefix.
   Verify OS hostname, MagicDNS, proxy listeners, and monitoring afterwards.
6. Review external consumers yourself: Kuma monitors, SSH config, provider
   labels, and any other references to the old name are not reconciled here.
   Their current state is unknown to this repository.

Until the console rename is complete, any intentional connection must use the
node's **verified current Tailscale IP** as an explicit, one-run override:

```bash
ansible edge_nodes -m ansible.builtin.ping -e "ansible_host=<current-tailscale-ip>"
```

Do not store a permanent old-name fallback or run the updated deployment early.
Public DNS and proxy backend names/routing files are unchanged by this migration.

### Identity rollback and later contraction

While the overlap policy remains applied, replace the node's tag back to
`tag:vps` (retain a tag), restore its recorded console name `edge-proxy`, and
verify MagicDNS and the original restrictions. If deployment changed the OS
hostname, restore its recorded value intentionally on the node as well.
Restore external consumers you changed. Use an explicit current-IP override
for recovery with this branch, or restore the pre-migration repository identity
in a separate reviewed commit before normal Ansible deployment; do not run
updated hostname reconciliation against an intentionally rolled-back name.

Keep `tag:vps` in the policy until the operator confirms **no device uses it**
and the cutover is verified. Its deletion is a later, separately validated
policy contraction, not part of this preparation or a permanent tag alias.

References: [Tailscale tags](https://tailscale.com/docs/features/tags) and
[machine names / MagicDNS](https://tailscale.com/docs/concepts/machine-names).

## Configuration

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

### `inventory/group_vars/edge_nodes/` — one file per concern

| File             | Configures    | Highlights                                                                   |
| ---------------- | ------------- | ---------------------------------------------------------------------------- |
| `bootstrap.yml`  | debian_common | packages, timezone, locale, unattended-upgrades, extra root keys, admin user |
| `ssh.yml`        | ssh           | `sshd_port` + auth modes — defined once, consumed by sshd, ufw and fail2ban  |
| `security.yml`   | ufw, fail2ban | default policies, static rules, `ufw_open_service_ports`, ban policy         |
| `tailscale.yml`  | tailscale     | hostname, optional auth key (from vault)                                     |
| `monitoring.yml` | monitoring    | checked units, disk threshold/mounts, backup freshness, host prefix          |

Firewall rules come from three merged sources: the SSH port, the static `ufw_rules` list, and the listen ports of every service in `vars/proxy.yml`. The security play in [`playbooks/edge.yml`](../playbooks/edge.yml) loads that routing file only when `ufw_open_service_ports` is enabled and passes the same `services` map used by nginx to UFW as `ufw_proxy_services`. The [UFW role](../roles/ufw/tasks/main.yml) consumes this explicit mapping; it does not locate or read routing files. Enabled automatic ports require that input (a missing or non-mapping value fails instead of silently omitting proxy listeners). VPN and monitoring disable automatic proxy ports and need neither the routing file nor this input.

Proxy listeners are deduplicated by port **and** protocol; omitted protocols default to TCP. Listeners already covered by SSH or static rules are excluded, and a shared SNI listener keeps the first service's `proxy: <service>` comment. Existing rules are not purged.

Switching from root to an admin user: set `bootstrap_admin_user`(+`_ssh_keys`), run `ansible-playbook playbooks/edge.yml --tags bootstrap`, switch `ansible_user` in inventory, set `sshd_permit_root_login: "no"`, re-run `playbooks/edge.yml`.

## Local render test (no VPS needed)

```bash
ansible-playbook playbooks/proxy-render.yml && cat /tmp/rendered-stream.conf
```

The command above uses the private `vars/proxy.yml` and the normal vault configuration. For a credential-free check using the public example, run the [offline Ansible gate](../CONTRIBUTING.md#local-ansible-checks). To select another routing file, pass `-e proxy_vars_file=/path/to/routing.yml`; `-e proxy_render_dir=/existing/output/directory` redirects both rendered files (default `/tmp`).

Routing-file overrides should be absolute, for example:

```bash
ansible-playbook playbooks/proxy-render.yml -e "proxy_vars_file=$PWD/vars/proxy.example.yml"
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
