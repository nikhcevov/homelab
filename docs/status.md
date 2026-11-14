# Current status

[Repository overview](../README.md)

Snapshot: 2026-11-15. Entry point for the Unraid → Proxmox migration.
Baseline cold staging passed full checksum comparisons for all eight trees.
Unraid writers remained stopped through the verified migration checkpoint.
PVE9.2.26 management is applied, tailnet-only and verified after the new-kernel reboot.
Independent vault snapshot `57492bf21849` completed; metadata check and22 GiB
representative restore passed. Keep both10 TB disks and the Unraid USB intact.
Live checks verify pinned SSH, the native key-store link/ownership, healthy
`rpool`, `local-zfs` and4 GiB ARC. No host-key checking was bypassed.
Reconnected HDDs are identified; both10 TB copies passed read-only recovery checks.
Google Drive remains cancelled. Approved8+8+4 TB cutover created healthy ZFS pools.
All five bulk mappings passed full checksum/metadata comparisons, exit0,
on2026-11-13 at23:06:09+04:00. VM100 boots; guest storage/GPU/runtime/Tailscale
are configured. Authorized production startup completed:12 stacks /34 containers
running, all configured healthchecks healthy and zero container restarts.
Existing application data and bounded GPU/client paths were exercised.
Public HTTPS and game ingress now target Docker VM100; external MQTT remains unavailable.
The populated physical UPS cycle and automatic power-return recovery passed.
Automatic backup schedules are armed. Local `home.arpa` works for manually
configured DNS clients; the VM's current LAN lease is not reserved.

Sources: [migration/runbook](proxmox-migration.md), [host](pve-host.md),
[Docker](docker-stacks.md), [backups/recovery](backups-proxmox.md),
[monitoring](monitoring.md), [HDD research](hdd-price-research.md).

## State by area

| Area | State | Authority |
| --- | --- | --- |
| Architecture review and source audit | Applied to desired configuration | Migration guide |
| Compose stacks | Twelve deployed;34 containers running; audited images retained | `compose/`, Docker inventory |
| Secrets/configuration | Vaulted inputs; sanitized Caddy/LiteLLM templates versioned | Docker/PVE vaults and templates |
| Host/storage/GPU/UPS | GPU VFIO and NUT applied; populated physical UPS shutdown/output-cut/automatic power-return passed | `pve_host`, `pve_storage`, `pve_gpu`, `pve_ups` |
| VM provisioning | VM100 running with OVMF, both GPU functions, verified agent/SSH; explicit host approval persisted | `pve_vm` |
| Docker baseline | Ext4 appdata/private NFS and NVIDIA/toolkit/tailnet applied; Docker guarded and active | `docker_vm`, `nvidia_guest`, `docker_debian` |
| Workload deployment | Explicitly authorized after cold restore; native data/API/GPU proofs recorded | `compose_stacks` |
| Guest appdata restoration | 49.1 GB copied; full checksum/metadata/extra-file gate and independent topology comparison passed | [Cold restore](proxmox-migration.md#phase-5--restore-and-authorize-workloads) |
| PBS | CT101/PBS4.2.10; native restore and proxy boot recovery passed; daily backup and maintenance schedules enabled | `pve_pbs` |
| Restic/collector | Full backup/recovery passed; eleven historical snapshots protected; four timers enabled with future NEXT at activation | `pve_backup`, `docker_backup` |
| Cloud restic | Cancelled after account loss; partial quota-limited upload is not usable protection | Cancellation markers and retained diagnostic log |
| Local staging | Final stopped mirror completed, exit0; eight zero-data-delta/metadata proofs retain baseline full checksums | [Final stopped sync](proxmox-migration.md#final-stopped-sync) |
| Independent migration backup | Completed, exit0; all eight trees/recovery, metadata check and22 GiB real restore passed | [Vault refresh](proxmox-migration.md#independent-pre-cutover-vault-refresh) |
| CI gates | Ansible, all-stack Compose, vaulted references, migration safety regressions | `tests/`, Ansible workflow |
| Monitoring | Existing external Kuma retained | Monitoring guide |
| Cutover/decommission | Public edge and temporary manual-client DNS verified; schedules armed; first automatic nightly result, stable LAN and decommission remain | Sequential migration gates |

## Decisions now in force

- `tank` remains an 8+8 mirror; `media/data` remains one replaceable 4 TB dataset.
  Old10 TB retains the existing restic repository; new10 TB is internal migration
  staging and can later hold a second local restic repository. Both use plain XFS;
  restic encrypts repository contents, not raw staged files. No disk leaves home.
  Do not erase either backup disk to build primary storage.
- VM100 has guest-local160G root/Docker and a128G appdata disk on
  `local-zfs` / `rpool/data`. Appdata is restored and fully compared against
  read-only staging before startup. No database/appdata NFS export exists.
- Private `vmbr1`: PVE `.1`, Docker `.2`, PBS `.3` on `10.77.0.0/29`, no physical
  uplink/gateway. Only bulk data is exported to `.2/32`, with runtime mount guards.
- PVE has static day-zero LAN identity; the VM's LAN NIC can remain DHCP.
  SSH/8006 are tailnet-only after independent IPMI/tailnet proof.
- One Docker VM owns both GTX1650 functions; ASPEED remains the host console.
  OVMF/UEFI is selected after real SeaBIOS+GTX1650 early-boot failure; no disk rebuild.
- Application image versions stay at audited source digests. The Debian image
  is dated/checksum pinned. GPU driver uses signed APT packages, not a runfile.
- No container startup before verified restoration and explicit authorization.
  Baseline installation/reboot cannot bootstrap empty databases.
- Backups: stop writers → PostgreSQL dumps → stop DBs → cold appdata copy and
  bulk snapshots → resume original running set → restic. No long repository scan
  during application downtime. PBS independently images both guest disks.
- Local target RPO24 hours. A second internal repository is local redundancy,
  not off-site protection. Google Drive is cancelled after account loss; no
  accessible remote backup is established. Keep the old vault intact and prove
  current independent local recovery before cutover. A new remote target is deferred.
- Preserve `domains/haos-krm/haos.qcow2`; it is not disposable merely because the
  libvirt service is inactive. Restore collector data before retiring Unraid jobs.
- Keep ZFS, Caddy host networking, temporary Technitium DNS and external Kuma.
  Metrics, Gatus and hardware upgrades are deferred, not prerequisites invented
  for this migration.

## Source audit and migration checkpoints

- `/var/log` is full (128 MiB tmpfs). Approximately60 MiB rotated syslog and54 MiB
  nginx logs were present; audit did not delete or rotate them.
  Follow-up cleared203 MiB of Docker JSON logs only; all32 running containers
  remained running. Docker logs are on a different filesystem, so `/var/log`
  remains full; system/nginx logs were not cleared.
- UPS firmware reports UT1050EG /630 W nominal, despite its generic CP1500 USB
  descriptor. Existing apcupsd limits:25% charge,10 minutes reserve,600 seconds
  on battery. Controlled NUT/guest/NFS shutdown testing is still required.
- Paperless2.20.15 uses PostgreSQL and had86 documents; Immich3.1.0 had no active
  external libraries. The removed `/toshiba` mount has no active library refs.
- Source/vault comparisons confirmed Paperless and order-manager credentials;
  collector key identity matched the repository public key. Private values were
  not printed; migration key/pins are encrypted in the PVE vault.
- SSD SMART/btrfs error counters were clean, but no scrub history existed.
  Sleeping HDDs did not provide fresh SMART attributes to standby-safe queries.
- New10 TB disk `19L0A0EDFHLG` now has full-capacity GPT/XFS, label `HLSTAGING`,
  UUID `d0347cdb-9c3b-41e8-88ce-498367a6f038`, mounted at `/mnt/staging`.
  No health/zeroing tests were repeated. All required shares plus flash/host
  recovery finished staging; the post-install reconnection check is recorded below.
- The operator confirmed IPMI access and the current `192.168.15.36` address.
  Future `192.168.103.1` belongs to the router; Proxmox will get another address
  on the new LAN. Server address and network changes are deferred.
- Google Drive is cancelled by the operator after loss of the account. The seed
  stopped on `403 userRateLimitExceeded` after750.535 GiB and exited1 at
  13:43+04:00; it was not accidentally killed. No restic/rclone cloud process or
  recurring retry is active. Do not contact or resume this target without renewed
  authorization. Cancellation is recorded in the source workspace and staged
  recovery `cloud-backup/CANCELLED`.
  The initial encrypted fixture restore passed, but the real history seed never
  completed and cannot count as recoverable protection. Existing credentials and
  logs are retained privately, not deleted or committed; the restic password still
  protects the local vault. See [cancelled seed](backups-proxmox.md#initial-cloud-seed).
- Saved the exact32-container running set; flushed Minecraft and dumped four
  PostgreSQL clusters before clean database shutdown (all four exited0). Docker
  was stopped without custom-network teardown; host DNS remains Cloudflare and
  the cloud upload kept progressing after shutdown and Docker-image freezing.
  The cold worker finished2026-11-11 at23:30:47+04:00 with exit0. All eight
  source/target marker pairs match and their difference reports are empty.
  Recovery `COMPLETE` and its exit0 were checked independently. Original writer
  cron contents were restored byte-for-byte; Docker remains stopped. The target
  is mounted at `/mnt/staging`, with about2.9 TiB used and6.3 TiB free.
  Resuming applications requires another final stopped sync before cutover.
  Controls and restart state are in the
  [cold-copy operation](proxmox-migration.md#current-cold-copy).
- Final sync completed2026-11-12 at02:11:23+04:00 with exit0 in both locations.
  All eight marker pairs match and final difference reports are empty. No regular
  files needed transfer; prior full byte checks remain the content proof, with
  new zero-data-delta/metadata comparisons. Flash/host archives were refreshed;
  recovery hashes passed. Controls:
  `/mnt/cache/appdata/migration-rclone/finalsync-20261111T204831Z`.
  At10:51+04:00 no copy/application processes remained and the five scheduled
  writers were still held; SMB remained stopped. Staging has2.9 TiB used/6.3 TiB
  free. The SSH observer's exit255 did not affect the detached worker.
  At the pre-refresh check, the old vault had10 snapshots, newest2026-11-08;
  the independent refresh below supersedes that recovery-freshness gap.
- Independent vault refresh completed2026-11-12 at18:44:29+04:00, exit0 in
  both control and independent evidence. Snapshot `57492bf21849` covers all eight
  staging trees plus recovery:885,309 files /3.141 TB processed, zero errors,
  about1.019 TB new packed data. All10 prior snapshots remain; metadata checking
  found no errors across11 snapshots. An actual22.032 GiB restore passed,
  including complete final recovery/four SQL dumps, the Home Assistant disk and
  personal/Paperless/original-photo samples. Recovery SHA256 and sampled
  bytes/owners/modes/ACLs/xattrs matched; disposable restore files were removed.
  Controls: `/mnt/cache/appdata/migration-rclone/vault-refresh-20261112T070305Z`.
  Independent proof:
  `/mnt/vault/migration-recovery/vault-refresh-20261112T070305Z`.
  Staging remains read-only, scheduled writers held and applications stopped.
  This was representative restore proof, not a full repository data scan.
  SSD-only PVE installation is now confirmed. The next destructive boundary is
  separately approved HDD pool creation; preserve both10 TB disks and the Unraid USB.
- Management-only bootstrap switched PVE to signed No-Subscription and disabled
  unsubscribed PVE/unused Ceph enterprise sources, retaining Debian/security.
  Rollback source archive:
  `/root/migration-bootstrap-20261112T184339Z/apt-sources.before.tar`.
  Safe upgrades installed PVE9.2.26 and kernel7.0.14-28-pve. A controlled reboot
  completed in85 seconds; the new kernel is running and post-reboot access checks passed.
- The first apply exposed pmxcfs's fixed key-store ownership: `authorized_key`
  follows the link but still attempts `chown`, failing after its content write.
  Root-key management now resolves the linked store and updates public-key lines
  without overriding native ownership. Real pmxcfs and regular-file probes
  passed, including preserved existing keys, link, owner/group/mode and idempotence;
  all disposable probe files were removed.
- Management bootstrap is complete. Fresh key-auth SSH works; password SSH is
  disabled; private `vmbr1` retains `10.77.0.1/29` with no physical ports.
  Gateway remains `192.168.15.1`, timezone `Asia/Yerevan`, ARC4 GiB and native
  root keys linked/root:33/0600. At that bootstrap, only SSD `25331E800584` and
  `rpool` were present; no VM/CT, HDD pool creation or GPU/UPS/backup activation occurred.
- The operator renamed the preserved old machine to `great-hornbill-unraid`.
  The stored unattended join key failed; browser authorization joined the new
  `great-hornbill.han-diatonic.ts.net` with key expiry disabled. Addresses:
  `100.113.245.34`, `fd7a:115c:a1e0::3328:f523`. Controller trust entries preserve
  the old machine under its renamed identity and pin the new node's verified key.
- Operator-confirmed IPMI recovery and the management-filter approval persist in
  `inventory/host_vars/great-hornbill.yml`. Tailnet-only TCP22/8006 filtering is
  active for IPv4/IPv6. SSH and HTTPS200 passed over tailnet IPv4 and direct IPv6;
  both LAN ports were blocked. These checks, the private bridge, native keys and
  healthy storage passed again after reboot. Controller IPv6 hostname resolution
  returned no address, so the IPv6 proof used the assigned literal address.
  Manage PVE at `https://great-hornbill.han-diatonic.ts.net:8006/`, not its LAN URL.

## Reconnected storage — 2026-11-13

| Disk | Serial | Current role/state |
| --- | --- | --- |
| 1 TB SanDisk SSD | `25331E800584` | PVE `rpool`; preserve |
| 8 TB WD | `WD-CA2HLH6L` | ZFS `tank` mirror member |
| 8 TB Seagate | `WSD1B75J` | ZFS `tank` mirror member |
| 4 TB HGST | `K7J5HTSB` | ZFS `media` pool |
| 10 TB Toshiba | `19L0A0EDFHLG` | Retained staging; manual read-only mount, currently unmounted after UPS reboot |
| 10 TB Toshiba | `28W0A2QGFKQE` | Retained restic at `/mnt/vault`; fresh rw mount for new backups on2026-11-14 |

- Both10 TB filesystems were selected by verified by-id/UUID and mounted with
  `ro,norecovery,nosuid,nodev,noexec,noatime`; no journal replay or fstab changes.
  Both were manual mounts at this checkpoint. The later backup stage configures
  only the retained vault persistently; staging stays manual/read-only.
- `FINAL_SYNC_COMPLETE` selects `finalsync-20261111T204831Z`; its exit is0,
  `COMPLETE` exists, no in-progress marker remains, and all eight staged trees
  and both generations' verification markers are present. Every entry in the
  final recovery `SHA256SUMS` passed, including all four SQL dumps and archives.
  This is checkpoint validation, not another full3 TB source comparison.
- Local restic0.17.3 was recovered from the checksum-verified flash archive.
  With no locks/cache and the vault physically mounted read-only, all11 snapshots
  decrypted and metadata checking passed. Exact migration snapshot `57492bf21849`
  covers all eight trees plus recovery; independent evidence records exit0.
  Three streamed file restores (personal, Paperless, original photo) matched
  staging SHA256. This is not a full repository data scan or a new22 GiB restore.
- Before the separately approved erasure, both8 TB partitions exposed XFS UUID
  `e0d1223d-dc74-4653-a5c7-ef95dd1d8818`. The source disks were identified by
  serial-verified by-id paths, never that ambiguous UUID.

## Approved storage cutover — 2026-11-13

- Operator explicitly approved erasing only `WD-CA2HLH6L`, `WSD1B75J` and
  `K7J5HTSB`, creating the planned pools and restoring bulk data. A guarded
  preflight checked all three identities, sizes, old filesystems, mounts,
  retained read-only copies and empty guest inventory before any erasure.
  Only signatures/partition tables were cleared; no full-disk zeroing.
- Host-specific by-id assignments are persisted. `--tags storage` selects only
  `pve_storage`; syntax/scope checks passed before the live apply. Actual apply
  finished with36 tasks OK,9 changed,0 failed. Pool creation defaults remain off.
- Native `zpool status` shows an ONLINE8+8 TB `tank` mirror and ONLINE4 TB
  `media`, with zero errors; existing SSD `rpool` remains ONLINE. All five
  configured datasets/properties/quotas were applied.
- NFS listens only on `10.77.0.1:2049`, enables only NFSv4.1 and exports only
  photos/files/media to `10.77.0.2/32`. An isolated temporary client namespace
  at that guest identity mounted all three exports read-only and checked real
  bytes, numeric UID/GID99:100 and mode0640. Fixtures/namespace were removed.
  Guest shutdown ordering includes NFS/ZFS; physical shutdown is still untested.
- Durable server-side restore started at00:48:36+04:00, initially copying media.
  Unit: `migration-bulk-restore-20261112t204101z.service`.
  Evidence: `/root/migration-storage-20261112T204101Z`.
  It preserves hardlinks, sparse files, numeric owners, modes, ACLs and xattrs,
  then requires empty full-checksum/metadata/extra-file comparisons for all five
  mappings. Root legacy/collector subtrees are intentionally excluded only from
  their parent files comparison and verified separately. All five copies finished;
  media/files/domains/collector comparisons passed before the outage. Photos
  passed after the verification-only continuation below.
  The SSH observer previously disconnected; the independent worker kept running.
- During a utility outage, the operator reported5–10 minutes UPS reserve.
  `upsc` was absent and NUT/apcupsd services were inactive: automatic UPS shutdown
  was not protecting PVE. The final photo check was stopped, interruption evidence
  saved as `power-outage-interruption.json`, all three pools explicitly synced,
  and `systemctl poweroff` returned0 with the request accepted. Physical power-off
  was not independently observed; no VM/CT was present. Do not restart on battery.
- After power returned, the rebooted host auto-imported all three pools ONLINE
  with identical GUIDs and zero errors; private `vmbr1` persisted and no guests
  appeared. Both10 TB disks retained their serials/UUIDs and were remounted with
  `ro,norecovery,nosuid,nodev,noexec,noatime`. Four previous proofs remain intact.
- UPS-only activation exposed a fresh-install USB permission failure: the
  attached0764:0501 node was root:root and the NUT driver could not open it.
  The role now reloads packaged udev rules and reapplies them only to the
  configured UPS IDs before starting services; the node is now root:nut.
  `--tags ups` excludes storage, GPU, guests and backup roles.
- Real UT1050EG telemetry reported `OL CHRG`,73% charge and1146 seconds estimated
  runtime. Driver/server/monitor are enabled and active; upsd binds only to
  `127.0.0.1:3493`. Policy:25% charge,600-second runtime reserve,600 seconds
  maximum on battery. The scheduler identity successfully signalled the real
  monitor using a harmless reload, not FSD.
- The actual NUT scheduler, running as `nut` with isolated accelerated config,
  invoked its synthetic timeout action and cancelled it on ONLINE; fixtures
  were removed. Those initial checks did not trigger production shutdown.
  The later physical host-level test is recorded below.
- Photo-only verification resumed at14:49:28+04:00 under
  `migration-photo-verify-20261113t104905z.service`, using
  `resume-photo-verification.py` in the existing evidence directory. It completed
  at23:06:09+04:00 with service/restore exit0, no data recopy or pool recreation.
  `RESTORE_COMPLETE`, `restore-status.json` and all five `*.verified` markers
  agree: every mapping passed a full checksum/metadata comparison with empty
  extra-file-aware difference reports. Final `zpool status` shows all three
  pools ONLINE with zero read/write/checksum errors; both10 TB filesystems remain
  read-only. Guest inventory is still empty. This proves bulk restoration, not
  guest appdata/database restoration or application startup.
- The SSD and both10 TB filesystems were preserved through bulk restoration.
  No guest, backup timer or application startup occurred. After source erasure,
  rollback means restoring from staging/retained restic, not booting the original
  array unchanged. Keep both copies and the Unraid USB.

## GPU hardware cutover — 2026-11-13

- GPU-only syntax/scope and live guards passed: GTX1650 functions `01:00.0`
  (`10de:1f82`) and `01:00.1` (`10de:10fa`) share group1 only with bridge
  `00:01.0` (class0604). ASPEED `05:00.0` is boot VGA in group12.
- `--tags gpu` applied only the guarded GPU role:16 tasks OK,5 changed,0 failed.
  Both EFI boot arguments and initramfs were refreshed; no host-console driver
  blacklist, ACS override, storage creation or guest provisioning was applied.
- A controlled reboot returned in91 seconds. Both GTX1650 functions now use
  `vfio-pci`; ASPEED remains `ast`/boot VGA and the bridge remains `pcieport`.
  The active command line includes `intel_iommu=on iommu=pt`.
- All pools auto-imported ONLINE with unchanged GUIDs and zero errors. Private
  bridge/NFS exports and enabled NUT driver/server/monitor persisted; UPS was OL,
  100% charged. The two manual10 TB mounts were initially unmounted after this
  reboot and remounted read-only after the physical UPS test.
- Recovery/evidence: `/root/migration-hardware-20261113T191056Z`, including
  `gpu-boot.before.tar`, actual role/reboot output and before/after PCI bindings.
  GPU bindings and ASPEED console survived the subsequent real UPS power cycle.

## Physical UPS host test — 2026-11-13

- Operator requested a shorter full test. Only the maximum on-battery timeout
  was temporarily set to120 seconds using `pve_ups_onbattery_timeout_seconds`;
  production default stays600, charge/runtime reserves stayed25%/600 seconds.
- Operator physically removed UPS input mains. Real NUT recorded ONBATT at
  23:28:55.846+04:00 and automatic timer/FSD at23:30:56.262—120.4 seconds later.
  No synthetic FSD or manual host shutdown was injected.
- Previous-boot journal proves orderly shutdown: `pve-guests` stopped at
  23:31:04.602, before NFS at23:31:04.724; ZFS datasets unmounted by23:31:11.510.
  Operator confirmed UPS outputs also switched off and the server started
  after input mains was restored. New boot ID and SSH access were verified.
- Production600-second timeout was restored through the UPS-only role and read
  back from the active scheduler configuration. NUT is active/OL, reserve
  thresholds unchanged, and the powerdown flag is clear. The temporary120-second
  test policy is not left active.
- After recovery: both GPU functions still `vfio-pci`, ASPEED still `ast`/boot VGA,
  all pools ONLINE with identical GUIDs and zero errors, private exports intact.
  Both10 TB backup/staging filesystems were remounted read-only by verified UUID.
  Final evidence: `ups-physical-test.COMPLETE.json` in the hardware directory.
- Limits: no VM/CT existed, so real guest shutdown durations and GPU workloads
  remain unproved. The timer/FSD path was tested, not discharge to low-battery
  reserve thresholds. Guest/application provisioning remains a separate gate.

## VM100 provisioning — 2026-11-14

- Operator authorized only VM creation/boot, not the Docker baseline, appdata
  formatting or workloads. `pve_vm_enabled: true` is persisted for this host.
  `[docker]` was held inactive for that stage; it is enabled for the baseline below.
- The real PVE CLI rejected `pvesm list --output-format json` before mutation.
  Both volume queries now use native
  `/nodes/localhost/storage/local-zfs/content` through `pvesh`; orphan and
  managed-import guards remain enforced. Three focused regression cases cover
  imported-root reuse, orphan refusal and EFI variables not aliasing the OS disk.
- SeaBIOS with the passed-through GTX1650 stalled before any virtual-disk reads.
  Temporarily detaching GPU functions booted the same Debian image successfully.
  OVMF with dedicated EFI variables then booted with both functions restored.
  Existing root/appdata volumes were preserved; no VM/disk recreation.

| VM100 item | Verified state |
| --- | --- |
| OS/firmware | Debian13.7; OVMF/UEFI; q35; dedicated4m EFI vars, pre-enrolled keys off |
| CPU/RAM | 6 vCPUs, host CPU,18 GiB configured |
| Root | `local-zfs:vm-100-disk-0`,160 GiB, ext4 grown on first boot |
| Appdata at provisioning | `local-zfs:vm-100-disk-1`,128 GiB, serial `homelab-appdata`; then blank, initialized in the later baseline |
| EFI variables | `local-zfs:vm-100-disk-2`,1 MiB reported; distinct from both data disks |
| LAN/private NICs | `192.168.15.49/24` DHCP; `10.77.0.2/29`; default route only via LAN |
| GPU | Both `10de:1f82` / `10de:10fa` enumerate inside the guest |

- The published pinned Debian build/checksum matched; the image lacked guest
  agent. Only the already-declared baseline package `qemu-guest-agent` was
  installed early. Real PVE agent ping/network reporting, key-only SSH, sudo,
  DNS/apt and private-host connectivity passed. No Docker/workloads were started.
- Guest SSH fingerprint
  `SHA256:q3E5d0g4brJP0SeTa93cdkQ7ajTItZbv7JF51+apYcs` was matched to trusted
  hypervisor serial-console output before SSH. It is pinned for the guest name,
  LAN and private IPs; strict checking was never bypassed. Temporary pins removed.
  Tailscale was not joined at that checkpoint; the baseline below joins it.
- Real running reconciliation returned `UNCHANGED`. A graceful stop/start with
  both GPU functions attached returned to verified SSH; existing volumes stayed
  attached and appdata stayed blank. Host pools remain ONLINE/zero errors,
  ASPEED remains `ast`, NUT is OL/active, and both10 TB mounts remain read-only.
- Cloud-init completed with no fatal errors but reports recoverable DEPRECATED
  warnings because PVE generates the old string `user` field. This upstream
  schema warning is retained, not suppressed; the pinned cloud-init is25.1.4.
  Guest configuration and restoration were separate later gates; baseline proof
  is recorded below. Workloads/backups were not authorized by that provisioning stage.
- Evidence: `/root/migration-vm100-20261113T195457Z`, including actual apply,
  reversible boot isolation, agent bootstrap, lifecycle and `guest.final.json`.

## Guest baseline — 2026-11-14

- Operator approved guest baseline only. The complete signature-free128 GiB
  device passed the zero-data check before ext4 initialization. Label:
  `HOMELAB_APPDATA`; UUID `1ff46576-74c5-4d71-a664-dc870738d50f`.
  At that baseline checkpoint appdata contained only `lost+found`; restoration follows below.
- PVE exposes the device-ID alias `scsi-0QEMU_QEMU_HARDDISK_drive-scsi1`,
  not a by-id alias derived from serial `homelab-appdata`. Serial checks remain
  independent. Real reboots reordered `/dev/sdX`; the corrected alias stayed valid.
- All three NFSv4.1 mounts use private source `10.77.0.1` and client `10.77.0.2`.
  Actual bidirectional file I/O and numeric-owner/mode checks passed; probes removed.
  A full rerun exposed redundant mountpoint tasks chowning/chmodding mounted roots.
  Those tasks were removed: the mount module creates missing directories itself.
  Only the three root directory metadata records were restored from read-only
  staging; owners/modes/mtime/ACLs/xattrs match. Child files were not copied or changed.
- Corrected the two obsolete NVIDIA repository URLs. Incomplete binary-name
  pinning caused real dependency conflicts; the vendor's exact-version
  `nvidia-driver-pinning-595.112.07` package replaces that preferences file.
  Installed driver-source packages and APT candidates all remain595.112.07-1.
- Paired kernel/headers `6.12.116+deb13-cloud-amd64`, DKMS and active driver
  595.112.07 passed after two planned guest reboots. GTX1650 reports4096 MiB.
  A real CUDA context allocated1 MiB, wrote GPU memory and byte-verified readback.
  Toolkit1.20.2 discovers the GPU; Docker daemon configuration validates without startup.
- `docker-1.han-diatonic.ts.net` is Running on `100.124.158.33` and
  `fd7a:115c:a1e0::5028:9e22`. Strict controller SSH through MagicDNS passed.
  Accepted subnet routes include `192.168.100.0/24` through `192.168.103.0/24`.
  Operator confirmed that guest key expiry is disabled; the CLI omits expiry fields.
  Real camera/MQTT protocol/authentication remains a workload gate.
- At the baseline checkpoint, Docker29.9.3 / Compose5.7.1 were installed but inactive:
  `ConditionResult=no`, both activation markers absent, all four mount requirements
  present. No Compose deployment or application startup had occurred.
  DNS port53 is free; security updates stay enabled, automatic reboots stay disabled.
- Post-reboot mounts/fstab, guest agent and LAN-only default route passed.
  Host pool GUIDs/health, VFIO/ASPEED ownership, OL UPS and both read-only10 TB
  mounts were preserved. GPU memory proof is not Immich/TensorRT/NVENC application proof.
- The complete baseline rerun through strict tailnet SSH passed:
  `ok=74 changed=0 unreachable=0 failed=0`. A subsequent root-only metadata
  comparison found no differences; guest NFS roots retained `99:100` / `0777`.
  Both activation markers remained absent and Docker remained inactive.
- Evidence: `/root/migration-guest-baseline-20261113T203354Z`.

## Cold appdata restoration — 2026-11-14

- Operator confirmed guest Tailscale key expiry is disabled and approved the
  cold restore, not production startup. Disk serial/label/UUID, stopped Docker,
  absent startup markers and both read-only10 TB mounts passed live preflight.
- Direct PVE → VM transfer used private `10.77.0.0/29` and
  `rsync -aHAXS --numeric-ids`:296,184 entries,49,074,347,029 logical bytes,
  zero deletions. Numeric ownership, sparse files, ACLs, xattrs and mtime were
  preserved. The restored root matches staging `99:100` / `0777` and exact mtime.
- The initial controller-mediated tar stream was superseded without discarding
  completed files. Tar skips filesystem sockets; the installed restricted-rsync
  writer also prevents special-file creation. A temporary source-IP-restricted
  key therefore ran one fixed rsync receiver command targeting appdata only;
  the system restriction helper was not changed.
- The temporary key then became a confined read-only sender. Full comparison
  passed with exit0 at2026-11-14 07:48:47Z: contents/checksums, metadata,
  hardlinks and extra files all match staging. Independent topology comparison
  also proved all53,540 hardlink groups and8 special files identical.
- An earlier SSH observer reset was not accepted as proof. The successful full
  gate ran locally under a transient PVE systemd unit, with persistent
  stdout/stderr and atomic result; runtime11m27s, empty stderr.
- Temporary guest authorization, private/public key files and copied verifier
  were removed. At that cold checkpoint both startup markers were absent and
  Docker was inactive with `ConditionResult=no`; no production database had opened.
- Both10 TB filesystems remained read-only and pools healthy. The separately
  authorized workload stage below supersedes the stopped/unauthorized state.
- Evidence: `/root/migration-appdata-20261113T212605Z`,
  `RESTORE_VERIFIED.json`, `verification.result.json`, `verification.stdout`,
  `topology.verified.json` and `guest.final.json`.

## Authorized workload startup — 2026-11-14

- Operator approved continuation into production startup. Reviewed all twelve
  production Compose models with real vaulted inputs privately; every bind source
  existed. Existing PostgreSQL clusters, numeric owners and credential contracts
  were retained, not replaced by empty databases or reset passwords.
- Before app writes, PVE created disk-only snapshot
  `pre-workloads-20261114t081708z` of root/appdata/EFI with agent freeze/thaw.
  It excludes NFS datasets and RAM/GPU state; it is local rollback, not independent
  backup. Stop writers and preserve subsequent writes before considering rollback.
- Created root0600 `/mnt/appdata/.homelab-restored` after the cold proof;
  explicit Compose authorization created root0600
  `/etc/docker/homelab-compose-authorized`. Docker now starts with its real
  appdata/NFS mount guards. Both10 TB copies remain read-only/historical.
- Applied one stack at a time with `--tags compose`; baseline packages, driver
  activation/reboots, PBS and backup timers were not selected. Caddy preceded the
  successful Minecraft start. Selected config rendering preserves existing parent
  ownership/modes and avoids mutating unselected stacks.
- Fixed dependency health ordering, Paperless's HTTP origin, closed Vaultwarden
  signup defaults and Homelable's guest CORS/CIDRs. Generated single-file config
  changes now recreate the affected stack; actual changed/unchanged Caddy runs
  proved recreation/no restart and retained canonical HTTPS pack delivery.
- Minecraft initially failed before boot: inherited DNS returned FORMERR for
  the pinned helper's Maven EDNS queries. A refreshed cache was diagnostic, not
  accepted as a fix. Four uncached same-image probes proved Minecraft-only
  Cloudflare DNS; actual deployment then booted healthy. Canonical pack HTTPS/
  host-gateway, source loader/launcher and installer identity remain intact.
- Final state:12 stacks /34 containers running, every configured healthcheck
  healthy, zero restart counters and no OOM-killed containers; about3.25 GiB guest
  memory available at that sample. Root43/158 GiB, appdata41/125 GiB used.
  Host pools are healthy; NUT OL/100%; both retained XFS mounts remain
  `ro,norecovery,nosuid,nodev,noexec,noatime`.

| Application | Actual retained state and runtime proof |
| --- | --- |
| Immich | 216,905 assets,12 albums,3 users; existing original readable; ping/UI and real ML inference passed |
| Paperless | 86 documents,16 tags,3 users; original PostgreSQL18 cluster and login UI |
| Vaultwarden | 597 ciphers,2 users,1 organization; SQLite quick check/API/login UI; signup closed |
| Homelable | 2 designs,29 nodes/29 edges,142 inventory rows,3 documents; backend health and signin UI |
| LiteLLM | 2 models,8 virtual keys,357 spend logs; authenticated APIs and one bounded real completion |
| Order-manager | 3 orders,2 customers,5 order lines,4 media files; native health and Telegram landing UI |
| Arr/qBittorrent | Existing series/movies/indexers/queues and10 torrents; root/save paths exist; real torrent/media hardlink retained |
| Jellyfin | 2,764 library items; authenticated native1 MiB range stream matched restored media exactly |
| Obsidian | Authenticated CouchDB:6,132 documents; publisher regenerated site; canonical TLS served exact generated index |
| Minecraft | Original seed matches native RCON;660 overworld regions,2 player files; canonical pack and rendered BlueMap |
| Frigate | Four real640×360 JPEG decodes at about5 fps; protected API401 and login UI; viewer-only preserved |
| DNS/Caddy | Real TCP/UDP DNS answers and console UI; native Caddy validation/canonical HTTPS; admin routes blocked |

- Real Immich CLIP inference produced512 finite normalized floats with CUDA
  provider/GPU-process attribution. It overlapped a bounded Jellyfin-bundled
  `hevc_cuvid` → `scale_cuda` → `h264_nvenc` job on real4K10-bit media:
  480 frames encoded, exit0. Sampled GPU peak940 MiB, minimum2776 MiB free;
  no new Xid/OOM matches. This is not peak-load, owner playback or HDR-quality
  proof. Jellyfin acceleration preferences remain `none`; Frigate detection,
  recording and snapshots remain off.
- All31 source-mapped binary config digests match after resolving modern OCI
  index/amd64-manifest IDs; order-manager's old project-name aliases are explicit.
  Homelable's three repository-pinned images are unchanged, but no counterpart
  containers exist in retained source inspect, so source-binary parity is unproved
  for those three. No application/database-major upgrades were made.
- Concrete external blocker: `192.168.100.30:1883` times out; same-site NVR
  `192.168.100.40:554` works through Tailscale. MQTT remains enabled, not disabled
  to hide the failure. Legacy HAOS was not revived.
- Owner-password/2FA/Telegram/LiveSync client sign-ins and visual playback quality
  remain manual acceptance checks; no credentials were reset or new tokens
  created. Private render/SQLite review copies and the inspection browser were
  removed after checks. No edge/LAN DNS/router changes or backup timers activated.
- Evidence: `/root/migration-workloads-20261114T081708Z`, including per-stack
  `*.verified.json`, `jellyfin.native-stream.json`, GPU proof,
  `minecraft.bootstrap-resolution.json`, `caddy.reconcile-verified.json` and
  `workloads.final-{guest,host}.json`.

## Guest shutdown and restart — 2026-11-14

VM100 was stopped through the real PVE/QEMU-agent path with `--forceStop 0`,
then restarted by a durable host worker. The host and NFS server stayed online;
no FSD, shortened UPS timeout or physical power interruption was injected.

| Cycle | VM shutdown | PVE start command | Container result |
| --- | --- | --- | --- |
| Initial | 36.654s | 8.328s | qbit_manage exceeded its default10s and exited137; four PostgreSQL and Minecraft exited0 |
| Corrected | 35.676s | 8.307s | All34 exit events recorded; no SIGKILL/137; qbit_manage, Minecraft and all four PostgreSQL exited0 |

- The pinned qbit_manage4.13.0 handler sets a flag which its30-second sleep
  delays observing. A60-second budget alone allowed exit0 in21.788s; the
  persisted Compose setting then passed the second complete VM lifecycle.
  No application image, stop signal or schedule changed.
- Guest journal proves Docker stopped before all four appdata/NFS unmounts.
  New boot IDs and strict SSH reconnect passed. PVE start-command duration is
  not full application recovery time.
- All34 containers returned running, configured healthchecks healthy and
  restart counters0. PostgreSQL logs show clean shutdown/startup, not interrupted
  recovery. Existing Immich216,905 assets, Paperless86 documents and Vaultwarden
  597 ciphers remain; real four-camera JPEG decode, GPU enumeration and Minecraft
  RCON passed after both boots. Stable appdata identity survived `/dev/sdX` reorder.
- Order-manager's application exited1 during the second shutdown with a
  database-disconnection error while Docker stopped services concurrently;
  its PostgreSQL exited0 and the recovered application health returned200.
  This is recorded, not described as every application exiting0. Backup's
  separate writer-before-database protocol remains required.
- This closes measured guest stop/restart, not the full physical UPS test with
  VM100 populated or low-battery reserve triggering. Those remain unproved.
- Backup preflight found activation blockers before deployment: native PVE
  deletes a prewritten PBS token file on storage add without `--password`;
  provisioning lacked an automatic-schedules-off mode. Staging was coupled to
  timers and a directory task touched the mounted vault root. These are now
  corrected. Native disabled-registration/write ordering passed; a further
  native failure showed `server`/`datastore` are immutable on update, so only
  mutable fields are reconciled. Saved identity and TLS-pinned storage now work.
- A separate native16 MiB ZFS fixture disproved the review's generic-filesystem
  mount-identity warning: a whole ZFS snapshot bind reports `dataset@snapshot`,
  matching the existing recovery guard. The fixture was removed; no production
  dataset/snapshot was changed for that probe.
- Evidence: `/root/migration-lifecycle-20261114T104107Z`, including
  `first-cycle.result.json`, final `result.json`, both stop-event records,
  `qbit-stop-budget-probe.json`, `guest.corrected-postboot.json`,
  `guest.final.json` and `native-zfs-bind-probe.json`.

## Current backups and isolated recovery — 2026-11-14

- PBS image `vm/100/2026-11-14T12:12:35Z` completed in8m47s, including root,
  appdata and EFI. Actual isolated VM900 restoration took about5m20s; Debian13
  booted with real ext4 appdata. Vaultwarden597 ciphers/SQLite `quick_check=ok`,
  PostgreSQL18 cluster files and the Minecraft world were recovered.
  NICs stayed down, GPU absent, Docker/Tailscale masked. Expected network/GPU
  failures mean this was not a complete application/client recovery.
  VM900 and all four owned volumes were removed after proof.
- The first restic checkpoint failed before scanning because a single ZFS
  snapshot call spanned `rpool` and `tank`. The original workloads resumed.
  Disposable native datasets reproduced the exact error and proved separate
  calls. The corrected real checkpoint produced matching read-only snapshots
  on appdata staging, photos and files before resuming applications.
- Restic point `f83a130ac874` protects four cold-copy SQL dumps, Vaultwarden and
  guest recovery configuration. Actual `restore --verify`, SHA256 and SQLite
  checks passed; all11 historical snapshots remain. Four isolated same-image
  PostgreSQL imports matched all230 dumped tables. Fixtures were removed.
  This smaller point precedes the completed full current checkpoint below.
- Full restic checkpoint `e752f5a4a909` completed at16:12:51 UTC, exit0.
  It processed884,393 files /1.943 TiB; collection and metadata checks passed.
  Actual photo/PDF restoration matched bytes, owner/group, mode, nanosecond mtime
  and xattrs. All11 historical snapshots remain among13 total.
  Temporary restored files were removed. All34 workloads remained healthy,
  no OOM and no stopped-container manifest after completion.
  This does not establish full repository pack-data integrity or off-site protection.
- Router pins had matched LAN Dropbear, not Tailscale SSH. Advertised keys of
  independently authenticated named peers matched the presented keys; strict
  collector-identity SSH passed. Only three vaulted public pins changed.
- The corrected checkpoint returned all34 workloads healthy, with no SIGKILL/137
  and clean PostgreSQL exits. Homelable frontend had two DNS-related startup
  exits during resume; its runtime-resolving Nginx template now handles absent
  or changed backend addresses without restarting. Same-image isolated proof,
  live proxied API and rendered sign-in UI passed; production images unchanged.
- PVE/PBS automatic jobs, PBS GC and host timers remain disabled/unscheduled.
  Keep retained staging read-only; the existing vault is deliberately read-write.
  Review host/PBS timezone and observed durations before arming schedules.
- Evidence: `/root/migration-backups-20261114T120556Z`, including
  `pbs.first-image.json`, `vm900-recovery.json`, `zfs-crosspool-contract.json`,
  `proof-backup.result.json`, `sql-recovery.result.json`,
  `checkpoint.second-views.json` and `homelable-dns-production-proof.json`.

## Populated UPS recovery and public ingress — 2026-11-14

- The real production600-second UPS timer shut down the populated host.
  VM100 stopped in36.139s before NFS; all34 original container exits were recorded,
  without SIGKILL/137. The operator observed UPS outputs off and automatic
  server startup after restoring only UPS input mains. Low-battery reserve
  discharge was not tested.
- Original workloads/data, NFS photo/PDF hashes, pool identities and GPU memory
  readback passed after recovery. The retained vault auto-mounted read-write;
  manual staging remained unmounted. No disk was initialized.
- PBS proxy boot failed because its volatile runtime directory belonged to root.
  The role now recreates it with tmpfiles as guest `backup:backup`0755.
  A separate CT reboot, pinned API, retained backup listing and rendered sign-in
  UI passed. Automatic backup/PBS schedules remain off.
- Evidence: `/root/migration-ups-populated-20261114T174036Z`,
  especially `ups-physical-populated.COMPLETE.json`.
- The owner assigned `tag:home` to the exact original Docker VM node.
  Live edge TCP443/25565 and uniquely identified UDP24454 delivery passed;
  TCP22/80/8006/8007 timed out as required. No policy change was needed.
- The approved edge time repair installed/enabled `systemd-timesyncd` through
  only two `time_sync` tasks, without a distribution upgrade. Native NTP state
  is synchronized, with actual UTC within one second of the controller.
- The owner explicitly accepted automated availability instead of personal
  client sign-ins/playback as this cutover gate. Those manual checks and HDR
  quality remain unverified; no client hosts file was edited.
- The checkpointed `--tags proxy` publication changed only the generated stream
  configuration and reloaded nginx. Main nginx configuration was unchanged.
  Home Assistant routing, listener/protocol set, public DNS, router and Tailscale
  policy were not changed.
- All seven public HTTPS names passed trusted-certificate checks: six HTTP200,
  and expected HTTP401 for protected notes. Vaultwarden `/admin` returned403.
  Immich and Vaultwarden sign-in pages actually rendered in an owned browser;
  no credentials were entered.
- A real public Minecraft status handshake returned version26.1.2. A uniquely
  identified public UDP24454 datagram traversed VPS nginx and arrived on VM100.
  Public TCP8006/8007/5380/4743/8096 were unreachable.
- Pre-publication source checkpoint: `1350b31` on
  `migration/pve-cutover-20261114`, not pushed. Unrelated workstation/keyd/wireless
  changes were excluded. Private routing stays outside Git.
- Evidence: `/root/migration-ingress-20261114T164316Z`,
  `checkpoint.before-publication.json`, `backend-ready.json` and
  `public-cutover.COMPLETE.json`; original edge configuration is retained there.
  Local `home.arpa` was still stale at that ingress checkpoint; the next phase
  below implements the owner's temporary manual-client DNS decision.

## Backup automation and manual-client DNS — 2026-11-15

- Persistent inventory enables PBS provisioning/schedules and four host backup
  timers. Source was first reconciled with explicit off overrides, then armed.
  Host and CT use Asia/Yerevan; maintenance windows avoid the measured restic scan.
  All four timers were enabled/waiting with future NEXT and inactive services
  at activation; native PBS maintenance next runs were also future.
- PVE disables missed-image catch-up and leaves retention to PBS. A native dry-run
  proved all eleven legacy snapshots remain outside automatic restic retention.
  Vault/quota headroom was checked, and the actual notification helper returned
  HTTP200/message ID using isolated state. No production success marker was forged.
- The first scheduled nightly PBS/restic run has not yet been observed. Existing
  full manual backups/restores remain established; no extra long scan was started.
- Router credentials were unavailable. The owner explicitly accepted current
  DHCP `.49` plus manual DNS on selected PCs; no reservation or whole-LAN fix is
  claimed. `home.arpa` now uses Docker A/wildcard CNAME and correct NS/SOA metadata;
  old explicit Unraid A was removed, unrelated `lab` stayed unchanged.
- Five names passed direct UDP/TCP. Actual client getent and ordinary Jellyfin
  HTTP reached `.49`/HTTP200 without overrides after flushing resolver cache.
  Browser navigation remained client-blocked; sign-in/playback were not tested.
  Router `.1` still lacks the local zone; use only VM DNS on intended clients.
- Existing password was used only through encrypted SSH transport and not changed.
  Temporary admin session, secret file and tunnel were cleaned up. Public ingress,
  Tailscale policy, router configuration and client hosts/profiles were untouched.
- Evidence: `/root/migration-automation-20261114T195553Z`,
  `backup-automation.COMPLETE.json`, `notification.acceptance.json`,
  `local-dns.COMPLETE.json` and `owner-scope-and-verification-limits.json`.

## Verification performed

- Nine Ansible entrypoints passed syntax checking and existing proxy behaviour gates.
- All13 Compose definitions passed the real Compose parser using synthetic vault
  values;21 vaulted references exist; no plaintext Compose `.env` is present.
- Twelve offline unittest cases passed, covering silent checksum mismatches, extra/missing
  files, hardlink/symlink preservation and failed-resume marker retention.
- Thirty runtime/config templates rendered; Python and shell runtime syntax
  checked. Rendered shell scripts passed focused shellcheck.
- The actual pinned Caddy binary validated the rendered ingress configuration in
  an isolated networkless container with synthetic credentials.
- Actual restic0.17.3 exercised repository copy, local/secondary full data checking,
  byte-verified restore and unchanged history after wrong-disk/missing-mount
  refusals. Privileged filesystem probes were simulated; no real pools were used.
- The guest helper stopped/resumed isolated real Docker containers, produced an
  actual PostgreSQL18 dump, and resumed the original set after an injected dump
  failure. The dump imported into a separate cluster and preserved the fixture row.
- An injected host checkpoint failure resumed actual containers and did not scan
  data into restic. VM fresh/rerun/partial-import and refusal paths were exercised
  against stateful PVE command fixtures, not a real hypervisor.
- A real Compose container preserved synthetic Argon2 dollar/braces/quote/
  backslash values unchanged, beyond the configuration parser checks.
- Focused local proof selected only the four bootstrap roles; a VM-only Ansible
  invocation with the default gate skipped all provisioning. Native-store writes
  were subsequently verified on real PVE pmxcfs, preserving link/ownership/mode
  and existing keys; regular0600 key creation and both reruns were idempotent.
  PBS template rendering/Python compilation and isolated token persistence/
  recovery cases passed without deploying PBS in those fixtures; current native
  provisioning and restoration are recorded above.
- Actual tailnet bootstrap, management filtering and an85-second controlled
  reboot passed. The new kernel, Tailscale identity, key-based SSH, web endpoint,
  dual-family rules, LAN denial and private bridge persisted. At that reboot,
  no guests or HDDs were present; HDDs were reconnected and checked subsequently.

Remaining unproved: personal sign-ins/playback/HDR quality, peak production
load and low-battery reserve triggering.
External MQTT remains unavailable. Full current PBS/restic backup and bounded
OS/file/SQL restoration, populated timer-driven UPS recovery and public ingress passed.

## Remaining gates and deferred decisions

1. Bulk/appdata restore, guest baseline and controlled workload startup passed.
   Preserve SSD, both10 TB copies, old restic history and Unraid flash. Applications
   now write new state: never blindly restore historical staging over live data.
2. The owner accepted availability-only validation for this cutover. Personal
   sign-ins/playback/HDR checks are deferred by that decision. External MQTT
   remains unavailable; do not reset credentials, enable camera recording/detection
   or change Jellyfin HWA as a migration shortcut.
3. Populated physical UPS shutdown and automatic power-return recovery passed;
   low-battery reserve discharge remains unproved.
   PBS, retained-vault guards and isolated OS/file/SQL recovery are established;
   the full current restic checkpoint and bounded bulk restore also passed.
   Router changes remain deferred; review the
   accepted `192.168.103.0/24` tailnet route before moving the LAN into that subnet.
4. Automatic schedules are armed after recovery proof. Observe the first real
   nightly PBS/restic result and ongoing freshness/capacity alerts; do not treat
   future NEXT timestamps as successful backup execution.
5. Public ingress and temporary manual-client local DNS passed. A stable VM
   reservation and ordinary LAN DHCP/forwarding remain deferred to router access;
   keep management private and do not point applications back at PVE.
6. Remove Unraid automation only after a complete new backup and restore cycle.
   Preserve the migrated collector. Commit reviewed repository changes before cutover.

Later choices: second SATA SSD mirror;64 GiB ECC replacing non-ECC DIMMs if needed;
router replacement/dnsmasq; object storage or another rotating off-site disk;
Gatus and optional metrics. Gatus needs URL/error redaction, authenticated push
producer migration and a genuinely separate public instance—not a filtered view
as an authorization boundary. Keep monitoring outside the home failure domain.

## Local checks

```bash
python tests/check_ansible.py
python tests/check_compose.py
python -m unittest discover -s tests -p 'test_*.py'
npx --yes markdownlint-cli2@0.23.3 '*.md' 'docs/**/*.md' 'files/**/*.md' '.github/**/*.md'
```

Review in order: migration → host → Docker → backups → actual role variables
and scripts. Verification limits are part of the status, not implied passes.
