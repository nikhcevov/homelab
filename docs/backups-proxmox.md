# Proxmox backups

[Repository overview](../README.md)

Sources: [host role](../roles/pve_backup/), [guest helpers](../roles/docker_backup/),
[PBS role](../roles/pve_pbs/), [backup variables](../inventory/group_vars/pve/backup.yml),
[PBS variables](../inventory/group_vars/pve/pbs.yml),
[migration gates](proxmox-migration.md#migration-plan).

PBS CT101 and host automatic backups are enabled after native backup/recovery
and first-activation checks. The first PBS image and isolated OS/appdata restore,
four SQL imports, and full restic photo/PDF recovery passed.
The first scheduled nightly PBS/restic executions have not yet been observed;
enabled future schedules are not a claim that a new backup already completed.
Preserve the existing repository, all eleven historical snapshots and staging.

## Ownership and coverage

| Mechanism | Covers | Does not establish |
| --- | --- | --- |
| PBS VM100 images | Guest root, Docker metadata, local ext4 appdata | NFS photos/files/media; host recovery |
| Host restic | Quiesced appdata, photos, files, collector, PVE/guest/PBS recovery configuration | Replaceable media or an independent running host |
| Second local restic copy | Retained repository snapshots on another internal disk | Off-site protection or an independent host |
| ZFS snapshots | Immutable backup inputs and short local history | Independent backup or cross-host availability |

The old XFS vault is mounted at `/mnt/vault`; repository `/mnt/vault/restic`
and `vault_restic_password` are retained. No local repository initialization or
disk formatting is performed. Automatic restic retention requires both host
`pve-backup` and tag `pve-owned`, grouped by host/tags. All eleven historical
Unraid/migration snapshots are outside that selector; never broaden it to the
whole repository. The same selector protects history in a secondary copy.

Before the refresh, a read-only Unraid check on2026-11-12 decrypted10 retained
snapshot records. The latest historical snapshot, `3e3d300f4008` from2026-11-08
at06:00+04:00, covered `/mnt/user/backup` and Immich `backups`, `library`,
`profile`, `upload`; it did not establish current coverage of every migration tree.

A one-off [pre-cutover vault refresh](proxmox-migration.md#independent-pre-cutover-vault-refresh)
completed2026-11-12 at18:44+04:00: snapshot `57492bf21849` includes all eight
read-only staging trees and recovery, preserving all10 older snapshots.
Metadata checking passed across11 snapshots;22.032 GiB of real recovery files,
the Home Assistant disk and user-data samples were restored and verified against
staging. This is not a full repository data scan or off-site protection.
Its `migration-pre-pve` tag is outside automatic `pve-owned` retention.

Reviewed cadence uses the existing `bootstrap_timezone=Asia/Yerevan` authority
(UTC+04, no daylight-saving changes), not a separate PBS timezone variable:

| Job | Local time | UTC |
| --- | --- | --- |
| Collector | daily01:00 +0–5min jitter | previous day21:00 +0–5min |
| PBS VM100 | daily02:00 | previous day22:00 |
| Restic | daily03:00 +0–5min jitter | previous day23:00 +0–5min |
| PBS prune | daily07:00 | daily03:00 |
| PBS GC | daily08:00 | daily04:00 |
| PBS verify | Sunday10:00 | Sunday06:00 |
| Restic random10% data check | first day of month12:00 +0–5min | 08:00 +0–5min |
| Freshness | hourly at:30 +0–5min | hourly at:30 +0–5min |

Host timer calendars explicitly include that timezone. PBS provisioning refuses
a host timezone mismatch, sets CT101's persistent LXC timezone and reconciles its
live timezone. The CT shares the synchronized host kernel clock; a separate CT
NTP client is not required. PBS calendars use the CT's local time; PVE uses the
host's. Maintenance was moved out of the observed03:00–~06:00 restic window
(2h46m55s coordinator, PBS8m47s). These are measurements, not maximum runtimes.
PBS has native task locks; it does not share the host restic/collector `flock`.
The host commands share a lock with a1h wait; independent collection also has
its own lock. Long contention fails visibly, rather than running concurrently.

Restic keeps7 daily,8 weekly,6 monthly points; PBS keeps7 daily,4 weekly,6 monthly.
Only PBS performs PBS pruning: the PVE image job explicitly uses `keep-all=1`.
Hourly freshness alerts after36h without a local success, allowing daily scan
duration/jitter to vary without false24h overdue alerts. A configured secondary
UUID also alerts after30 days; a blank UUID defers only that copy's check.
Neither the internal replica nor successful checks establish off-site protection.

## Consistency protocol

1. The PVE coordinator verifies actual filesystem UUIDs, mounts and datasets.
2. The collector refreshes VPS archives, Home Assistant backups and router
   configurations. Failed sources alert individually; local application backup
   continues with the last collected archives and reports overall failure.
3. A restricted private-link SSH helper records the exact running container IDs
   durably before stopping anything. It stops application writers, dumps the
   configured PostgreSQL services atomically, then stops those databases.
4. PVE pulls appdata read-only into `rpool/backup-staging/appdata`, preserving
   numeric owners, ACLs, xattrs and hardlinks. The parent staging directory is
   root-only; the copied guest root metadata remains unchanged.
5. ZFS snapshots of appdata staging, `tank/photos` and `tank/files` are taken
   in separate native calls while all relevant writers remain stopped across
   every call. One invocation cannot span pools: native ZFS reports
   `multiple snapshots of same fs not allowed`, even for distinct datasets.
   This is one quiesced checkpoint, not an atomic transaction across two pools.
6. Original database containers resume first, then other originally running
   containers. Previously stopped containers remain stopped. No restic scanning,
   retention or integrity checking happens during downtime.
7. Restic reads read-only snapshot views and protected recovery archives.
   Metadata checks must pass before recording local success. Only owned ZFS
   snapshots expire; unrelated snapshots are untouched.

Traps and systemd `ExecStopPost` attempt resume after failures. A failed SSH
resume retains `/var/lib/homelab-backup/guest-needs-resume`; the guest keeps its
original running manifest until every container is running again. Power loss or
SIGKILL can still interrupt recovery: inspect both manifests and explicitly run
`homelab-backup resume` before any further repository work.

Frigate configuration/database are protected; replaceable recordings under the
configured exclusions are not. Media is deliberately excluded. External file
writers must also be stopped during the checkpoint; do not add another writer
without extending this ownership protocol.

## Apply

Prerequisites:

- PVE storage, Docker baseline and restored workloads passed their phase gates.
- Existing vault UUID matches the audited disk. If configuring a second
  repository, record its XFS UUID in `pve_backup_offsite_uuid`, never `/dev/sdX`.
- The guest helper is installed by `playbooks/docker.yml`. Its collector public
  key allows only prepare/resume and read-only rsync under `/mnt/appdata`, from
  `10.77.0.1`. It cannot open an unrestricted guest shell.
- Source collector SSH identity and existing known-host pins are vaulted.
  Verify the guest ED25519 fingerprint independently before deliberately using
  `pve_backup_bootstrap_known_hosts=true` once; bootstrap never replaces a pin.
  Router Tailscale SSH endpoints present different keys from LAN Dropbear.
  Reconcile a stale pin only after matching the presented key to the authenticated
  named peer's `sshHostKeys` in `tailscale status --json`; preserve unrelated pins.
- Vault/restic passwords have a separate offline copy. An encrypted backup of
  its own password is not sufficient for first recovery.

### Provision without automatic schedules

Provision PBS alone, leaving `pve_pbs_schedules_enabled=false`:

```bash
ansible-playbook playbooks/pve.yml --limit great-hornbill --tags pbs -e pve_pbs_enabled=true -e pve_pbs_schedules_enabled=false
```

The role discovers the official Debian13 LXC template, creates managed CT101,
uses unprivileged backup UID34 → host100034 and registers TLS-pinned `pbs-tank`.
Inventory assigns5 GiB for the1 TiB datastore; first creation also requires1 GiB
available host headroom. This is a sizing guard, not peak-load proof.
`tank/pbs` must have `atime=on`; its datastore root must belong to host
UID/GID100034. Only an empty root may be changed, never recursively chown an
existing store. The root-owner check is not a recursive contents audit:
native verify/restore must establish existing backup readability.
The bind datastore is excluded from CT backups and has a fail-closed startup guard.

PBS's volatile `/run/proxmox-backup` must be writable by guest `backup`34.
The role installs `/etc/tmpfiles.d/homelab-pbs.conf` to recreate that directory
as `backup:backup`0755 on every boot and applies it before starting PBS.
This is separate from datastore ownership; never recursively chown backup data
to repair a runtime PID-file error.

PVE's native add hook deletes a password omitted from CLI arguments. Initial
registration therefore creates disabled storage, writes its root-only native
password file, then enables it and requires active status. Secrets never enter
process arguments. Saved token identity and TLS pins are checked on reconciliation.
Server/datastore are immutable PVE fields: validate them, but do not resend them
on `pvesm set`.

PBS API access is private host `.1` only; the LAN NIC is for DHCP/outbound updates.
Guest SSH service/socket are masked; administration uses `pct`/PBS. PVE datacenter
filtering has default-accept host policy and CT default-drop policy, preserving
the separate host management restriction. The VM/CT share one hardware failure domain.

With schedules off, PVE's backup job is disabled, PBS prune is disabled,
verification is manually runnable but unscheduled, and datastore GC is unscheduled.
Reruns preserve this state. Do not arm schedules merely to provision storage.

Prepare host backup staging/credentials with timers still off:

```bash
ansible-playbook playbooks/pve.yml --limit great-hornbill --tags backup -e pve_backup_provision=true -e pve_backup_enabled=false
```

`pve_backup_provision` creates the staging datasets and validates credentials/pins;
`pve_backup_enabled` alone controls timer activation. Protected installation
directories remain root0700, but creating mount paths does not chmod/chown a
mounted retained filesystem. The role writes fstab without mounting/initializing
the vault. Staging parent permissions never rewrite copied guest-root metadata.

### Attach the retained vault and run manually

The migration vault starts `ro,norecovery`. XFS cannot remount that state directly
read-write. After UUID/source verification and confirming no process uses the
vault, unmount it and mount it fresh using the now-installed fstab entry:

```bash
findmnt --mountpoint /mnt/vault -o SOURCE,UUID,FSTYPE,OPTIONS
fuser -m /mnt/vault
umount /mnt/vault
mount /mnt/vault
findmnt --mountpoint /mnt/vault -o SOURCE,UUID,FSTYPE,OPTIONS
```

Require UUID `6d3f33cb-faaf-4497-8131-2f40f07cfbbd`, XFS, `rw`, no `norecovery`;
preserve its existing root owner/mode. Keep `/mnt/staging` read-only. This permits
new repository writes; it does not authorize formatting, initialization or deleting
the eleven migration/legacy snapshots. Record their IDs before the first run.

With all timers/schedules confirmed off, start the existing service manually:

```bash
systemctl start homelab-backup.service
```

It runs durably through SSH loss and retains the failure/resume hooks. A collector
failure still allows local protection but makes the overall result fail; do not
disable a source or suppress that result to claim complete collection.

### Arm only after recovery proof

After a real current backup, file/dump import and isolated VM restoration pass:

1. For initial preparation or a deliberate maintenance re-arm, first require no
   active backup service; use the provisioning commands above with their explicit
   schedule/timer disable overrides. Current inventory is armed: a normal scoped
   apply preserves activation. Existing strict pins suffice; do not bootstrap again.
2. Require no backup/collector/check/freshness service active, no durable guest
   resume manifest, the retained UUID mounted RW, pinned PBS storage active, and
   all eleven historical IDs still present. Confirm host and CT timezone/NTP
   state and inspect the native catalogs and saved recovery results below.
3. Inspect disabled timer stamps and pending schedules **before** activation:

   ```bash
   systemctl show homelab-backup{,-collect,-check,-freshness}.timer \
     -p Id -p ActiveState -p UnitFileState -p Persistent -p LastTriggerUSec -p NextElapseUSecRealtime
   find /var/lib/systemd/timers -maxdepth 1 -name '*homelab-backup*' -printf '%f %TY-%Tm-%TdT%TH:%TM:%TS\n'
   systemd-analyze calendar --iterations=2 '*-*-* 03:00:00 Asia/Yerevan'
   pct exec 101 -- proxmox-backup-debug api get /admin/prune --output-format json
   pct exec 101 -- proxmox-backup-debug api get /admin/verify --output-format json
   pct exec 101 -- proxmox-backup-debug api get /admin/gc --output-format json
   ```

   All four timers use `Persistent=true`: an old stamp can immediately catch up
   a missed run after activation/boot, including application quiescence. The
   initial automation preflight found **no stamps**, disabled/inactive timers
   and empty LAST/NEXT; a first enable creates stamps at the current time and
   waits for the next calendar event (plus up to5min jitter/1min accuracy).
   If stamps now exist, review their age; do not blindly start timers while
   production/DNS work is in progress. To intentionally discard catch-up for a
   maintenance re-arm, first stop/disable timers, confirm associated services
   inactive, then use `systemctl clean --what=state UNIT.timer` for each timer.
   Never erase the backup's own durable state or a guest resume manifest.
   PVE explicitly sets `repeat-missed=0`. PBS job state is independent: review
   native `next-run` fields for overdue maintenance, not just systemd NEXT.
4. The integration owner persists `pve_pbs_enabled: true`,
   `pve_pbs_schedules_enabled: true` and `pve_backup_enabled: true` in their
   inventory files **only after readiness review**, then applies:

   ```bash
   ansible-playbook playbooks/pve.yml --limit great-hornbill --tags pbs
   ansible-playbook playbooks/pve.yml --limit great-hornbill --tags backup
   ```

   Extra-vars are per-run; inventory flags determine later reconciliation.
   Do not arm restic before PBS recovery configuration can be captured.
   Verify enabled/waiting timers and **future** NEXT times immediately;
   do not manually launch heavy jobs just to demonstrate activation.

Initial capacity preflight (2026-11-15 local): vault available6,875,949,281,280
of9,998,694,297,600 bytes; PBS quota1,099,511,627,776, used54,942,691,328,
available1,044,568,936,448 bytes. This is ample current headroom, not a guarantee
that all retention generations fit without deduplication. Monitor native quota,
free space and task results as new generations accumulate. Keep the staging disk
unmounted; do not initialize a repository or prune history to manufacture space.

### Observed automation activation — 2026-11-15

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
The first nightly scheduled PBS/restic execution remains unobserved; existing
manual backup/restore evidence above is not a new automatic-run result.

Evidence: `/root/migration-automation-20261114T195553Z`,
`activation.guard.json`, `backup-automation.COMPLETE.json`,
`schedules.after-activation.json` and `notification.acceptance.json`.

## Verify

On PVE, as root:

```bash
homelab-backup backup
homelab-backup check-metadata
homelab-backup check-data
homelab-backup check-full
systemctl list-timers 'homelab-backup*'
pvesm status --storage pbs-tank
vzdump 100 --storage pbs-tank --mode snapshot
pct exec 101 -- proxmox-backup-manager verify-job run homelab-verify
```

`check-metadata` does not read pack contents. `check-data` reads a random10%
subset; repeated samples do not guarantee complete coverage. `check-full` reads
all pack data. A successful job or byte verification does not prove that restored
PostgreSQL/application data is usable: import a dump and open recovered state.

Test a failed dump/copy and confirm the original containers resume without a
success timestamp. Test missing/wrong mounts, reboot ordering and a controlled
UPS shutdown on the real host. Never simulate a failure against production by
removing a live disk or corrupting its repository.

### Observed migration recovery — 2026-11-14

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

The new10 TB disk stays internal. Prepare plain XFS, without LUKS, for migration
staging. Keep all staged data until backup and application restore gates pass;
initializing a restic repository does not erase those files. Later, this disk can
hold another restic repository if capacity permits. Restic encrypts the repository;
raw staging files remain unencrypted.

The existing `offsite-*` commands operate the optional second XFS repository
slot. Using them on this internal disk creates a local replica only. Configure
`pve_backup_offsite_uuid` with its filesystem UUID when ready; until then, copy
freshness monitoring is deferred and local backup freshness remains enforced.
No encryption mapper or unlock step is required. Mount, UUID, XFS, writability
and distinct-vault identity guards remain mandatory.

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

After explicitly setting the new disk's filesystem UUID:

```bash
homelab-backup offsite-attach
homelab-backup offsite-init EXPECTED_UUID
homelab-backup offsite-refresh
homelab-backup offsite-check-full
```

Run `offsite-init` only once, against an existing verified XFS mount with no
`restic` directory. It does not partition/format/delete anything. `offsite-refresh`
uses `restic copy` with compatible chunker parameters, includes historical source
snapshots, and performs a metadata check. Do not substitute rsync of a live
repository or prune legacy snapshots implicitly.

Restore into an empty, dedicated mounted test filesystem under `/mnt/restore/`:

```bash
homelab-backup verify-restore local SNAPSHOT_ID /mnt/restore/local-test
homelab-backup verify-restore offsite SNAPSHOT_ID /mnt/restore/offsite-test
homelab-backup offsite-detach
```

The helper restores and byte-verifies the selected snapshot. It refuses a
nonempty/unmounted target. Inspect recovered applications/dumps as well.
`offsite-detach` unmounts the secondary filesystem; it does not establish remote
protection. Freshness timestamps record copy success, not physical location.

## Isolated VM restoration

1. List PBS backups using `pvesm list pbs-tank`; restore the selected volume into
   an unused ID, not VM100:

   ```bash
   qmrestore LISTED_BACKUP_VOLUME 900 --storage local-zfs --unique 1
   qm set 900 --onboot 0 --delete hostpci0,hostpci1
   ```

2. **Do not start the clone yet.** Inspect its configuration, remove/disable every
   NIC or move them to a disconnected test bridge, and reduce RAM if necessary.
   Do not attach the production GPU to two guests. `--unique` is not storage
   isolation and does not remove production NFS endpoints.
3. Inspect restored disks read-only, or provide isolated copies of bulk data and
   adjust the clone's mounts before booting it. Keep external bot/webhook/game
   traffic disabled. Never point a restore test at writable production NFS.
4. Verify local appdata, PostgreSQL recovery and representative application
   state. Record the backup ID, restored state and elapsed recovery time.

## SSD-loss bootstrap

Recover from a host console; do not assume PBS can start from the failed SSD.

1. Reinstall PVE onto the replacement SSD, configure static node networking and
   tailnet/IPMI access, and import surviving `tank` without recreating it.
2. Recreate `local-zfs` on `rpool/data`, the private bridge and host filtering.
   Obtain the repo and vault/restic passwords from independent offline storage.
3. Rebuild CT101 using `pve_pbs` against the surviving dataset. Restore PBS's
   `/etc/proxmox-backup` together with
   `/root/.config/homelab/pbs-token.json`, not an old host token alone into a
   newly initialized PBS identity. Alternatively, explicitly move the saved
   token JSON aside and issue a new token with the same auth ID.
4. Re-register/verify the datastore and TLS fingerprint, restore VM100, and restore
   lost bulk data from restic as required. Reconcile mount and startup guards
   before authorizing Docker.
5. Recover host configuration selectively from `pve-config.tar.gz` and the
   pmxcfs SQLite backup. Do not extract all of `/etc/pve` or host SSH/network
   configuration blindly onto a running replacement. Recover guest Compose
   environments from `.homelab-recovery/guest-config.tar.gz` if needed.
6. Validate source credentials and notification destinations before enabling jobs
   or public ingress. Keep the old repository and recovery artifacts intact.

Recovery archives contain private SSH keys, rendered environments, NUT/restic
credentials and PBS token/certificate material. They are root-only locally and
inside encrypted restic snapshots. Handle a restored copy as a credential store.
