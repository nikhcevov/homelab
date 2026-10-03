# SSH public keys

Drop your public SSH keys here, bird-named after the device, e.g. `starling.pub` (one key per file).

`little-raven.pub` is the main operator PC's public key. Keep private keys on their source machines; only public keys belong here.

| Target | Login | Key list |
| ------ | ----- | -------- |
| Edge, VPN, monitoring VPSes | `root` | `bootstrap_root_ssh_keys` in each group's `bootstrap.yml` |
| OpenWrt routers | `root` | `ssh_authorized_keys` in `inventory/group_vars/routers/ssh.yml` |
| Unraid | `root` | `ssh_authorized_keys` in `inventory/group_vars/unraid/ssh.yml` |
| Workstations | `boss` | `workstation_ssh_keys` in `inventory/group_vars/workstations/common.yml` |
| Home Assistant | `boss` | Advanced SSH & Web Terminal add-on's `ssh.authorized_keys` option |

All inventory groups include `little-raven.pub`. VPSes, workstations, and Unraid add keys without removing existing access; routers render their configured key list authoritatively. Unraid updates both persistent flash and active SSH paths. Home Assistant's options are managed separately from Ansible; retain the backup collector's key when adding the operator key.

Apply only authorized keys, without upgrades, SSH daemon changes, or other service configuration:

```sh
ansible-playbook playbooks/edge.yml --tags ssh_keys
ansible-playbook playbooks/vpn.yml --tags ssh_keys
ansible-playbook playbooks/mon.yml --tags ssh_keys
ansible-playbook playbooks/openwrt.yml --tags ssh_keys
ansible-playbook playbooks/unraid.yml --tags ssh_keys
ansible-playbook playbooks/workstation.yml --tags ssh_keys --ask-become-pass
```

For the local operator workstation, key-only deployment needs no root privilege:

```sh
ansible-playbook playbooks/workstation.yml --tags ssh_keys \
  --limit little-raven -c local -e ansible_become=false
```

Initial access still requires an already authorized key or the machine's console. Offline machines receive the configured keys only when their playbook is applied after they return online. Verify access using the source key explicitly:

```sh
ssh -o BatchMode=yes -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 \
  root@edge.han-diatonic.ts.net id -un
```

[Repository overview](../../README.md)
