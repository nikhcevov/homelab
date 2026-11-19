# SSH public keys

Drop your public SSH keys here, bird-named after the device, e.g. `starling.pub` (one key per file).

`starling.pub` is the desktop; `little-raven.pub` is the laptop, which hosts the homelab repository and is the management controller. Keep private keys on their source machines; only public keys belong here.

Rotating a machine's key means replacing its file: every consumer references it by filename. Root key lists on VPSes/PVE/Docker, Docker operator keys and workstation keys are additive, so the previous key blob stays authorized until purged by hand. Routers render their configured list authoritatively.

| Target | Login | Key list |
| ------ | ----- | -------- |
| VPSes, PVE and Docker VM | `root` | `bootstrap_root_ssh_keys` in each group's `bootstrap.yml` |
| OpenWrt routers | `root` | `ssh_authorized_keys` in `inventory/group_vars/routers/ssh.yml` |
| Docker VM | `boss` | `docker_vm_ssh_keys` in `inventory/group_vars/docker/docker_vm.yml` |
| Workstations | `boss` | `workstation_ssh_keys` in `inventory/group_vars/workstations/common.yml` |
| Home Assistant | `boss` | Advanced SSH & Web Terminal add-on's `ssh.authorized_keys` option |

`github-actions.pub` is the GitHub Actions container-deploy key. Only its public
half belongs here; the private half is the `SSH_PRIVATE_KEY` environment secret.

Managed key lists include `little-raven.pub`. Additive updates retain existing access; they do not revoke rotated keys. Home Assistant's options are managed separately from Ansible; retain the backup collector's key when adding the operator key.

Apply only authorized keys, without upgrades, SSH daemon changes, or other service configuration:

```sh
ansible-playbook playbooks/edge.yml --tags ssh_keys
ansible-playbook playbooks/vpn.yml --tags ssh_keys
ansible-playbook playbooks/mon.yml --tags ssh_keys
ansible-playbook playbooks/openwrt.yml --tags ssh_keys
ansible-playbook playbooks/pve.yml --tags ssh_keys
ansible-playbook playbooks/docker.yml --tags ssh_keys
ansible-playbook playbooks/workstation.yml --tags ssh_keys --ask-become-pass
```

Docker's key-only command updates root keys; operator keys are reconciled by the
[guest baseline](../../docs/docker-stacks.md#baseline-and-authorization).

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
