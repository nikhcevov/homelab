# Getting started

[Repository overview](../README.md)

Sources: [Ansible configuration](../ansible.cfg), [collections](../requirements.yml), [inventory](../inventory/hosts.ini), [group variables](../group_vars/), and [host variables](../host_vars/).

Run commands from the repository root. These day-0 instructions cover VPS hosts; use the [OpenWrt](openwrt.md) and [workstation](workstations.md) guides for their bootstrap procedures. After day-0, continue with the [edge](edge.md), [VPN](vpn.md), or [monitoring](monitoring.md#monitoring-vps) guide.

## Repository layout

```text
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
├── host_vars/<host>.yml or <host>/   per-host deltas and per-host vault secrets
├── vars/proxy.yml               edge routing map (gitignored; see proxy.example.yml)
├── roles/                       common, ssh, ufw, fail2ban, tailscale, nginx, monitoring,
│                                xui, caddy, vpn_backup, kuma, kuma_backup, openwrt_*,
│                                arch_common, arch_packages, keyd, docker, dotfiles, syncthing
├── roles/monitoring/files/       monitoring checks (bash) + cron definition
├── scripts/                     operator tools (laptop power benchmarks)
└── files/                       ssh public keys, Unraid backup-pull script
```

## Requirements

- Control machine: Python 3.14 with the pinned [controller](../requirements-controller.txt) and [collections](../requirements.yml); follow [local Ansible setup and checks](../CONTRIBUTING.md#local-ansible-checks).
- Edge VPS: Debian 12, x86_64; VPN/mon VPS: Debian 13 / Ubuntu 24.04+. Python 3 is the only target requirement. The [Tailscale installation platform contract](tailscale.md#installation-platforms) requires a published repository matching the host's distribution and release.
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
