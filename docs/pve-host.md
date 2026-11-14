# Proxmox host

[Repository overview](../README.md)

Sources: [playbook](../playbooks/pve.yml), [host](../roles/pve_host/),
[storage](../roles/pve_storage/), [GPU](../roles/pve_gpu/),
[VM](../roles/pve_vm/), [UPS](../roles/pve_ups/),
[PBS](../roles/pve_pbs/), [backup](../roles/pve_backup/),
[group variables](../inventory/group_vars/pve/).

PVE management/storage/private NFS/NUT, VM100 provisioning and guest baseline are applied.
All five bulk restores and cold guest appdata restoration passed full comparisons.
Production startup is authorized and applied; see [runtime evidence and limits](status.md#authorized-workload-startup--2026-11-14).
The destructive sequence and rollback boundaries are in the
[migration runbook](proxmox-migration.md#migration-plan).
Run controller commands from the repository root.

## Scope

| Role | Owned configuration |
| --- | --- |
| `pve_host` | Apt-source gate, ARC4 GiB ceiling, journald retention, private bridge, dual-family management filter |
| `debian_common`, `ssh`, `tailscale` | Base OS, key-only SSH and tailnet bootstrap |
| `pve_storage` | Opt-in blank pools, datasets/quotas, private NFSv4.1 exports and shutdown ordering |
| `pve_gpu` | Explicit opt-in IOMMU/VFIO configuration, both GPU functions; ASPEED remains available |
| `pve_vm` | Registered ZFS storage checks and ownership-marked resumable VM100 provisioning |
| `pve_ups` | Explicit opt-in standalone NUT, low-charge/runtime reserve and maximum battery timer |
| `pve_pbs`, `pve_backup` | Opt-in PBS lifecycle and independent file/config backups |

Manual prerequisites: ISO installation, a usable signed PVE repository,
static LAN address/hostname resolution, controller root key, IPMI access,
physical disk identity/erasure, and real recovery/power tests. No-subscription
repository selection is separate from the installer disk selection; the apt gate
fails rather than silently changing an enterprise subscription configuration.

## Bootstrap

1. Install PVE9 onto the identified SSD only. Configure `192.168.15.36/24`,
   gateway `192.168.15.1`, matching node hostname resolution and a DHCP exclusion
   or reservation. Do not rely on the router usually returning the same lease.
2. Move the inventory host from `[unraid]` to `[pve]` only after installation.
   Authorize the controller root key from the console and verify the new SSH
   fingerprint through IPMI before replacing its controller known-host entry.
   Root-key updates resolve the managed symlink and change content only, retaining
   pmxcfs's fixed ownership. `authorized_key` with `follow: true` still attempts
   `chown` and fails on this native store; it is not used for root-key updates.
   Before joining Tailscale, rename/archive the offline Unraid machine entry so
   the new host can reuse `great-hornbill`; preserve the old node for rollback.
   Without a subscription, disable both PVE and unused Ceph enterprise sources
   in Node → Updates → Repositories, then add the signed PVE No-Subscription
   repository. Keep Debian/security sources enabled; no reinstall is needed.
   The first run uses LAN because the new Tailscale identity does not exist yet:

   ```bash
   ansible-playbook playbooks/pve.yml --tags bootstrap --limit great-hornbill --force-handlers -e ansible_host=192.168.15.36 -e pve_host_management_filter=false
   ```

   `--force-handlers` applies validated SSH/sysctl/journald changes even if the
   manual Tailscale-login gate stops the play. If the old node name is not freed
   yet, explicitly pass an empty `tailscale_auth_key` to hold automatic joining.

3. Join the tailnet, confirm the actual MagicDNS name/IP and prove controller SSH
   plus independent IPMI recovery. Do not assume the old100.x address was reused.
   Then enable the management filter through Tailscale:

   ```bash
   ansible-playbook playbooks/pve.yml --tags bootstrap --limit great-hornbill -e pve_host_ipmi_verified=true
   ```

   Filtering allows loopback/tailscale0 to TCP22/8006 for IPv4 and IPv6; LAN
   management is intentionally blocked only at this point. Guest forwarding is
   unaffected.
4. Persist reviewed activation settings in inventory before routine reruns.
   `--check --diff` is not an execution rehearsal for hardware discovery,
   provisioning scripts, mount operations, reboot or shutdown behaviour.

`--tags bootstrap` selects only `pve_host`, `debian_common`, `ssh` and `tailscale`.
It excludes storage/NFS, GPU/UPS, VM/PBS and backup installation. A full untagged
run is not bootstrap-only, even with pool creation and backup timers disabled.
The PVE timezone stays `Asia/Yerevan`; no unattended upgrade/reboot is enabled.

`vmbr1` is a host-only bridge: `10.77.0.1/29`, no physical ports, no default
gateway. VM100 gets `.2`, PBS CT101 gets `.3`; the guest LAN interfaces remain
on `vmbr0`. Updating this bridge does not reload the physical LAN bridge.

## Pools and exports

Pool creation is deliberately not an automatic wipe operation:

1. Finish staging/checksum/restore prerequisites in the migration guide.
2. Explicitly erase only the selected source disks after confirming serials.
3. Populate `pve_storage_pools[].disks` and
   `pve_storage_approved_blank_disks` with by-id paths.
4. Run only storage, without activating unrelated roles:

   ```bash
   ansible-playbook playbooks/pve.yml --tags storage --limit great-hornbill -e pve_storage_create=true
   ```

   The role refuses partitions, signatures, mounted disks, duplicate assignment
   or unapproved identities; it never uses `zpool create -f`.

Only `/tank/photos`, `/tank/files`, `/media/data` are exported, bound to the
private host address and client `10.77.0.2/32`. The `mountpoint` export guard
refuses empty underlying directories if a dataset is not mounted. NFSv2/v3 and
other v4 minor versions are disabled. No appdata/database export exists.

`pve-guests.service` starts after NFS and stops before NFS during host shutdown.
The dependency is `Wants`, not `Requires`: restarting NFS must not invoke PVE's
stop-all-guests action. The real UPS test observed this ordering with an empty
guest inventory; actual VM shutdown durations still need proof after provisioning.

## VM and GPU

VM100 uses `local-zfs` backed by `rpool/data`, not a storage ID inferred from
pool name `rpool`. A dated Debian13 genericcloud image and its SHA512 are pinned
in [VM variables](../inventory/group_vars/pve/vm.yml).

Guest provisioning is off by default (`pve_vm_enabled: false`). After the storage
and GPU phase gates, explicitly authorize VM100 creation/reconciliation:

```bash
ansible-playbook playbooks/pve.yml --tags vm --limit great-hornbill -e pve_vm_enabled=true
```

Persist `pve_vm_enabled: true` only once this guest is approved for management.
The flag authorizes VM provisioning/boot, not application startup or restoration.

- Root160G, local appdata128G with SCSI serial `homelab-appdata`, 18 GiB RAM,
  six vCPUs, host CPU type and q35.
- OVMF/UEFI with dedicated4m EFI variable storage is selected. The real
  SeaBIOS+GTX1650 boot stalled before disk reads; the same OS disks boot with
  OVMF and both functions attached. Pre-enrolled keys are off. Serial console
  is explicit (`--vga serial0`); use `qm terminal 100`.
- The provisioner only reconciles its ownership-marked VM. Foreign VM IDs,
  ambiguous/orphan disks and incompatible attached disks require inspection.
  Interrupted managed shell/import steps can resume without recreating data.
  Volume inspection uses the native `pvesh` storage-content API; `pvesm list`
  does not support JSON output on this PVE. EFI variables must be separate
  from root/appdata. Actual fresh creation, running no-op and stopped restart
  passed; safety regressions cover root reuse, orphan refusal and EFI aliasing.
- GPU binding requires `pve_gpu_configure=true`. Both GTX1650 functions must be
  on vfio-pci before VM autostart; unrelated IOMMU companions and ASPEED takeover
  are refused. Do not enable ACS override to make an invalid group pass.

  GPU-only activation:

  ```bash
  ansible-playbook playbooks/pve.yml --tags gpu --limit great-hornbill -e pve_gpu_configure=true
  ```

  On2026-11-13 the real91-second reboot passed: `01:00.0`/`.1` use `vfio-pci`,
  ASPEED `05:00.0` remains `ast`/boot VGA, and `00:01.0` remains `pcieport`.
  This proves host binding, not guest GPU workloads. Boot-config rollback and
  evidence: `/root/migration-hardware-20261113T191056Z`.
- A root mirror remains a later hardware step; start with a second SATA SSD
  unless the board/adapter's NVMe bifurcation support has been established.

VM100 runs on LAN `192.168.15.49`, private `10.77.0.2` and tailnet `100.124.158.33`.
Guest agent, paired cloud kernel/headers, NVIDIA595.112.07 and Container Toolkit
are verified after planned reboots; a real CUDA GPU-memory write/readback passed.
Appdata128G is ext4, restored and fully compared; Docker is now explicitly authorized and active.
SSH host trust was pinned from the hypervisor serial-console fingerprint:

```bash
ssh boss@192.168.15.49
# Or through the trusted host when only its tailnet route is available:
ssh -J root@great-hornbill.han-diatonic.ts.net boss@10.77.0.2
```

The guest has joined Tailscale; strict SSH to `boss@docker-1.han-diatonic.ts.net`
and a full zero-change baseline rerun passed. LAN/private routes remain recovery paths.
Cloud-init retains its upstream deprecated string-`user` warning; fatal errors
are empty. Provisioning evidence: `/root/migration-vm100-20261113T195457Z`;
baseline evidence: `/root/migration-guest-baseline-20261113T203354Z`.
Cold appdata proof: `/root/migration-appdata-20261113T212605Z`.
The checksum/metadata/extra-file gate and independent hardlink/special-file topology
comparison passed; temporary migration access was removed. Both startup markers
now exist following separate operator approval. Workload evidence:
`/root/migration-workloads-20261114T081708Z`. Real Immich CUDA inference and bounded
Jellyfin NVDEC/NVENC passed; this is not a populated-guest UPS shutdown test.
Disk-only `pre-workloads-20261114t081708z` retains pre-start root/appdata/EFI;
it excludes NFS/RAM/GPU state and does not replace independent backup.

## UPS

Enable with `pve_ups_configure=true` only at physical cutover. USB remains on the
host. The audited UPS firmware reports UT1050EG, 630 W nominal; USB descriptor
CP1500 AVR is not treated as the actual model.

Apply only UPS configuration, without storage/guest/backup roles:

```bash
ansible-playbook playbooks/pve.yml --tags ups --limit great-hornbill -e pve_ups_configure=true
```

The role reloads packaged USB udev rules and reapplies them to
`pve_ups_usb_vendor_id` / `pve_ups_usb_product_id` (default0764:0501). This fixes
fresh installation with an already attached root:root USB node without running
the driver as root or granting world-write access. Real driver/server/monitor
and telemetry are active. Safe monitor-signal/isolated scheduler checks passed,
followed by the physical host shutdown/output-cut/power-return test below.

NUT uses `MODE=standalone`, local-only upsd, vaulted monitor credentials, a
25% charge/600-second runtime reserve and a600-second on-battery timer
(`pve_ups_onbattery_timeout_seconds`, default600). The scheduler callback is
executable by group `nut`; NUT invokes normal host shutdown, which stops guests
before host NFS. No custom PVE poweroff hook is needed merely to stop guests.

With IPMI present, test mains loss, reserve/timer triggering, actual guest
shutdown duration, final UPS power cut and return-of-power behaviour. Configure
firmware power recovery deliberately. Do not use `upsmon -c fsd` as a harmless
probe: it initiates the shutdown chain. `upsc` success proves only communication.

On2026-11-13 a real physical mains-loss test passed using an operator-requested
temporary120-second timeout. The real timer triggered FSD after120.4 seconds;
the journal proves PVE stopped before NFS and ZFS unmounted. Operator observed
UPS output power-off and startup after mains restoration. The production600-second
timeout was restored and verified immediately after recovery, with reserves
unchanged. Evidence: `/root/migration-hardware-20261113T191056Z`.
No guests existed during that physical test. On2026-11-14, populated VM100's
QEMU-agent shutdown completed in35.676s with no forced container termination
after correcting qbit_manage's stop budget; restart, data, private mounts and GPU
passed. Evidence: `/root/migration-lifecycle-20261114T104107Z`.
The host stayed online during that earlier guest-only test.

On2026-11-14 a populated physical UPS cycle passed with VM100 and CT101.
The unchanged production600-second timer triggered after600.834s; VM100
stopped in36.139s before host NFS shutdown. All34 original containers stopped
without SIGKILL/137. The operator observed server shutdown, UPS output-off,
and automatic server startup after restoring only UPS input mains.
Pools, the retained vault mount, application data, real photo/PDF NFS reads
and GPU device-memory readback recovered. PBS's runtime-directory boot failure
was corrected persistently and proved by a separate CT-only reboot, pinned API,
existing backup listing and rendered sign-in UI.
Evidence: `/root/migration-ups-populated-20261114T174036Z`,
`ups-physical-populated.COMPLETE.json`.
Low-battery reserve discharge triggering remains unproved; this was the real
timer path, not a synthetic FSD. Do not leave a shortened test timeout active.

## Verify

On PVE:

```bash
pveversion
hostname --ip-address
zpool status -x
zfs list -o name,used,avail,mountpoint
pvesm status --storage local-zfs
exportfs -v
ip -br a
tailscale status
qm config 100
qm status 100
cat /sys/module/zfs/parameters/zfs_arc_max
upsc cyberpower@localhost
```

Expected: correct pool mounts and quotas, three private exports, both VM disks,
private NIC, correct VFIO ownership and running guest once explicitly enabled.
ARC changes apply after initramfs/reboot. NFSv3-only `showmount` discovery is not
a readiness gate for the v4-only server.

Validate management from two clients: tailnet SSH/8006 works, LAN/IPv6
non-tailnet management is refused, application forwarding still works. Test
missing datasets without exporting writable empty fallback directories.

## Recover

- Wrong/unmarked VM or CT: inspect config and disks; no automatic adoption,
  deletion or destructive repair is performed.
- Apt401: disable the unsubscribed enterprise source and configure the signed
  no-subscription repository; a reinstall is not necessary solely for this.
- Management lockout: use IPMI/console. To temporarily remove only our management
  restriction, without flushing other firewall policy:

  ```bash
  systemctl disable --now homelab-management-filter
  for tool in iptables ip6tables; do
      "$tool" -D INPUT -p tcp -m multiport --dports 22,8006 -j HOMELAB-MGMT
  done
  ```

  Stopping the oneshot unit alone does not clear installed rules. Restore and
  verify tailnet/IPMI access, then rerun bootstrap to re-enable the restriction.
- VFIO mismatch: inspect both functions/IOMMU companions after hardware changes;
  do not blindly reuse the old PCI addresses.
- Missing NFS: restore the actual dataset mount before re-exporting. Do not
  create an empty directory to bypass the check.
- UPS issue: inspect `nut-driver@cyberpower`, `nut-server`, `nut-monitor`,
  scheduler permissions and the configured USB device before enabling timers.
- SSD or pool loss: follow [backup bootstrap](backups-proxmox.md#ssd-loss-bootstrap).
