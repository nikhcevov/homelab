# Docker stacks

[Repository overview](../README.md)

Sources: [compose definitions](../compose/), [guest baseline](../roles/docker_vm/),
[deployment role](../roles/compose_stacks/), [GPU role](../roles/nvidia_guest/),
[Docker variables](../inventory/group_vars/docker/compose.yml),
[host provisioning](pve-host.md#vm-and-gpu), [backups](backups-proxmox.md).

Guest baseline and authorized production deployment are applied.
See [current status](status.md) for real-machine evidence and remaining gates.
Run controller commands from the repository root.

## Storage boundary

| Guest path | Backing storage |
| --- | --- |
| `/var/lib/docker` | Guest root disk160G, `local-zfs` on host SSD |
| `/mnt/appdata` | Guest-local ext4 disk128G on SSD, serial `homelab-appdata` |
| `/mnt/photos` | Managed3072 GiB ext4 `scsi2`, `tank/vm` via `tank-vm` |
| `/mnt/files` | Managed64 GiB ext4 `scsi3`, `tank/vm` via `tank-vm` |
| `/mnt/data` | External/private NFSv4.1, host `media/data`; excluded from backup |

This storage boundary is now deployed: all34 original containers resumed after
the immutable seed, frozen final delta and local mount cutover. Both data disks
have `backup=1`; staging mounts are gone. Configured healthchecks, four core HTTP
services, four PostgreSQL clusters and GPU checks passed. Originals are retained
for recovery. Full B-primary VM restore acceptance passed; A remains quarantined.
See [current acceptance](status.md) for dated evidence and protection limits.

PostgreSQL and SQLite files stay local to the guest. Neither placing NFS on the
same physical machine nor using `hard` makes it suitable for these databases.
Final PBS VM backups include root/appdata/EFI/photos/files, not external media.
Data disks are managed ZFS volumes, never raw physical-disk passthrough.

The appdata initializer requires explicit `docker_vm_initialize_appdata=true`,
the exact SCSI serial, no partitions/signatures and an entirely zero-filled
new device. It never formats a restored/unknown disk. The PVE device-ID alias
is `/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi1`; the serial is checked
independently. The filesystem label is `HOMELAB_APPDATA`.
Mount tasks create missing mountpoints themselves. Never chown/chmod an already
mounted appdata/NFS root as part of directory setup: that changes restored data
ownership. The full baseline rerun preserves the original numeric IDs and modes.

Photos/files use actual aliases
`/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi2` and
`/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi3`; independently validate
serials `homelab-photos`/`homelab-files`, sizes and ext4 labels
`HOMELAB_PHOTOS`/`HOMELAB_FILES`. The serial is not the by-id filename.
See [guest disk authority](../inventory/group_vars/docker/docker_vm.yml).
`--tags docker_vm_data_prepare` inspects/prepares only these disks without
replacing production NFS mounts. Initialization additionally requires explicit
`-e docker_vm_initialize_data=true` and parent-proven fresh allocation; it is
not a request to scan3 TiB of zeros or format unknown/restored volumes.
Both current disks are already initialized: omit that flag.
After writer pause, final comparison and explicit NFS unmount, use
`--tags docker_vm_data_cutover` to mount the existing local filesystems.
Do not run the untagged target baseline during the live seed.

`/mnt/data/torrents` and `/mnt/data/media` remain one dataset, preserving Arr
hardlinks and atomic renames. Preserve numeric ownership during restoration;
`99:100` applies to selected applications, not every database or Minecraft tree.

## Baseline and authorization

`playbooks/docker.yml` configures base packages, operator/root keys, local and
private media mounts, SSH/Tailscale, Docker and GPU.
Its first run uses the verified VM LAN address until Tailscale is joined:

```bash
ansible-playbook playbooks/docker.yml --limit docker-1 --force-handlers -e ansible_host=192.168.15.49 -e tailscale_auth_key= -e docker_vm_initialize_appdata=true -e compose_data_restored=false
```

This is not an application deployment. `compose_data_restored` defaults false.
The new128 GiB disk has now passed the full zero-data check and was initialized;
omit the initialization flag on later runs. If the manual Tailscale gate stops
the play, run `sudo tailscale up --hostname=docker-1 --accept-routes`, approve
the displayed URL, disable that machine's key expiry, then rerun the baseline
with `-e tailscale_auth_key=`. The old unattended join key must not be retried.
Unattended security updates remain enabled; unattended reboots stay disabled
during migration/restoration. Kernel/driver activation reboots are explicit.

Docker's systemd unit requires every real mount and both startup markers:

- `/mnt/appdata/.homelab-restored`: created by the operator only after data
  restoration and the fail-closed comparison gate.
- `/etc/docker/homelab-compose-authorized`: written only after explicit Compose
  authorization, validated mounts and successfully rendered configuration.

These separate markers stop a baseline package installation or guest reboot
from starting empty applications. Cold appdata restoration and full comparison
passed before the operator authorized startup. Both markers now exist; Docker
is active. Temporary migration access was removed.

For application-only reconciliation, without baseline packages/driver reboots:

```bash
ansible-playbook playbooks/docker.yml --limit docker-1 --tags compose -e compose_data_restored=true
```

During controlled startup, select one stack explicitly:

```bash
ansible-playbook playbooks/docker.yml --limit docker-1 --tags compose -e compose_data_restored=true -e '{"compose_stacks":["caddy-cloudflare"]}'
```

The physical-host refusal runs even with `--tags compose`. Before any Compose
mutation, strict local mount guards validate the expected devices, serials,
filesystems, labels, writable/noatime mounts and reject NFS/empty fallbacks.
Thus source-defined compose-only reconciliation is not a live-seed shortcut.
Selected deployment renders only that stack's extra/configuration files and
preserves existing configuration-parent ownership/modes. Missing parents alone are created.
Changed generated configurations force recreation of the affected stack:
atomic replacement of a single-file bind otherwise leaves the old inode mounted.
This can restart that stack's database too; an unchanged run does not recreate
containers. Actual Caddy changed/unchanged runs verified both paths.

Use the same explicit flag for desired Compose/config updates. A baseline-only
rerun does not remove an existing startup authorization. To withdraw it, stop
the workloads/Docker deliberately and remove the authorization before another
reboot; do not delete the data marker as a substitute for stopping writers.
`--check --diff` alone does not exercise discovery/reboots/startup semantics.

## GPU

The GTX1650 belongs to this VM; ASPEED stays with PVE. The source driver was
595.104.02. The guest uses signed NVIDIA Debian13 APT packages pinned to
595.112.07-1, not a runfile or an unproven downgrade to Debian550.
The role installs the vendor's exact-version
`nvidia-driver-pinning-595.112.07` package before the driver and removes the
old partial binary-name preferences file. This keeps GL/EGL/CUDA and kernel
dependencies on one source branch, including packages without `nvidia` in
their names. See NVIDIA's [APT version-locking guide](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/version-locking.html#apt).

The role selects paired cloud kernel/headers, DKMS and required repository
components, blacklists Nouveau, and reboots as needed before requiring the
selected active driver. Toolkit runtime configuration and Docker restart occur
before GPU stacks start. Real Immich CUDA inference and app-bundled Jellyfin
NVDEC/NVENC overlapped successfully in a bounded smoke check. This is not peak
capacity or HDR-quality proof. The real4 GiB VRAM limit remains; `nvidia-smi`
alone is not application acceleration proof.
Do not change to a driver branch that drops Turing support without explicitly
changing this hardware decision.

## Stack and configuration ownership

The authoritative deployment list remains
[`compose_stacks`](../inventory/group_vars/docker/compose.yml).
Frigate, LiteLLM, Scrutiny, and the Homelable MCP container are removed from
this Docker VM. Their stacks, Caddy routes, secrets, containers, and retained
data are gone. Do not revive the stopped StirlingPDF container or legacy HAOS
guest merely because their files were preserved.

Each stack has a static `compose.yaml` and vaulted `.env.j2`. Container memory
ceilings are set per service. They are hard caps, not reservations; the host can
still overcommit. The current values were chosen from cgroup `memory.peak` with
headroom; re-measure with `docker stats` before tightening. Peak-sensitive
services are Paperless, FlareSolverr, Immich ML, Jellyfin and Minecraft. Source
application images are pinned to audited digests, including Paperless2.20.15 and Immich3.1.0;
PostgreSQL14/18 majors and their data-directory layouts are preserved. An OS/
driver transition does not authorize an application/database-major upgrade.
Update those independently after migration and restore proof.

Code-owned Immich extension YAML is deployed beside its Compose file, not into
appdata. Sanitized Caddyfile/home/public routing templates are versioned;
private domain/email values and credentials remain vaulted.
Caddy's old Unraid management route was removed, not redirected to PVE.

Immich waits for the vendor PostgreSQL healthcheck and Redis health; Paperless
waits for its PostgreSQL18 readiness check. Paperless's generated origin remains
HTTP to match its actual `home.arpa` Caddy route. Vaultwarden keeps restored
closed-signup behavior. Homelable's CORS permits the new Docker guest, not the
old physical-host application address.

Homelable's pinned Nginx frontend uses the code-owned
[`nginx.conf.template`](../compose/homelable/nginx.conf.template), mounted over
the image's input template rather than its generated configuration. Its shared
upstream resolves Docker DNS at runtime: independently restarted containers need
not follow Compose dependency ordering. The original static resolution caused two
frontend startup exits when `backend` was still absent. The replacement started
without a backend, preserved all six proxy URI paths and followed a changed
backend IP without restart in an isolated same-image proof. Production UI and
proxied OpenAPI returned200; the real sign-in form rendered without browser errors.

Sure is a four-container Rails stack: `web`, a Sidekiq `worker`, PostgreSQL16 and
Redis8. Images are digest-pinned. It publishes only loopback port3010 because
Grafana owns3000. Caddy serves the internal `https://sure.home.arpa` with its
local CA and the public `https://budget.<public-domain>` with an ACME
certificate. The public site adds HSTS and `X-Robots-Tag: noindex, nofollow`;
edge SNI `budget.<public-domain>` forwards to `docker-1:443`. The public DNS
record must be a DNS-only A record for the edge address; Cloudflare proxying
would terminate TLS and bypass the L4 SNI route. `RAILS_ASSUME_SSL` and
`RAILS_FORCE_SSL` are both true, so session cookies carry Secure, HttpOnly and
SameSite. Clients using the internal name must trust
`/mnt/appdata/caddy/data/caddy/pki/authorities/local/root.crt`.
Caddy uses a code-owned `/etc/resolv.conf` with public resolvers because the
router resolver returns FORMERR for ACME DNS-01 zone discovery.
Memory is deliberately constrained: `RAILS_MAX_THREADS=2` (Puma two threads;
Sidekiq one default plus one AI lane), jemalloc `narenas:2` with one-second dirty/
muzzy decay, PostgreSQL `shared_buffers=64MB`/`max_connections=20`, and Redis
`maxmemory=64mb`. Production RSS measured about web380–470 MiB, worker350 MiB,
PostgreSQL60 MiB and Redis21 MiB; the 640m web cap leaves headroom for request
spikes. Caps are web640m, worker768m (the worker needs headroom for a first
large import), PostgreSQL256m and Redis128m. Sure has no app-level backup
service here: PBS VM images cover
`/mnt/appdata/sure`, including PostgreSQL, and QGA freeze/thaw requires WAL
replay. `SECRET_KEY_BASE` and the three Active Record encryption keys are
vaulted and must never change after data exists; rotating them makes encrypted
provider tokens unreadable. The first super-admin exists and
`sure_onboarding_state` is `closed`; registration redirects to login. WebAuthn
relying-party and allowed-origin values are pinned to the public hostname, so
register a passkey before relying on public access. Do not change the public
hostname after passkeys exist without re-registering them.

Minecraft retains MC26.1.2, Fabric loader0.20.1 and launcher1.1.2. Start Caddy
before Minecraft: `PACKWIZ_HOST` maps the canonical HTTPS pack hostname to the
Docker host gateway, preserving SNI/certificate validation without early edge
cutover. Minecraft uses explicit Cloudflare DNS resolvers: inherited DNS
returned FORMERR for the pinned helper's Maven EDNS queries. Four uncached
same-image probes succeeded with the override and unchanged installer hash;
no global resolver/router change or expiring cache workaround is used.

## Image updates

Every `image:` is pinned as `repository:tag@sha256:digest`. The digest is
authoritative; the tag makes the running release readable and lets update
tooling compare versions. Keep both. A tag alone would make the running image
depend on a mutable registry pointer, and a digest alone hides the release and
prevents version-aware updates.

Detection is delegated to [Renovate](https://docs.renovatebot.com/) through
[`renovate.json5`](../renovate.json5). Install the
[Mend Renovate app](https://github.com/apps/renovate) on the GitHub repository
once. It maintains one **Container updates** issue (the
Dependency Dashboard) and opens grouped PRs per stack. Major updates are
disabled; database and application majors need their own backup and migration
check. Renovate changes only `compose/**/compose.yaml` and never deploys.
PRs are scheduled daily before 06:00 Europe/Moscow.

Review and merge the PR, then apply only the affected stack:

```bash
ansible-playbook playbooks/docker.yml --limit docker-1 --tags compose \
  -e compose_data_restored=true \
  -e '{"compose_stacks":["media"]}'
```

The role copies the changed Compose file; `docker compose up -d` pulls the new
digest and recreates only changed services. Do not use `docker compose pull` on
the host as an update mechanism: the digest pin wins over a moving tag, so a
pull without a source change does nothing.

Manual bump when Renovate is unavailable:

```bash
docker buildx imagetools inspect ghcr.io/seerr-team/seerr:v3.5.2
```

Copy the printed `Digest:` into the tag+digest reference, run the Compose gate,
merge, and deploy the stack as above. `docker manifest inspect` shows manifests
but does not print the registry digest in the form the pin needs.

The tag must describe the digest. Some vendors rebuild the same release and move
the tag; Renovate then opens a digest-only PR for that release. Review it like
any other image change. Roll back by reverting the pin and redeploying the same
stack. An older image may not read a database already upgraded by a newer one;
restore the pre-update backup in that case. See [Recover](#recover).

## Networking

- VM private storage is `.2`, host `.1` on host-only `vmbr1`. LAN DHCP changes
  cannot change the NFS endpoint. Tailscale accepts the existing remote-site
  subnet routes; route approval/ACLs remain required.
- Caddy retains host networking and loopback upstreams. Proxied services publish
  to loopback unless direct access is deliberate. Its admin API is explicitly
  `localhost:2019`, not a LAN management surface.
- Minecraft, torrent peer ports and discovery traffic stay direct. Jellyfin HTTP
  remains direct for discovery clients. Loopback publication is not authentication
  for routes that Caddy itself exposes; review the intended audience per route.
- Technitium publishes TCP and UDP53. The role disables resolved's stub listener
  only when that unit exists; a `127.0.0.53` listener does not make wildcard53 free.
  The host resolver must not depend on a not-yet-started DNS container.
- Arr download/indexer integrations were audited: Sonarr uses `qbittorrent` and
  `prowlarr`; Prowlarr applications/proxy already use service DNS names. Preserve
  these names rather than introducing host LAN-address dependencies.
- Private edge HTTPS/Minecraft/voice upstreams target `docker-1` with its trusted
  backend tag, not the physical `great-hornbill` host. Keep public routing and
  [tailnet endpoint identity](tailscale.md) aligned; LAN DNS alone cannot retarget ingress.

### Stable LAN identity and local DNS

The current LAN remains `192.168.15.0/24`, gateway/DHCP server `192.168.15.1`.
VM100's `net0` MAC is `BC:24:11:36:00:01`; its observed `192.168.15.49`
is a dynamic24-hour lease, **not a reservation**. The guest retains cloud-init
Netplan/systemd-networkd and `ipconfig0=ip=dhcp`; no assumed-free static IP was set.

After the `router-evn` cutover ([OpenWrt](openwrt.md#home-router-router-evn))
the home LAN is `192.168.102.0/24` with gateway/DHCP `192.168.102.1`; VM100's
`192.168.102.49` becomes a DHCP reservation and the router forwards DNS to it,
so clients can return to DHCP. Until that cutover the addresses above are
current.

On2026-11-15 the owner confirmed no current GPON-router administrator access
and explicitly chose temporary manual DNS on selected PCs until router replacement.
Configure those clients with **only `192.168.15.49` as DNS**; do not add the
router/public DNS as an alternate that cannot resolve the local zone.
No hosts file or client network profile was changed by this migration step.
The current controller still inherits router DNS alongside its manual VM DNS;
that fallback is not reliable local-zone configuration for other clients.
If the VM lease changes, update the client DNS address and authoritative A record.

Using the owner-supplied existing administrator password through a loopback-only
SSH tunnel, the supported Technitium API migrated only `home.arpa`:

- `docker-1.home.arpa` A → the current VM address, TTL300.
- `*.home.arpa` CNAME → `docker-1.home.arpa`, TTL300; the explicit old `unraid` A was removed.
- Home-zone NS/SOA now name the real in-zone Docker identity, not an old container ID;
  SOA contact/timers were preserved and its native serial increased.

Unrelated `lab` records were unchanged. Existing admin credentials and global
DNS settings were not reset. The temporary login session was logged out,
the supplied private secret file deleted, and the temporary tunnel closed.

Direct UDP/TCP DNS passed for the VM and four application names. After a resolver
cache flush, ordinary client `getent ahostsv4 jellyfin.home.arpa` returned `.49`,
and ordinary `curl --noproxy '*' -L http://jellyfin.home.arpa/` reached HTTP200
from `.49`, without `--resolve` or hosts overrides. External recursion also passed
over UDP/TCP. Managed-browser `.arpa` navigation was blocked by its client policy;
no rendered Jellyfin UI, personal sign-in or playback claim follows from HTTP200.

Router `.1` still returns NXDOMAIN for the zone and advertises only itself via
DHCP option6. **Unconfigured ordinary LAN clients are not fixed.** After router
access/replacement, create a real reservation for the exact VM MAC, then prefer
conditional forwarding of `home.arpa` to Technitium. If advertising Technitium
through DHCP instead, verify external recursion and keep the VM's boot resolver
independent of its own not-yet-started DNS container; avoid forwarding loops.
Review the accepted tailnet route before the deferred LAN-subnet migration.

Private rollback/acceptance evidence on PVE:
`/root/migration-automation-20261114T195553Z`, including
`local-dns/zones.before.tar`, `home-zone.api.before.json`,
`home-zone.api.after.json` and `local-dns.COMPLETE.json`.
Restore records through supported administration, not binary edits in a running
server. Do not expose DNS/admin publicly or add a physical-PVE proxy workaround.

## Secrets and databases

Rendered `.env` files and configurations are root-only; sensitive Ansible tasks
use `no_log`. Vault encryption does not by itself make dotenv values literal:
JSON quoting/dollar escaping and URI percent-encoding are applied separately.
The Compose gate exercises dollar/braces/quote/backslash roundtripping with
synthetic values and never decrypts production vaults.

Sure requires `vault_sure_secret_key_base`, `vault_sure_postgres_password`, and
the three `vault_sure_active_record_encryption_*` keys. The secret key and
encryption keys are immutable once data exists; changing any of them makes
encrypted bank/provider tokens unreadable. The first super-admin is created in
the UI while onboarding is open.

Paperless receives explicit PostgreSQL engine/application password and polling
for its consume directory (historically NFS, local files disk after cutover).
The audit confirmed86 documents in its actual PostgreSQL database; a new empty
SQLite installation is not a migration success.
Its pinned2.20.15 polling setting is `PAPERLESS_CONSUMER_POLLING=30`.

Order-manager's audited application URL password matched its initialization
password and the vault. The derived, encoded URL therefore preserves the source
credential; the obsolete duplicate URL secret was removed. Existing database
role passwords are never reset merely by changing `POSTGRES_PASSWORD`.

Immich had zero active external libraries at audit, so dropping the
`/toshiba` import mount does not remove an active configured library. Preserve the source disk separately if it contains
unimported files; an application query cannot classify unrelated disk contents.

## Verify

```bash
python tests/check_compose.py
ssh docker-1 'findmnt /mnt/appdata /mnt/photos /mnt/files /mnt/data'
ssh docker-1 'nvidia-smi'
ssh docker-1 'docker ps --format "table {{.Names}}\t{{.Status}}"'
ssh docker-1 'docker exec sure-web curl -fsS http://127.0.0.1:3000/up'
ssh docker-1 'docker stats --no-stream --filter name=sure- --format "table {{.Name}}\t{{.MemUsage}}"'
curl --cacert /path/to/caddy-root.crt -fsS https://sure.home.arpa/up
curl -fsS https://budget.han-diatonic.uk/up
curl -sS -o /dev/null -w '%{http_code}\n' https://budget.han-diatonic.uk/registration/new
```

Exercise restored state and real client paths: Paperless documents, Immich
originals/albums, Vaultwarden login, order-manager data, Arr queues/hardlinks,
Jellyfin playback and Minecraft. Test a
reboot, missing NFS and GPU concurrency before public
cutover. Parsing Compose and waiting for container health are not recovery proof.

## Recover

- Interrupted native PBS snapshot-mode backup: inspect the native task, guest
  agent freeze/thaw and database recovery. Routine jobs restart neither the VM
  nor containers. Confirm filesystems are thawed before retrying; retired cold
  backup helpers and their manifests are not the current recovery mechanism.
- Missing mount: restore the real device/dataset; never create an empty fallback
  and authorize Docker to make the boot pass.
- Broken update: restore compatible data/config or roll back the pinned image;
  an old image cannot necessarily read a database upgraded by a newer one.
- Caddy internal TLS site serving an expired cached certificate after a restore:
  remove `/mnt/appdata/caddy/certificates/local/<host>` and restart
  `caddy-cloudflare`; Caddy reissues from its local CA. Clients must trust
  `/mnt/appdata/caddy/data/caddy/pki/authorities/local/root.crt`.
- Lost guest/root SSD: use [native PBS recovery](backups-proxmox.md#ssd-loss-bootstrap). Keep the vault
  password independently offline; rendered environments help only if recoverable.
