# Backups → Unraid

[Repository overview](../README.md)

Sources: [unraid.yml](../unraid.yml), [homelab-backup-pull.sh.j2](../files/unraid/homelab-backup-pull.sh.j2), [restic-vault-backup.sh.j2](../files/unraid/restic-vault-backup.sh.j2), [restic-vault-check.sh.j2](../files/unraid/restic-vault-check.sh.j2).

Run commands from the repository root.

## Weekly schedule (Sunday-night chain)

One chain so the array wakes once a night and the `vault` pool disk only for restic:

| Time | Task | Where configured |
| --- | --- | --- |
| Sun 00:00 | Mover (cache→array; up to ~1 TB to drain, 4 h headroom) | Settings → Scheduler → Mover |
| Sun 04:00 | CA Appdata Backup (appdata + flash) into the `backup` share | plugin GUI |
| daily 05:00 | `homelab-backup-pull` (VPS archives + router configs) | User Scripts GUI (`0 5 * * *`) |
| Sun 06:00 | `restic-vault-backup` → vault pool (captures the fresh 04:00/05:00 data) | User Scripts GUI (`0 6 * * 0`) |
| monthly 08:00 (1st) | `restic-vault-check` — `restic check --read-data-subset=10%` on the vault repo (XFS pool: no scrub; random sampling does not guarantee full coverage in ten runs) | User Scripts GUI (`0 8 1 * *`) |
| monthly 08:00 | Parity check (day-of-month in the GUI, e.g. the 1st; for "first Sunday"/incremental use the Parity Check Tuning plugin) | Settings → Scheduler |

Restic must not scan while the mover works (renames mid-scan → spurious "file vanished" errors), hence the ordering.

Unraid **pulls** the configured hosts' backups over the tailnet ([collector template](../files/unraid/homelab-backup-pull.sh.j2), deployed into the User Scripts plugin by [unraid.yml](../unraid.yml); schedule set in the plugin GUI). Pull model on purpose — source hosts hold no Unraid credentials and cannot log into the collector through this backup setup. The rsync copies use `--delete`: source deletions propagate to the mirror, so retained restic snapshots are the separate recovery layer.

What gets pulled: `rsync` of `/opt/*-backup/archives/` from the VPS hosts (vpn/kuma, own 14-day rotation), `rsync` of `/backup/` from Home Assistant (`ha-krm`; its own automatic-backup retention applies — note HA encrypts backups by default, so the copies stay encrypted too: keep the encryption key in a password manager), and `sysupgrade -b` streamed over SSH from each router into dated tarballs (30-day retention). Every source is tracked in a state file: ntfy fires only on transitions (OK→FAIL alerts, FAIL→OK info).

Setup:

1. On Unraid: `ssh-keygen -t ed25519 -C "great-hornbill"` (default path, empty passphrase), put the pubkey in `files/ssh/great-hornbill.pub` — referenced by routers' `ssh_authorized_keys` and VPS `bootstrap_root_ssh_keys`.
2. One-time chicken-egg: authorize `starling.pub` on Unraid via `/boot/config/ssh/root/authorized_keys` (persists; `/root` is a ramdisk).
3. Fill in `RSYNC_SOURCES` / `ROUTERS` / `DEST` in the script template.
4. `ansible-playbook unraid.yml` (raw + base64 — Unraid has no Python), then set the schedule in Settings → User Scripts and run once manually.
5. Re-run `openwrt.yml` / `mon.yml` / `vpn.yml` so the great-hornbill key is authorized on the sources.
6. Home Assistant (`ha-krm`): install the _Advanced SSH & Web Terminal_ add-on, put `files/ssh/great-hornbill.pub` into its `authorized_keys` option, clear the password, and install `rsync` (`packages: [rsync]` add-on option). The [collector's `RSYNC_SOURCES`](../files/unraid/homelab-backup-pull.sh.j2) already includes `ha-krm`; verify its Tailscale IP and add-on username (currently `boss`), and that `sudo rsync` works without a password for access to root-owned `/backup`. Backups land in `/mnt/user/backup/homelab/ha-krm` and are included in the weekly restic backup of the `backup` share.

Restore: VPS DBs — copy the tarball back and follow the role's restore path (`vpn-restore.yml`); routers — upload in LuCI _Backup/Flash Firmware_ or `sysupgrade -r`.

## Local weekly copy → vault pool (restic)

The `photos` and `backup` shares are copied weekly into a restic repository on `vault`, a single-disk XFS pool (no parity, no shares — the disk spins down between runs). Sources are read via `/mnt/user/<share>` (FUSE union), so cache→array mover state is transparent; the source is strictly read-only, nothing is ever deleted from the shares.

For a new installation, provision a single-disk pool named `vault` with XFS in the Unraid GUI; [unraid.yml](../unraid.yml) deploys scripts and prerequisites, not the pool or its schedule. Do not reformat an existing backup pool to follow these setup instructions.

Script [files/unraid/restic-vault-backup.sh.j2](../files/unraid/restic-vault-backup.sh.j2), deployed by `unraid.yml` together with the pinned restic binary (stored at `/boot/extra/restic`, staged into `/usr/local/bin` at runtime — `/boot` is vfat+noexec) and the repo password (`/boot/config/restic/password`, root-only; master copy: `vault_restic_password` in the vault — keep another copy in a password manager). Retention: 8 weekly + 6 monthly snapshots (`forget --prune`); every run ends with `restic check` (metadata). Include list (see `BACKUP_PATHS` in the script): the `backup` share plus Immich `library/`, `upload/`, `backups/` (postgres dumps), `profile/`; Immich `thumbs/`/`encoded-video/` are regenerable and `frigate/` is skipped entirely. Tradeoff: new top-level folders are NOT protected automatically — the script logs a WARN for unexpected entries, so check the syslog after adding new services. Runs in the Sunday-night chain (table above). Data integrity: the pool is XFS (no checksumming/scrub), so [restic-vault-check.sh.j2](../files/unraid/restic-vault-check.sh.j2) runs monthly with `check --read-data-subset=10%`. Random subsets can overlap; ten runs do not guarantee that every pack was checked. Run a full `restic check --read-data` manually after SMART warnings or unclean shutdowns of the vault disk.

Restore: `cp /boot/extra/restic /usr/local/bin/restic && chmod 755 /usr/local/bin/restic`, then `export RESTIC_REPOSITORY=/mnt/vault/restic RESTIC_PASSWORD_FILE=/boot/config/restic/password` and `restic snapshots` / `restore latest --target ...` (details in the script header). After restoring Immich, re-run its thumbnail/transcode jobs to rebuild the excluded `thumbs/` and `encoded-video/`.

Related guides: [VPN backup and restore](vpn.md), [monitoring backup and restore](monitoring.md), and [OpenWrt router provisioning](openwrt.md).
