# Current status

[Repository overview](../README.md)

Accepted state: **2026-11-19**. This summarizes recorded acceptance, not a new
runtime health check or an observed subsequent scheduled night.
The complete original dated record is preserved in
[migration checkpoints](archive/migration-checkpoints.md).

## Accepted production state

| Area | Accepted state |
| --- | --- |
| Hypervisor | PVE `great-hornbill`; management SSH/8006 tailnet-only |
| Docker | VM100 `docker-1`; 12 production stacks / 39 containers; configured healthchecks healthy at acceptance |
| PBS | CT101; temporary sole primary B; only B's `mp2` attached |
| Router | OpenWrt VM102 `router-gw`; manually managed/rebuildable, not a backed-up production VM |
| Storage | SSD root/appdata; guest-local ext4 photos/files on `tank` ZFS mirror; replaceable media on private NFS |
| Access | Public HTTPS/game ingress targets VM100; manual-client `home.arpa` DNS works |
| Power | Populated physical UPS shutdown/output-cut and automatic power-return recovery passed |
| Monitoring | Local Grafana/Prometheus/Loki, six scrape targets and ntfy alert delivery accepted; external Kuma retained |

Sure was added on 2026-11-18, including web, Sidekiq, PostgreSQL16 and Redis8.
Its public route is `https://budget.han-diatonic.uk`; onboarding is closed and
the first super-admin exists. Other migrated application data and bounded
GPU/client paths passed their recorded acceptance checks.

The current LAN remains `192.168.15.x`; VM100's DHCP lease is not reserved.
The future home-network/router cutover is separate deferred work, not an
already-applied address change.

## Backup coverage and schedules

**One active local B repository is temporarily accepted. There is no healthy
second repository or off-site copy.**

- B: 10 TB Toshiba, serial `19L0A0EDFHLG`,
  XFS UUID `d0347cdb-9c3b-41e8-88ce-498367a6f038`.
- A: serial `28W0A2QGFKQE`,
  XFS UUID `6d3f33cb-faaf-4497-8131-2f40f07cfbbd`, quarantined after recurring
  errors followed the disk across bays. A/tank copies remain offline, with no
  CT101 startup dependency. They are not accepted redundant protection.
- Native PBS protects VM100's OS, appdata and managed photos/files disks.
  Routine backups use `snapshot` mode and QGA filesystem freeze/thaw, without
  stopping containers or rebooting/stopping the VM. Database recovery replays
  WAL/journals; the cold SQL comparisons were acceptance work, not nightly jobs.
- The filesystem job protects host/PBS recovery configuration and collected
  VPN/HA, `router-srt` and `router-krm` archives, with source-age checks.
  Inactive `router-trvl` / planned `router-evn` collection is excluded by explicit
  owner approval. Its 25 old archives remain; no current coverage is claimed.
- Replaceable media and manual/rebuildable VM102 are outside this coverage.
  Original photos/files datasets, migration copies, legacy Restic/PBS history
  and the Unraid USB remain preserved; historical staging is not live authority.
- Restic is not part of routine backup operation. Google Drive was abandoned
  after account loss; its incomplete seed is not recoverable protection.
  Backup encryption is not enabled by owner decision.

Enabled schedules, all **Asia/Yerevan**:

| Job | Schedule |
| --- | --- |
| VM100 native PBS snapshot | Daily 02:00 |
| PBS prune | Daily 07:00 |
| Filesystem backup / collector | Daily 07:15 |
| PBS garbage collection | Daily 08:00 |
| PBS verification | Sunday 10:00 |

The local target RPO is 24 hours. Enabled timers and accepted manual points do
not establish that a later scheduled cycle has run successfully.

## Verified acceptance

The latest recorded manual acceptance is **2026-11-19**:

- VM point: `vm/100/2026-11-19T11:32:30Z`.
- Host/collector point: `host/pve-recovery/2026-11-19T11:39:20Z`.
- Full B native image restoration and isolated boot/data recovery passed.
  Three real files, Vaultwarden SQLite, four PostgreSQL clusters / 305 tables,
  and CouchDB database/document counts matched their captured references.
  The clone had no NIC or GPU passthrough; production's 39 containers stayed up.
- Host bootstrap extraction, pmxcfs integrity, PBS credential identity and full
  collector checksum/metadata comparisons passed, including current-source
  freshness. All 25 inactive-router archives retained their hashes/metadata.
- B's persisted 120-minute idle policy reached natural standby and woke through
  a real live backup without observed SATA/I/O errors or production reboot/
  container-start changes. Native PBS maintenance alert delivery passed.
- Owned test VMs900/901/902 and their proof fixtures were removed after recovery
  acceptance. Original datasets and backup histories were not deleted.

Evidence root: `/root/migration-pbs-b-primary-20261117T212001Z`, including
`restore-b-boot.COMPLETE.json`, `idle-wake.COMPLETE.json` and
`final-acceptance.COMPLETE.json`. Private SQL/CouchDB receipts are retained.
Earlier failed attempts, historical schedules, measured outputs and offline
gate results remain in the [checkpoint archive](archive/migration-checkpoints.md).

The obsolete Unraid deployer/templates and empty inventory group are retired.
Detailed migration records are archived; keys and the legacy Restic password
remain. This repository cleanup does not deploy, revoke keys or delete data.

## Remaining risks and next actions

1. Establish and independently restore-test a healthy second copy and an off-site
   copy. Keep A quarantined pending a separately approved hardware decision;
   successful integrity reads did not clear its recurring reliability fault.
   Preserve existing copies, old recovery history and the Unraid USB.
2. Observe subsequent scheduled VM/file and maintenance cycles; monitor backup
   age, source-archive generation/freshness, capacity and alert delivery. The
   Nov19 manual acceptance is not a claim about the next scheduled night.
3. Restore inactive-router collection only when the source is available and
   owner-approved; retain its historical exports until then.
4. Complete the separately planned router/LAN cutover and stable VM reservation.
   Until then, local DNS is manual-client only; do not claim whole-LAN DHCP/DNS
   forwarding or move management exposure to the LAN.
5. Personal sign-ins, 2FA/Telegram/LiveSync clients, playback/HDR quality, peak
   load and low-battery reserve discharge remain unproved. Availability-only
   cutover acceptance was explicit; external MQTT remains unavailable. Do not
   reset credentials or enable recording/detection/HWA to bypass these limits.

## Guides and historical evidence

- Current operation: [host](pve-host.md), [Docker](docker-stacks.md),
  [backups/recovery](backups-proxmox.md), [monitoring](monitoring.md),
  [OpenWrt](openwrt.md).
- Dated evidence: [complete status history](archive/migration-checkpoints.md),
  [migration/cutover](archive/proxmox-migration.md),
  [backup cutover](archive/backup-cutover.md),
  [legacy Unraid backups](archive/backups-unraid.md).

Historical commands and gate counts describe their recorded checkpoints only.
They are not deployment instructions or newly executed verification.
