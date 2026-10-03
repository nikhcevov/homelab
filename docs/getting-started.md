# Getting started

[Repository overview](../README.md)

Sources: [Ansible configuration](../ansible.cfg), [collections](../requirements.yml), [inventory](../inventory/hosts.ini), [group variables](../inventory/group_vars/), and [host variables](../inventory/host_vars/).

Run commands from the repository root. These day-0 instructions cover VPS hosts; use the [OpenWrt](openwrt.md) and [workstation](workstations.md) guides for their bootstrap procedures. After day-0, continue with the [edge](edge.md), [VPN](vpn.md), or [monitoring](monitoring.md#monitoring-vps) guide.

## Repository layout

```text
├── playbooks/                   flat entrypoints; run from the repository root
│   ├── edge.yml                 edge VPS: imports the 5 sibling layers below
│   ├── edge-bootstrap.yml       layer 1: OS hostname + base + ssh ┐
│   ├── edge-security.yml        layer 2: ufw + fail2ban           │
│   ├── edge-network.yml         layer 3: tailscale                ├ also standalone
│   ├── edge-proxy.yml           layer 4: nginx stream proxy       │
│   ├── edge-services.yml        layer 5: monitoring               ┘
│   ├── vpn.yml / vpn-restore.yml   VPN VPS deploy / restore
│   ├── mon.yml                  monitoring VPS deploy
│   ├── openwrt.yml / openwrt-upgrade.yml   routers deploy / upgrade
│   ├── unraid.yml               deploy backup scripts to Unraid
│   ├── workstation.yml          Arch/CachyOS desktops
│   └── proxy-render.yml         local nginx render (no VPS needed)
├── inventory/
│   ├── hosts.ini                active hosts and groups; router day-0 uses LAN
│   ├── group_vars/<group>/      one file per concern (bootstrap, ssh, security, ...)
│   └── host_vars/<host>.yml or <host>/   per-host deltas and encrypted secrets
├── ansible.cfg                  inventory source, root roles path, vault configuration
├── requirements*                pinned controller and collection dependencies
├── vars/                        public proxy.example.yml; private proxy.yml (gitignored)
├── roles/                       configuration behavior; monitoring/files owns checks
│   └── debian_common/           Debian-family (Debian/Ubuntu) baseline
├── files/                       shared SSH public keys, Unraid templates, tailnet policy
├── scripts/                     operator tools (laptop power benchmarks)
├── tests/                       offline Ansible gate
└── docs/                        operational guides
```

Inventory-adjacent variables load from `inventory/` even when a playbook is outside
the repository. Group settings remain shared defaults; host variables override them.
All entrypoints use the existing root `roles/` through `roles_path` in `ansible.cfg`.
The private routing map stays at `vars/proxy.yml`, resolved explicitly from the plays.

The edge inventory uses host `edge`, group `edge_nodes`, and
`inventory/group_vars/edge_nodes/`. For the existing node, complete the
[identity cutover](edge.md#existing-node-identity-cutover) before running the
updated playbooks; these files describe desired identity, not verified live state.

The [`debian_common` role](../roles/debian_common/tasks/main.yml) supplies the shared
Debian-family (Debian/Ubuntu) baseline for edge, VPN, and monitoring hosts. Its
configuration stays in each group's `bootstrap.yml` with the existing `bootstrap_*`
variables; Arch and OpenWrt use their separate `arch_common` and `openwrt_common` roles.

## Requirements

- Control machine: Python 3.14 with the pinned [controller](../requirements-controller.txt) and [collections](../requirements.yml); follow [local Ansible setup and checks](../CONTRIBUTING.md#local-ansible-checks).
- Edge VPS: Debian 12, x86_64; VPN/mon VPS: Debian 13 / Ubuntu 24.04+. Python 3 is the only target requirement. The [Tailscale installation platform contract](tailscale.md#installation-platforms) requires a published repository matching the host's distribution and release.
- A Tailscale tailnet with MagicDNS; `tailnet_domain` set once in `inventory/group_vars/all/tailscale.yml`.
- A reachable ntfy.sh topic for notifications.

## First run (new VPS)

**Day-0 (manual, once, on the host):**

1. Provision the VPS with your SSH public key.
2. Join the tailnet: `curl -fsSL https://tailscale.com/install.sh | sh && tailscale up --hostname=<name>`, open the login URL, then **disable key expiry** in the admin console — otherwise the node silently drops off the tailnet after 180 days.
3. Convention: inventory name = tailscale hostname, so `ansible_host` needs no change.

**On the control machine:**

```bash
ansible-galaxy collection install -r requirements.yml   # one-time
ansible-vault encrypt_string 'the-secret' --name vault_ntfy_topic_info  # add secrets to inventory/group_vars/*/vault.yml
cp vars/proxy.example.yml vars/proxy.yml && $EDITOR vars/proxy.yml      # edge routing map
ansible-playbook playbooks/edge.yml        # or playbooks/vpn.yml / playbooks/mon.yml for those hosts
```

Extra SSH keys: drop the `.pub` into `files/ssh/` and list it in `bootstrap_root_ssh_keys` (`inventory/group_vars/<group>/bootstrap.yml`). Public keys belong in Git.

## Secrets

In Git: templates, roles, inventory, playbooks, service/domain lists. **Never** plaintext: private keys, tokens, auth keys, passwords, real domains.

Secrets live as inline `!vault` blocks (`ansible-vault encrypt_string`) — shared ones in `inventory/group_vars/all/vault.yml`, per-group in `inventory/group_vars/<group>/vault.yml`, per-host in `inventory/host_vars/<host>.yml`. Keys and comments stay readable in diffs; Ansible decrypts natively. The real routing map `vars/proxy.yml` is plaintext-gitignored (config, not credentials).

The vault password lives in `.vault_pass` (gitignored, referenced by `ansible.cfg`) — keep it in your password manager; losing it means losing all secrets. Sanity check before pushing: `git grep -L '!vault' inventory/group_vars/ inventory/host_vars/` on files that should be encrypted.

| Vault var                            | Where                                | Why                                                     |
| ------------------------------------ | ------------------------------------ | ------------------------------------------------------- |
| `vault_ntfy_topic_*`                 | `inventory/group_vars/all/vault.yml` | ntfy topic name = password                              |
| `vault_tailscale_auth_key`           | `inventory/group_vars/all/vault.yml` | optional unattended tailnet join (empty = manual day-0) |
| `vault_kuma_domain`                  | `inventory/group_vars/mon/vault.yml` | real Kuma domain                                        |
| `vault_*_domain`, `vault_xui_*_path` | `inventory/host_vars/vpn-<cc>.yml`   | VPN domains + secret 3x-ui URL paths                    |
