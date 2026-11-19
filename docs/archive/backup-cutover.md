# Proxmox backups

> Historical snapshot archived on 2026-11-19. All headings, measurements and
> commands below describe prior checkpoints, not current deployment instructions.
> Do not repeat staging, retired Restic schedules or cloud access. A is now
> untrusted/offline; B is the temporary sole active datastore. Use
> [current operations](../backups-proxmox.md) and [current status](../status.md).
> Google Drive remains cancelled; uploaded packs are not usable protection.

[Repository overview](../../README.md)

Sources of truth: [PBS role](../../roles/pve_pbs/),
[file backup/collector role](../../roles/pve_backup/),
[legacy guest-helper retirement](../../roles/docker_backup/),
[PBS inventory](../../inventory/group_vars/pve/pbs.yml),
[collector inventory](../../inventory/group_vars/pve/backup.yml),
[collector age policy](../../roles/pve_backup/defaults/main.yml),
[VM disks](../../inventory/group_vars/pve/vm.yml) and
[guest mounts](../../inventory/group_vars/docker/docker_vm.yml).
See also the [migration gates](proxmox-migration.md#migration-plan).

**Temporary B-only protection accepted on2026-11-19.** Full VM/filesystem recovery
and natural HDD standby/real-backup wake passed; A's hardware path remains untrusted.
The owner approved B as the temporary sole active PBS datastore, with A offline.
Native VM/file backup, freshness and PBS maintenance schedules are now enabled.
This is one active local repository, not dual-copy or off-site protection.
Restic histories and original datasets remain preserved; follow
[current acceptance evidence](../status.md). Historical sections below concern
the earlier Unraid/Restic/PBS cutover.

## Ownership and coverage

| Mechanism | Approved coverage | Limits |
| --- | --- | --- |
| Native snapshot-mode VM100 backup to vault-b | OS/EFI, Docker/appdata, managed photos and files disks | Not host/PBS bootstrap, VM102 or external media |
| Small PBS `host/pve-recovery` backup | PVE/PBS recovery configuration and remote VPS/HA/router collector | Independent source generations, not one transaction with VM100 |
| Optional native secondary sync | Disabled while the secondary datastore is empty | No current second active repository or off-site copy |
| Original datasets, legacy PBS/Restic histories | Preserved rollback/recovery evidence during migration | Not proof of current PBS-only coverage |

VM102's image is outside this VM100 job; its source-managed gateway rebuild is
documented in [OpenWrt day-0](../openwrt.md#gateway-vm-router-gw).

The active collector policy currently covers VPN/HA and router-srt/router-krm.
The owner temporarily excluded offline router-trvl/planned router-evn; its old
archives remain preserved and are not current protection. Re-enable it only
after the intended device is reachable and its SSH identity is verified.

VM root160 GiB and appdata128 GiB remain on SSD-backed `local-zfs`. Photos
3072 GiB (`scsi2`, serial `homelab-photos`) and files64 GiB (`scsi3`,
`homelab-files`) are managed sparse volumes on the existing HDD ZFS mirror via
`tank-vm`. Guest ext4 labels are `HOMELAB_PHOTOS`/`HOMELAB_FILES`; paths stay
`/mnt/photos` and `/mnt/files`. They must be enabled for image backup at cutover.
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
| vault-b | Selected temporary primary; acceptance pending | `/mnt/backup-b/pbs` → `/mnt/datastore/vault-b` | `d0347cdb-9c3b-41e8-88ce-498367a6f038` |

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
host `pve-backup` plus tag `pve-owned`, grouped by host/tags. Never broaden that
selector to historical Unraid/migration points or prune them to manufacture space.

Before the refresh, a read-only Unraid check on2026-11-12 decrypted10 retained
snapshot records. The latest historical snapshot, `3e3d300f4008` from2026-11-08
at06:00+04:00, covered `/mnt/user/backup` and Immich `backups`, `library`,
`profile`, `upload`; it did not establish current coverage of every migration tree.
A one-off [pre-cutover vault refresh](proxmox-migration.md#independent-pre-cutover-vault-refresh)
completed2026-11-12 at18:44+04:00: `57492bf21849` includes all eight read-only
staging trees and recovery, preserving all10 older points. Metadata checking
passed across11 snapshots;22.032 GiB of actual recovery files, the HA disk and
user-data samples were restored against staging. This was not a full pack scan
or off-site proof. Its `migration-pre-pve` tag is outside `pve-owned` retention.

## Consistency protocol

1. PVE's native `homelab-vm100-pbs` job uses **snapshot** mode against
   `pbs-vault-b`, with the enabled/running QEMU Guest Agent freezing/thawing local
   filesystems. Recovery is crash-consistent, not a clean application shutdown;
   databases must replay their journals/WAL. This preserves QEMU dirty bitmaps
   between backups and avoids nightly VM/GPU restarts. Stopping the VM loses
   those bitmaps and requires rereading its data even when little changes.
   The first cold acceptance point explicitly uses stop mode; recurring jobs do
   not stop containers, cold-rsync appdata, dump SQL or choreograph ZFS snapshots.
2. After upstream archive generation, the host coordinator collects remote
   archives over the existing strictly pinned SSH identity into the root-only
   ZFS dataset `/rpool/backup-staging/collector`. Migrate the existing
   `/tank/files/homelab-backups` history there before enabling it. The collector
   requires the exact mounted writable dataset, not a fallback directory.
3. Each archive source must have a matching completed regular non-symlink file,
   nonempty, not future-dated and at most24h old. Successful rsync or a fresh
   unrelated file is insufficient. Router backups are generated during collection
   and must be nonempty valid gzip archives.
4. The coordinator takes a consistent SQLite backup of pmxcfs, packages
   `pve-config.tar.gz` (including the canonical PBS token) and
   `pbs-config.tar.gz` (`/etc/proxmox-backup`), validates gzip, then sends
   `recovery.pxar` and `collector.pxar` to PBS as `host/pve-recovery`.
   Rendered guest configuration is protected inside the VM's OS/appdata image.
5. The [PBS proof helper](../../roles/pve_backup/templates/pbs-file-backup.py.j2)
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
[`homelab-pbs-ntfy` webhook and `homelab-pbs-errors` matcher](../../roles/pve_pbs/templates/notifications.py.j2)
route verification/GC/prune warnings and errors to the existing alerts channel.
The channel secret is kept only in root0600 PBS private notification configuration,
never process arguments or logs. Native target delivery has been tested; phone
receipt and full PBS-only nightly acceptance are not implied by that test.

After backup/recovery acceptance, the
[HDD policy](../../roles/pve_pbs/tasks/power.yml) sets ATA timeout244, **120min idle**,
only on enabled declared SATA/XFS10 TB disks after serial/UUID checks; currently B.
Disks stay connected and mounted; this is standby, not physical power-off,
unplugging or forced sleep during active work. Include VM/file backup, sync,
prune, GC and verify in the I/O/wake window, not merely the02:00 VM start.
SMART monitoring respects standby. Observe an actual idle interval and successful
backup/maintenance wake afterward; polling must not itself wake disks.
No sleep/wake acceptance or disk lifespan improvement is claimed.

## Apply

The commands below are deliberate cutover/reconciliation actions, not permission
to reinitialize existing disks. Current bulk data is local and included in native
VM backups. On a new/rebuilt node, keep schedules and HDD standby disabled
throughout recovery acceptance and require verified parity before final mounts.

### Provision without automatic schedules

1. Confirm original data/history remains intact and no backup/collector/native PBS
   task is active. Recover any old host `guest-needs-resume` or guest
   `/var/lib/homelab-appdata-backup/running.json` transaction using the still-installed
   legacy tooling before retirement; preserve its record, never just erase it.
   A one-time cold SQL reference can support acceptance, not recurring operation.
   `prepare` alone does not keep this point cold across a guest reboot: containers
   with `restart: always` start again. Record Docker unit enable/mask state and
   persistently mask both `docker.service` and `docker.socket` for this one-time
   acceptance window; runtime masks disappear on reboot. Once the native backup
   point is established and the guest is running, restore the recorded unit state
   and resume the original container IDs immediately, not after the bulk transfer.
   That one-time recovery point retains the masks/pending manifest: configure
   isolation and real mount guards before explicitly unmasking/starting Docker
   and selecting workloads to recover. Never add this choreography to daily jobs.
2. Verify physical identities, free space and existing XFS against
   [PBS inventory](../../inventory/group_vars/pve/pbs.yml). Keep A/tank identity
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
4. Complete immutable seed verification, then bounded writer pause, final delta
   and frozen-point metadata/content proof using
   [verify-tree](../../scripts/verify-tree.py). Switch guest photos/files to the
   managed local disks, validate applications and enable both disk backups.
   Keep originals and rollback evidence; do not blindly revert after new writes.
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
`norecovery`. B was unmounted and freshly mounted normal RW before preparing
private restore space; all nine migration directories remain. Require XFS, exact
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

Historical capacity preflight (2026-11-15 local): vault available6,875,949,281,280
of9,998,694,297,600 bytes; old tank PBS quota1,099,511,627,776,
used54,942,691,328, available1,044,568,936,448 bytes. These are historical
measurements, not current A/B capacity or a guarantee that full bulk retention
fits. Monitor each independent disk's free space and native tasks; no formatting,
history pruning or old1 TiB tank fallback to manufacture space.

### Observed automation activation — 2026-11-15

**Historical Unraid/Restic cutover evidence; not PBS-only acceptance.** The
following activation describes the prior pipeline and its then-current schedules.

The reviewed source was first applied with explicit schedule overrides off, then
the persistent inventory flags were enabled and scoped PBS/backup applies passed.
No timer stamps existed before activation, all four services were inactive and
no guest-resume manifest existed. Native acceptance found all four timers enabled
and waiting, with future NEXT values and no surprise service start.
PVE VM100 backup is enabled with `repeat-missed=0` and `keep-all=1`; PBS alone
owns its prune policy. PBS prune, GC and verify report future native next runs.
Host and CT both persist Asia/Yerevan, sharing the synchronized host clock.

A read-only retention dry-run preserved all eleven historical IDs among thirteen
snapshots, outside the automatic selector. One isolated notification-state fixture
exercised the real ntfy helper: HTTP200 and a message ID were returned; production
success/failure markers were untouched. Phone receipt was not tested.
At this activation checkpoint, the first nightly execution was still unobserved.
The subsequent first-night acceptance below establishes the automatic result.

Evidence: `/root/migration-automation-20261114T195553Z`,
`activation.guard.json`, `backup-automation.COMPLETE.json`,
`schedules.after-activation.json` and `notification.acceptance.json`.

### First scheduled night and recovery — 2026-11-15

**Historical prior pipeline.** The timing defect below motivates the new07:15
collection and24h source-age policy; the measurements do not prove a new bulk
image, B recovery or standby acceptance.

Observed times use Asia/Yerevan:

| Job | Started–finished | Result |
| --- | --- | --- |
| Collector | 01:02:31–01:02:44 | exit0,13s |
| PBS VM100 | 02:00:01–02:05:12 | native taskOK,5m11s |
| Restic coordinator | 03:05:09–03:20:09 | exit0,15m |

New PBS volume `vm/100/2026-11-14T22:00:01Z` and the retained original image
both passed native PBS verification. Scheduled prune, GC and verify reportedOK;
GC reported no bad chunks. The monthly restic data check is not due until Dec01.

New restic point `53ae0b7ab959` processed884,457 files /1.945 TiB; its scan took
5m32s, adding2.201 GiB stored through deduplication. Metadata checking found no
errors across14 snapshots; all eleven historical IDs remain present.
Production helpers resumed the original containers around03:12, before scanning.
All34 original container IDs/pinned references match, all are running, configured
healthchecks are healthy, and restart counts/resume manifests show no pending failure.
Ordinary Immich, Vaultwarden and local Jellyfin HTTP probes returned200.

Bounded restoration used only these **new automatic** points:

- PBS native file recovery extracted guest OS identity plus Vaultwarden SQLite
  and its matching WAL. OS hash matched; SQLite `quick_check=ok`,597 ciphers.
  No full VM was restored or booted.
- Restic verified the original photo/PDF bytes and UID/GID/mode/mtime/xattrs
  against matching frozen ZFS sources. All four latest SQL gzip/hash checks passed.
  One new Immich dump replayed into an isolated pinned-image container: all66
  table counts matched that dump, including216,918 assets.
- Recovery helpers, disposable database/container/volume and sensitive fixtures
  were removed. Production was not stopped for this acceptance exercise.
  This is not a full2-TB restore, replay of every SQL application or UI sign-in proof.

**Upstream timing warning:** the frozen nightly point contains VPS/HA archives
dated Nov14, while newer Nov15 archives now exist on those sources. The collector
at01:00 and the coordinator's embedded collection precede their generation.
In current timezones, HA's new archive mtime is about04:00 Yerevan, Kuma's daily
cron runs05:00, and VPN's03:30 Europe/Amsterdam cron runs06:30 Yerevan in CET.
Successful rsync is not proof of current-generation source archives.
Align generation/collection and source-freshness expectations before calling this
same-night remote coverage. This verification changed no schedules or jobs.

Private evidence: `/root/migration-overnight-20261115T075700Z`,
`night.verdict.json`, `pbs.recovery-result.json`, `restic.sql.json`,
`legacy-preservation.json`, `upstream.frozen-archive-proof.json` and
`upstream.archive-generation.json`. Keep raw worker transcripts private.

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
  [verify-tree](../../scripts/verify-tree.py) for full migration parity.
- Fault handling rejects wrong/missing mounts, stale/empty/future sources, failed
  VM/sync and missing indexes without advancing the corresponding success.
  Use disposable fixtures; do not unplug or corrupt production disks to test.
- Native maintenance alerts, conservative standby and subsequent backup plus
  maintenance wake work, with old histories preserved.

A successful sync, native chunk verify, receipt or bounded sample alone does not
prove usable full-stack recovery. B bulk restore/sleep gates remain open.

### Observed migration recovery — 2026-11-14

**Historical acceptance of the earlier OS/appdata + Restic model.** Statements
about disabled schedules below describe that checkpoint, not current desired state.

- PBS `vm/100/2026-11-14T12:12:35Z` completed in8m47s, including root,
  appdata and EFI. Actual restoration into isolated VM900 took about5m20s.
  Debian13 booted with real ext4 appdata: Vaultwarden597 ciphers/SQLite
  `quick_check=ok`, Paperless PostgreSQL18 cluster files and Minecraft world
  files were present. Docker/Tailscale stayed masked, NICs down and GPU absent.
  Expected network/GPU failures made this a degraded isolated boot, not complete
  application/client recovery. The marker-guarded VM and its four volumes were removed.
- The first host checkpoint failed before restic at the cross-pool snapshot
  command; its trap resumed the original workloads. Disposable native datasets
  reproduced the exact failure and proved separate calls; fixtures were removed.
- The corrected coordinator created matching read-only snapshots on all three
  datasets, then resumed the original workload set before the long scan.
- Separate restic point `f83a130ac874` protects the completed cold-copy four SQL
  dumps, Vaultwarden and guest recovery configuration. Actual `restore --verify`
  plus SHA256 comparison passed; recovered Vaultwarden contains597 ciphers.
  All11 historical snapshots remain. This smaller point precedes the complete
  current checkpoint below; it is not a substitute for full bulk coverage.
- Three router failures were endpoint-key mismatches, not Dropbear key rotation:
  authenticated Tailscale peer keys matched the presented SSH keys, and strict
  collector-identity authentication passed without an approval challenge.
  Host-pin proof alone does not establish successful fresh archive collection.
- Full checkpoint `e752f5a4a909` completed2026-11-14 at16:12:51 UTC, exit0.
  It processed884,393 files /1.943 TiB in2h40m47s; the complete coordinator,
  including collection/quiescence, took2h46m55s. Deduplication reused the existing
  repository, adding1.191 GiB stored. Collection succeeded and metadata checking
  reported no errors.
- Actual `restore --verify` from that full snapshot recovered an Immich original
  photo and a PDF. SHA256, numeric UID/GID, permissions, nanosecond mtime and
  xattrs matched the frozen inputs, including all three PDF xattrs.
  Disposable restored files were removed; all11 historical snapshots remain
  among13 repository snapshots. This is bounded recovery proof, not a full
  repository pack-data scan or off-site protection.

Evidence: `/root/migration-backups-20261114T120556Z` on PVE, including
`vm900-recovery.json`, `zfs-crosspool-contract.json`, `proof-backup.result.json`,
`collector-hostkey-identity-proof.json`, `checkpoint.second-views.json`,
`restic.full-summary.json` and `full-bulk-restore.result.json`.
Automatic PVE/PBS jobs, PBS GC and host timers remain disabled/unscheduled.

The populated physical UPS cycle subsequently exposed a proxy startup failure:
`/run/proxmox-backup` had been recreated as root, denying the `backup` service
its PID file. The persistent tmpfiles fix passed a native regression probe and
a CT-only reboot: pinned storage became active, the original VM image remained
listed and the real PBS sign-in UI rendered. No backup schedules were enabled.
Evidence: `/root/migration-ups-populated-20261114T174036Z`,
`pbs-runtime.after-reboot.json` and `ups-physical-populated.COMPLETE.json`.

### Logical SQL recovery — 2026-11-14

The four actual restic-restored dumps were replayed with `ON_ERROR_STOP` into
fresh volumes using their pinned PostgreSQL14/18 images. Fixtures had no network,
published ports or production mounts. Every dumped table's row count matched:

| Database | Dumped tables matched | Restored rows |
| --- | ---: | ---: |
| Immich | 66 | 1,860,855 |
| Paperless | 72 | 5,885 |
| LiteLLM | 78 | 859 |
| Order-manager | 14 | 51 |

All fixture databases shut down with exit0, no OOM; their containers and volumes
were removed. Evidence: `sql-recovery.result.json` in the directory above.
This proves logical recovery, not owner-client sign-ins or off-site availability.

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
Google API requests without renewed authorization; the partial upload is not
usable backup protection. Historical setup used remote `gdrive:`, rclone1.72.0,
the operator's desktop OAuth client and `drive.file` scope. The initial64 KiB
transport test passed, but account availability no longer holds.

Credentials are stored at `/mnt/cache/appdata/migration-rclone/rclone.conf`,
root-owned `0600` inside a `0700` directory on the persistent cache filesystem.
The workspace is excluded from the cold appdata copy; credentials were captured
separately in protected recovery `cloud-backup/`, now marked `CANCELLED`. Preserve
them only as recovery evidence; do not deploy them to PVE as an active cloud target.

No Google access command is provided here: this target is cancelled.

### Encrypted cloud repository

**Cancelled historical experiment, not active protection.**

Former repository `rclone:gdrive:homelab-restic` (ID prefix `379416da99`) was
initialized in format2 with local chunker parameters; initialization copied no
source snapshots. It used the existing password file
`/boot/config/restic/password`; that password was privately confirmed against
`vault_restic_password` in the encrypted Ansible vault. Keep a separate offline
recovery copy of the password/vault unlock key.

Actual verification backed up a256 KiB synthetic binary plus files, hardlink,
symlink and empty directory. Cloud `check --read-data` passed; `restore --verify`
preserved bytes, numeric UID/GID, permissions and links. A wrong password was
rejected. Only the verification snapshot and its unused packs were removed from
the new cloud repository; all10 existing local snapshots were preserved.

The real seed exited1 after Google's daily upload limit, having transferred about
750.535 GiB. The operator subsequently lost access to the account and cancelled
the target. No cloud process, automatic retry loop or recurring schedule remains.
Do not infer recoverable snapshots from uploaded packs or the synthetic restore.
The old local vault remains intact; replace remote protection separately.

### Initial cloud seed

**Cancelled historical seed; retain evidence, do not resume.**

Started2026-11-10 with `restic copy` from `/mnt/vault/restic` into
`rclone:gdrive:homelab-restic`, capped at25 MiB/s upload (`RCLONE_BWLIMIT=25M:off`).
Tmux failed before launch, so the copy used `nohup` and survived SSH disconnects.
It later stopped on Google's upload limit and is now explicitly cancelled after
account loss. Source retention/prune was never requested.

Protected run files under `/mnt/cache/appdata/migration-rclone/`:

- `cloud-seed-20261110T191924Z.log`: copy output and minute-by-minute rclone stats.
- `cloud-seed-20261110T191924Z.pid`: source-side supervisor PID,1411011 at launch.
- `cloud-seed-20261110T191924Z.exit`: created when the command exits;0 means copy
  completed, nonzero means it stopped/failed. Absence alone does not prove liveness.
- `cloud-seed-20261110T191924Z.cancelled`: explicit operator cancellation; no resume.

Observe from Unraid:

```bash
tail -f /mnt/cache/appdata/migration-rclone/cloud-seed-20261110T191924Z.log
```

The initial pack uploads and synthetic restore were exercised, but the real seed
failed on `403 userRateLimitExceeded` at13:43+04:00 and must not be resumed now.
The source-side cancellation marker is also saved as recovery
`cloud-backup/CANCELLED`. Logs and credentials are retained privately; no attempt
was made to access or delete objects in the unavailable Google account.

### Secondary internal filesystem repository

This heading is retained for historical links. The former internal Restic-copy
workflow is retired; no attach/init/refresh/detach helper or legacy variable is
required. Do not initialize a repository or delete migration data. B is now the
selected primary, not an active replica. Secondary sync is disabled until a
healthy copy is configured and proven. Legacy passwords/snapshots and private
cloud cancellation evidence remain preserved.

## Isolated VM restoration

1. Select an exact completed VM point from A (then independently repeat from B)
   and record its native task, archive list and original VM storage configuration.
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
3. Discover surviving A/B XFS by the recorded UUIDs, inspect mounts read-only
   first and preserve contents. For normal PBS service, unmount any
   `ro,norecovery` inspection mount and mount fresh RW with access-time updates.
   Never format or create an empty replacement store. Use the existing
   `pbs` directories and PBS datastore reuse, not initialization of lost history.
4. Rebuild unprivileged CT101/PBS4 with only surviving A/B binds and schedules/
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
