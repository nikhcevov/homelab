# Proxmox backups

[Repository overview](../README.md)

Sources of truth: [PBS role](../roles/pve_pbs/),
[file backup/collector role](../roles/pve_backup/),
[legacy guest-helper retirement](../roles/docker_backup/),
[PBS inventory](../inventory/group_vars/pve/pbs.yml),
[collector inventory](../inventory/group_vars/pve/backup.yml),
[collector age policy](../roles/pve_backup/defaults/main.yml),
[VM disks](../inventory/group_vars/pve/vm.yml) and
[guest mounts](../inventory/group_vars/docker/docker_vm.yml).
See also the [historical migration gates](archive/proxmox-migration.md#migration-plan)
and [dated backup cutover evidence](archive/backup-cutover.md).

**Temporary B-only protection accepted on2026-11-19.** Full VM/filesystem recovery
and natural HDD standby/real-backup wake passed; A's hardware path remains untrusted.
The owner approved B as the temporary sole active PBS datastore, with A offline.
Native VM/file backup, freshness and PBS maintenance schedules are now enabled.
This is one active local repository, not dual-copy or off-site protection.
Restic histories and original datasets remain preserved; follow
[current acceptance evidence](status.md). Dated prior workflows are preserved in
[backup cutover history](archive/backup-cutover.md), not pending operational stages.

## Ownership and coverage

| Mechanism | Approved coverage | Limits |
| --- | --- | --- |
| Native snapshot-mode VM100 backup to vault-b | OS/EFI, Docker/appdata, managed photos and files disks | Not host/PBS bootstrap, VM102 or external media |
| Small PBS `host/pve-recovery` backup | PVE/PBS recovery configuration and remote VPS/HA/router collector | Independent source generations, not one transaction with VM100 |
| Optional native secondary sync | Disabled; no healthy secondary configured | No current second active repository or off-site copy |
| Original datasets, legacy PBS/Restic histories | Preserved rollback/recovery evidence during migration | Not proof of current PBS-only coverage |

VM102's image is outside this VM100 job; its source-managed gateway rebuild is
documented in [OpenWrt day-0](openwrt.md#gateway-vm-router-gw).

The active collector policy currently covers VPN/HA and router-srt/router-krm.
The owner temporarily excluded offline router-trvl/planned router-evn; its old
archives remain preserved and are not current protection. Re-enable it only
after the intended device is reachable and its SSH identity is verified.

VM root160 GiB and appdata128 GiB remain on SSD-backed `local-zfs`. Photos
3072 GiB (`scsi2`, serial `homelab-photos`) and files64 GiB (`scsi3`,
`homelab-files`) are managed sparse volumes on the existing HDD ZFS mirror via
`tank-vm`. Guest ext4 labels are `HOMELAB_PHOTOS`/`HOMELAB_FILES`; paths stay
`/mnt/photos` and `/mnt/files`. Both are enabled for native image backup.
The guest guard checks the actual device, serial, size, filesystem, label and
mount; neither an empty directory nor a stale NFS view may substitute for a disk.

Replaceable media `/mnt/data` remains actual host NFS (`/media/data`) and is
outside the VM image. A full running stack still requires that real mount.
Do not create an empty fallback to make Compose pass; compose-only applies also
run the local disk/mount guard before mutation.

The two existing10 TB XFS disks are not a mirror and are never reformatted:

| Store | Participation | Host directory → CT101 directory | Existing filesystem UUID |
| --- | --- | --- | --- |
| vault-a | Inactive/offline after recurring errors | `/mnt/vault/pbs` → `/mnt/datastore/vault-a` | `6d3f33cb-faaf-4497-8131-2f40f07cfbbd` |
| vault-b | Accepted temporary sole active primary | `/mnt/backup-b/pbs` → `/mnt/datastore/vault-b` | `d0347cdb-9c3b-41e8-88ce-498367a6f038` |

Use only each disk's `pbs` subdirectory; preserve `/mnt/vault/restic` and all
other migration trees on B. Datastore binds are excluded from CT backups.
Unprivileged CT backup UID/GID34 maps to host100034. Only an empty datastore
root may receive that ownership automatically; never recursively chown history.
The mount guard rejects wrong UUID/filesystem, read-only mounts, `noatime`,
symlink redirection and root-filesystem fallback. PBS GC needs access-time updates.

`pve_pbs_datastores` retains each identity and stable `mount_index`, with explicit
`enabled` participation. Only B is enabled; selected primary must be enabled.
Inactive A and legacy tank remain offline recovery assets, not CT startup,
mount-guard, maintenance or HDD-policy dependencies. Exact managed binds are
retired without deleting datastore configuration or contents; foreign bind
identities refuse reconciliation. Slots remain legacy0, A1, B2.

With `pve_pbs_secondary_datastore` empty, no sync runs and no replica success is
published. A future healthy enabled secondary can use native root-namespace
local pull with owner `pve@pbs!pve` and `remove-vanished=false`, after independent
recovery proof. PVE uses `keep-all=1`; server-owned prune/GC/verification owns
retention, not the backup token. A later remote PBS is separate work; the current
single local repository does not protect against loss of the host/site.

### Retained legacy repository

The old XFS repository `/mnt/vault/restic` and `vault_restic_password` remain
recovery assets, not the destination of the new recurring pipeline. Preserve an
offline password/vault-unlock copy; backing up a password inside its own encrypted
repository cannot bootstrap recovery. Historical automatic Restic retention used
host `pve-backup` plus tag `pve-owned`; do not run that retired retention workflow
or broaden it to Unraid/migration points. Never initialize, forget or prune the
retained repository as part of recovery. Dated snapshot IDs, refresh measurements
and restore results are in [cutover history](archive/backup-cutover.md#retained-legacy-repository)
and the [pre-cutover refresh](archive/proxmox-migration.md#independent-pre-cutover-vault-refresh).

For read-only legacy recovery, identify the original disk by UUID before accessing
`/mnt/vault/restic`; A is quarantined, so do not attach/use it automatically.
Prefer an independently validated preserved copy. On an authorized recovery host,
use a trusted compatible Restic binary and a protected offline password file
(the historical Unraid location was `/boot/config/restic/password`, master secret
`vault_restic_password`). Keep source repository and restore destination distinct:

```bash
export RESTIC_REPOSITORY=/VERIFIED_EXISTING_COPY/restic
export RESTIC_PASSWORD_FILE=/PROTECTED_OFFLINE_PASSWORD_FILE
restic --no-lock snapshots
restic --no-lock ls EXACT_SNAPSHOT_ID
restic --no-lock restore EXACT_SNAPSHOT_ID --verify --target /EMPTY_ISOLATED_RECOVERY_DIRECTORY
```

Use a read-only source mount, inspect the exact point's paths first (old snapshots
use `/mnt/user/`, migration refresh uses `/mnt/staging/`) and restore into a new
root-only destination, never over live applications or the source repository.
Check recovered bytes/metadata and replay SQL only in isolated compatible images.
Immich thumbnails/transcodes were excluded from routine legacy coverage; regenerate
them after recovery. See [historical Unraid recovery](archive/backups-unraid.md#local-weekly-copy--vault-pool-restic)
for retained paths and [application restore guides](archive/backups-unraid.md) for
VPS, HA encryption-key and router recovery facts. Do not redeploy retired scripts.

## Consistency protocol

1. PVE's native `homelab-vm100-pbs` job uses **snapshot** mode against
   `pbs-vault-b`, with the enabled/running QEMU Guest Agent freezing/thawing local
   filesystems. Recovery is crash-consistent, not a clean application shutdown;
   databases must replay their journals/WAL. This preserves QEMU dirty bitmaps
   between backups and avoids nightly VM/GPU restarts. Stopping the VM loses
   those bitmaps and requires rereading its data even when little changes.
   Recurring jobs do not stop containers, cold-rsync appdata, dump SQL or
   choreograph ZFS snapshots. Cold cutover proofs are historical only.
2. After upstream archive generation, the host coordinator collects remote
   archives over the existing strictly pinned SSH identity into the root-only
   ZFS dataset `/rpool/backup-staging/collector`. On a rebuild, recover its existing
   history before enabling collection. The collector requires the exact mounted
   writable dataset, not a fallback directory.
3. Each archive source must have a matching completed regular non-symlink file,
   nonempty, not future-dated and at most24h old. Successful rsync or a fresh
   unrelated file is insufficient. Router backups are generated during collection
   and must be nonempty valid gzip archives.
4. The coordinator takes a consistent SQLite backup of pmxcfs, packages
   `pve-config.tar.gz` (including the canonical PBS token) and
   `pbs-config.tar.gz` (`/etc/proxmox-backup`), validates gzip, then sends
   `recovery.pxar` and `collector.pxar` to PBS as `host/pve-recovery`.
   Rendered guest configuration is protected inside the VM's OS/appdata image.
5. The [PBS proof helper](../roles/pve_backup/templates/pbs-file-backup.py.j2)
   requires the exact newly completed host point and both pxar indexes before
   atomically fsyncing its receipt. It then requires the current-night successful
   native VM task and its matching point, including OS/appdata/EFI **and both
   managed bulk image indexes**. Yesterday's success or a config blob alone fails.
6. `complete-cycle` waits for a running current VM task (up to the configured24h
   limit) and publishes distinct primary-cycle evidence only after both inputs
   pass. This gate is mandatory even without a secondary. If a secondary is
   configured, it then validates/runs native local sync, awaits its exact taskOK
   and proves both same points/all archives there before recording replica
   success. Empty secondary means no sync call or fabricated replica marker.

Schedules use `bootstrap_timezone=Asia/Yerevan` (UTC+04). The role rejects host
timezone drift and reconciles CT local time; CT shares the host kernel clock.

| Job | Local time | UTC |
| --- | --- | --- |
| Native VM100 snapshot-mode backup | daily02:00 | previous day22:00 |
| Upstream HA / VPN generation (observed) | about04:00 /06:30 | 00:00 /02:30 |
| Collect + host pxar + primary-cycle proof | daily07:15 | daily03:15 |
| PBS prune / GC | daily07:00 /08:00 | 03:00 /04:00 |
| PBS verify | Sunday10:00 | Sunday06:00 |
| Host freshness | hourly:30 +0–5min jitter | hourly:30 +0–5min |

VPN's Europe/Amsterdam schedule changes with DST; validate source generation
against collection rather than assuming UTC never changes. At07:15 yesterday's
scheduled04:00/05:00/06:30 files exceed24h and fail, while same-day delayed/manual
collection remains possible. External systems need not share VM transaction time.
PBS retains7 daily,4 weekly,6 monthly points. Maintenance has native locks and can
overlap a long backup; these clocks are not runtime guarantees.

### Receipts, failures and disk standby

Protected root0700 state under `/var/lib/homelab-backup` includes file and primary
receipt/epoch pairs: `pbs-file-latest.json`, `pbs-file-last-success`,
`pbs-primary-latest.json`, `pbs-primary-last-success`. A configured replica also
uses `pbs-sync-latest.json`/`pbs-sync-last-success`. Inspect native task/catalog
evidence too: receipts alone are not restore proof.

Hourly freshness requires matching selected-store file/primary evidence and
age-valid points/completion markers, maximum36h. A configured secondary also
requires matching replica points/store identity. Missing, torn, wrong-store,
invalid/future or old points fail even with a newly touched success timestamp.
Old replica markers are preserved but ignored when no secondary is configured;
they never substitute for current primary protection. File success may precede
a later completion failure. Never forge a receipt to make it green.

The host lock waits up to1h. Missing/wrong mounts, failed source transfer/age,
invalid credentials/TLS pin, missing image indexes, failed VM/sync task or timeout
fail the coordinator and alert; a failed collection stops the file/sync pipeline,
not the separately scheduled VM job. Source failures alert individually.
Inspect service journals, native tasks and protected inputs, repair the cause and
rerun deliberately. Do not delete receipts/manifests, weaken freshness, disable a
source or accept yesterday's VM point to make the run green. Notifications are
state-transition based; failed delivery leaves state unchanged for another attempt.

Native PBS warning/error maintenance delivery is separate from the host helper:
[`homelab-pbs-ntfy` webhook and `homelab-pbs-errors` matcher](../roles/pve_pbs/templates/notifications.py.j2)
route verification/GC/prune warnings and errors to the existing alerts channel.
The channel secret is kept only in root0600 PBS private notification configuration,
never process arguments or logs. Native target delivery has been tested; phone
receipt is not implied by that test.

After backup/recovery acceptance, the
[HDD policy](../roles/pve_pbs/tasks/power.yml) sets ATA timeout244, **120min idle**,
only on enabled declared SATA/XFS10 TB disks after serial/UUID checks; currently B.
Disks stay connected and mounted; this is standby, not physical power-off,
unplugging or forced sleep during active work. Include VM/file backup, sync,
prune, GC and verify in the I/O/wake window, not merely the02:00 VM start.
SMART monitoring respects standby. Observe an actual idle interval and successful
backup/maintenance wake afterward; polling must not itself wake disks.
Accepted natural standby/real-backup wake evidence is linked from [status](status.md);
no disk lifespan improvement is claimed.

## Apply

The commands below are deliberate cutover/reconciliation actions, not permission
to reinitialize existing disks. Current bulk data is local and included in native
VM backups. On a new/rebuilt node, keep schedules and HDD standby disabled
throughout recovery acceptance and require verified parity before final mounts.

### Provision without automatic schedules

1. Confirm original data/history remains intact and no backup/collector/native PBS
   task is active. On a rebuild recover retained configuration and application
   state before enabling schedules. Historical cold writer-pause/legacy transaction
   procedures remain in [cutover history](archive/backup-cutover.md#provision-without-automatic-schedules);
   they are not recurring backup steps.
2. Verify physical identities, free space and existing XFS against
   [PBS inventory](../inventory/group_vars/pve/pbs.yml). Keep A/tank identity
   records with `enabled: false`, B enabled/selected and secondary empty.
   Preserve all non-PBS directories; do not format either disk.
3. Provision/reconcile PBS with schedules and standby off:

   ```bash
   ansible-playbook playbooks/pve.yml --limit great-hornbill --tags pbs \
     -e pve_pbs_enabled=true -e pve_pbs_schedules_enabled=false \
     -e pve_pbs_hdd_standby_enabled=false
   ```

   CT101 is Debian13/PBS4,5 GiB RAM, with host-only private API access from
   `10.77.0.1` to `10.77.0.3`; guest SSH stays masked, administration uses `pct`.
   Preserve management filtering. The runtime tmpfiles rule recreates
   `/run/proxmox-backup` as guest `backup:backup`0755 after reboot; a PID-file
   permission fault is not a reason to recursively chown datastore contents.
4. On a rebuild, restore the managed local photos/files disks and verify their
   serials, filesystems, labels and mounts before starting Docker. Enable both
   disk backups. If migrating new source data, require immutable seed, bounded
   final writer pause and complete byte/metadata proof with
   [verify-tree](../scripts/verify-tree.py); never overwrite newer writes with staging.
5. Create/mount the protected collector dataset and migrate its existing history.
   Prepare the host pipeline with timers off:

   ```bash
   ansible-playbook playbooks/pve.yml --limit great-hornbill --tags backup \
     -e pve_backup_enabled=false
   ```

   The backup role does not create the collector dataset; the storage inventory
   declares it for the `storage` role. Reuse the existing collector identity and
   host pins; bootstrap only missing pins after independent identity
   verification. Never replace a mismatched pin blindly. Do not run the full
   Docker play casually: its guest backup role retires legacy helpers only after
   active transactions and manifests are cleared, preserving old SQL/artifacts.

### Attach the retained vault and run manually

A disk mounted `ro,norecovery` must be verified idle, **unmounted**, then mounted
fresh RW using the declared UUID/fstab policy. Do not remount directly from XFS
`norecovery`. Preserve all migration directories and private restore space;
require XFS, exact
UUID, RW and access-time updates. PBS never authorizes formatting/erasing history.

With schedules off and the local-data cutover complete, create a reviewed native
`vzdump 100 --storage pbs-vault-b --mode snapshot` acceptance point. Prove actual
guest-agent freeze/thaw and recovery. Any one-time writer pause for matching
logical SQL references must end after the snapshot boundary, not after the
hours-long bulk transfer; it is not recurring backup choreography.
Run `systemctl start homelab-backup.service` only after fresh upstream archives
and B readiness, in the same scheduled cycle as a completed VM task. If a long
initial transfer crosses02:00, take a new native delta in the new cycle before
completion proof. Native catalog verification and actual B recovery are required.

### Arm only after recovery proof

Review `homelab-backup.timer` and `homelab-backup-freshness.timer` stamps,
`Persistent=true`, service inactivity and future NEXT times **before** activation.
The old separate collector/check timers are removed; the07:15 service collects
itself. Existing stamps can cause immediate catch-up on enable/boot. For a
deliberate discard of catch-up, stop/disable the timer, ensure its service is
inactive and clean only that timer's systemd state, never backup receipts.
PVE uses `repeat-missed=0`; PBS maintenance next-run state is independent.

After the recovery gates pass, retire only the legacy guest backup automation:

```bash
ansible-playbook playbooks/docker.yml --limit docker-1 --tags backup
```

The `backup` tag selects the guarded `docker_backup` retirement role, not Compose,
networking or the rest of the guest baseline. Pending old transactions still
refuse removal; existing SQL dumps and backup artifacts remain untouched.

After full B VM/archive and filesystem recovery proof, preserved histories and
readiness review, reconcile `pve_pbs_backup_mode=snapshot`, schedules and
`pve_backup_enabled=true` through inventory/scoped `pbs`/`backup` applies.
Extra-vars do not persist; inventory controls subsequent reconciliation.
Inactive A/tank remain offline with no CT bind/start dependency; their data is
not deleted. Enable B standby only after those gates and observe real sleep/wake
including maintenance. Record evidence before describing this temporary
single-repository setup as accepted; never describe it as two-copy protection.

Historical capacity measurements, prior timer activation and first scheduled-night
Restic/PBS recovery results are retained in [cutover history](archive/backup-cutover.md#observed-automation-activation--2026-11-15).
Monitor actual B free space/native tasks; do not format, prune history or use the
old 1 TiB tank datastore to manufacture capacity.

## Verify

Use native tools and the deployed PBS-only interface as root for status/freshness
checks (`freshness` can emit alerts and update notification state):

```bash
systemctl list-timers 'homelab-backup*'
systemctl status homelab-backup.service
pvesm status --storage pbs-vault-b
pvesm list pbs-vault-b
pct exec 101 -- proxmox-backup-manager task list --all true
pct exec 101 -- proxmox-backup-manager datastore list
homelab-backup freshness
```

During an approved manual backup window, use the native snapshot-mode VM backup
(`vzdump 100 --storage pbs-vault-b --mode snapshot`), then start
`homelab-backup.service`. Native verification is manually runnable with
`pct exec 101 -- proxmox-backup-manager verify-job run homelab-verify-vault-b`.
Verify completion, not merely launch. `homelab-backup backup` runs the same host
pxar/collection/primary-proof path, plus sync only when a secondary is configured;
it does not start VM backup or replace native verification. The only operator
commands on that wrapper are `backup` and `freshness`; old Restic/offsite/check
commands and resume aliases are not part of the current interface.

Acceptance must establish all of the following:

- Enabled B's exact XFS identity and CT startup guard survive reboot without
  empty fallback; inactive A/tank are not required for appliance startup.
- Native VM taskOK, matching current B point and all five OS/appdata/EFI/photos/files
  image indexes; current B host point with both pxar indexes. A future configured
  secondary additionally needs both exact points/all archives there.
- Recovery/collector archives actually extracted into a protected destination and
  inspected, with fresh matching upstream archives, not only catalog entries.
- Real isolated B VM recovery, current database/application state and
  representative original photo/file bytes plus ownership, modes, timestamps,
  ACLs/xattrs and links. Use frozen references and
  [verify-tree](../scripts/verify-tree.py) for full migration parity.
- Fault handling rejects wrong/missing mounts, stale/empty/future sources, failed
  VM/sync and missing indexes without advancing the corresponding success.
  Use disposable fixtures; do not unplug or corrupt production disks to test.
- Native maintenance alerts, conservative standby and subsequent backup plus
  maintenance wake work, with old histories preserved.

A successful sync, native chunk verify, receipt or bounded sample alone does not
prove usable full-stack recovery. Accepted B recovery/standby evidence and remaining
risks are recorded in [current status](status.md); earlier OS/appdata/Restic and
logical SQL proofs are [historical](archive/backup-cutover.md#observed-migration-recovery--2026-11-14).

## Secondary copy and off-site protection

The owner approved B as the temporary sole active PBS repository after A's
recurring errors followed it to another SATA port. A successful A data restore
does not certify its disk/tray/path. Keep A offline for repair/replacement and
preserve its PBS/Restic history. No second active copy currently exists.

Later, independently prove a healthy secondary before enabling native sync and
claiming dual-copy protection. Preserve that disk's other migration trees and use
no delete propagation. Two local disks still share host/site risk; remote PBS is
separate work after an explicitly reviewed move and recovery test.

Google Drive is **cancelled after account loss**. Do not resume its copy or make
Google API requests without renewed authorization. The partial seed is not usable
backup protection. Credentials, measurements and cancellation evidence remain in
[cloud cutover history](archive/backup-cutover.md#encrypted-cloud-repository).
The former internal Restic-copy workflow is retired; do not initialize repositories
or deploy its old helpers. B is the primary, not a replica.

## Isolated VM restoration

1. Select an exact completed VM point from primary **B**, recording its native
   task, archive list and original VM storage configuration. A is untrusted/offline;
   never automatically restore from A or treat it as an independent recovery copy.
   Use an unused VMID, never overwrite VM100. Preserve **per-storage mappings**:
   root/appdata/EFI originally use `local-zfs`, photos/files use `tank-vm`.
   Do not restore all disks with `--storage local-zfs`: it would redirect the
   multi-TB bulk disks onto the SSD. With original storage IDs available, omit
   the global override; otherwise explicitly map each original storage to a
   correctly sized isolated destination using the installed native restore UI/API.
   Verify supported mapping syntax and free capacity before issuing the restore.
   Sparse provisioning is not a promise that full restored data fits.
2. Restore the selected listed volume with a new identity and leave it stopped,
   for example `qmrestore LISTED_BACKUP_VOLUME UNUSED_VM_ID --unique 1`.
   Before boot, set `onboot=0`, inspect every disk's actual destination and remove
   all physical passthrough/GPU assignments. Never attach a production physical
   disk or GPU to two guests. Do not assume `--unique` isolates storage or services.
3. Budget RAM before starting. This host has32 GiB, production VM18 GiB, PBS5 GiB
   plus host/ZFS demand; do not boot another18 GiB VM concurrently. Prefer
   read-only disk inspection first; boot a reduced-memory clone only with measured
   headroom, or stop production in an approved window for a full-size test.
4. Disconnect NICs or use an isolated bridge, mask Docker/Tailscale until ready
   and suppress external webhooks/bots/game traffic. Original filesystem labels
   and data are expected on the clone; host mount paths and original network
   identities must not be shared accidentally.
5. Check OS, local appdata and database recovery, then representative photo/file
   hashes and metadata against frozen original references. Native VM images
   protect database files; daily snapshot recovery also requires successful
   journal/WAL replay. Logical dump import remains a one-time acceptance check,
   not a recurring dump requirement.
6. A degraded isolated boot is not full-stack proof. The image excludes media
   NFS at `/mnt/data`; provide real appropriately isolated media/NFS for a
   full-stack test. Never point the clone at writable production exports or
   replace an absent mount with an empty directory. Retain the guard's failure.
7. Record datastore, exact snapshot, restore destinations, resource isolation,
   application/data results and recovery time. Remove only marker-identified
   disposable test resources after recording proof; preserve all source histories.

## Single backup-disk failure

Only enabled datastore mounts are mandatory for CT101 startup. In the temporary
B-only configuration, missing A must not block PBS; missing B must fail closed
rather than expose an empty fallback. An offline historical store is not a
current independent copy.

1. Preserve evidence and stop backup/sync/maintenance schedules. Inspect active
   tasks before stopping the CT; do not force standby during I/O.
2. Verify any surviving copy by recorded UUID and existing PBS contents. Never
   format it, substitute an empty directory or recursively change ownership.
3. Retain identity records, disable failed stores, enable/select only the verified
   survivor and clear the secondary. Keep original indices, schedules/standby off.
   Reconciliation retires only exact inactive binds and startup dependencies;
   mismatched foreign binds require operator recovery, not deletion. Preserve
   unavailable store configurations/data offline.
4. Read/restore through the surviving native PBS/PVE storage with pinned TLS and
   authorized identity. Primary-only completion/freshness still require current
   VM/file evidence; no replica receipt is forged. Re-arm only after fresh backup
   and recovery proof for the surviving configuration.
5. Repair/replace the failed copy. Enable a secondary only after native sync and
   its own recovery proof; until then report one active local repository.

## SSD-loss bootstrap

Recover from a host console. CT101 root and host credentials were on the lost SSD;
do not assume either PBS or its normal backup token survived.

1. Obtain independent offline recovery material: repository/vault unlock details,
   trusted PBS certificate fingerprint or authenticated means to establish the
   replacement fingerprint, and host/PBS administrative access. The pxar backups
   hold token/PBS configuration, but requiring that lost token to read the archive
   containing it would be circular. Use local console/root administration to
   bootstrap PBS and grant a controlled recovery identity; no insecure TLS bypass.
2. Reinstall PVE onto the replacement SSD. Restore only reviewed host networking,
   private bridge/filtering and recovery access. Import surviving `tank` without
   recreating it if available, and recreate `local-zfs` on the replacement SSD.
   Backup access itself must not depend on importing the mirror or `/tank/pbs`.
3. Discover B by its recorded UUID and inspect mounts read-only first; A remains
   quarantined unless separately diagnosed and explicitly approved for recovery.
   Preserve contents. For normal PBS service, unmount any
   `ro,norecovery` inspection mount and mount fresh RW with access-time updates.
   Never format or create an empty replacement store. Use the existing
   `pbs` directories and PBS datastore reuse, not initialization of lost history.
4. Rebuild unprivileged CT101/PBS4 with only verified approved surviving binds and schedules/
   standby off, or bootstrap compatible PBS under controlled administration.
   Existing disk data has host UID/GID**100034** for guest `backup`**34**:
   preserve that unprivileged mapping. A bare-metal PBS expecting host34 cannot
   blindly use the same ownership. Recreate the compatible mapping/mount design;
   never recursively chown surviving backup trees to work around the mismatch.
   Restore the writable runtime tmpfiles rule as well as datastore guards.
5. Through console/root PBS administration, reuse/register the surviving store,
   establish/pin trust and authorize controlled read recovery before trying the
   normal PVE token. Recover `recovery.pxar` and `collector.pxar` into a root-only
   destination. Restore `/etc/proxmox-backup` and the canonical
   `/root/.config/homelab/pbs-token.json` as a matched server/host identity, or
   deliberately issue a replacement token and update the native root-only
   `/etc/pve/priv/storage/<storage-id>.pw` files. A saved host token alone cannot
   authenticate to a newly initialized server identity. The role fails closed on
   token/server mismatch; resolve it explicitly rather than guessing secrets.
6. Selectively recover `pve-config.tar.gz` and `pmxcfs-config.db`; never extract
   all `/etc/pve`, SSH or network configuration blindly onto a running new host.
   Confirm TLS pins, storage identities/ACLs and native datastore readability.
   Restore the VM with the original per-storage mappings: SSD `local-zfs` for
   OS/appdata/EFI, HDD `tank-vm` (or an explicitly mapped replacement) for
   photos/files. If the mirror is also lost, provide sufficient replacement bulk
   storage first. All four data classes come from PBS, not a required Restic step.
7. Verify guest disk identities/mount guards before Docker, and restore actual
   media NFS separately for the full stack. Validate recovered applications/data,
   collector credentials and notification delivery before enabling schedules or
   public ingress. Preserve original backup disks, old `/tank/pbs` data and legacy
   Restic history throughout recovery.

Recovery archives contain private keys, rendered configuration, pmxcfs secrets
and PBS token/certificate/notification material. Protect restored files as a
credential store. The current pxar client explicitly uses `--crypt-mode none`;
root-only local files and pinned TLS do **not** encrypt the XFS disks at rest.
Restrict physical/admin access and keep independent offline bootstrap material.
