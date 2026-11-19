# OpenWrt routers

[Repository overview](../README.md)

Sources: [playbooks/openwrt.yml](../playbooks/openwrt.yml), [router variables](../inventory/group_vars/routers/).

Run commands from the repository root.

The `routers` group mixes hardware site routers (`router-krm`, `router-srt`, `router-evn`) with one x86-64 gateway VM (`router-gw`), all managed end-to-end by `playbooks/openwrt.yml` over the tailnet. Config is authoritative — roles deploy whole `/etc/config/*` files, manual `uci` edits get overwritten. Per-host deltas (LAN IP, exit-node flags) live in `inventory/host_vars/router-*.yml`.

Day-0 for a hardware router (manual, over LAN — no tailnet yet; the gateway VM has its own [day-0](#gateway-vm-router-gw)):

1. Flash OpenWrt, set root password.
2. Set the hostname to the inventory name (`router-srt`) and the LAN IP/subnet from the host's `host_vars` (`owrt_lan_ip`) — LuCI or `uci`, your choice. The roles will re-apply both authoritatively, but a correct hostname now means the tailnet node gets the right name on first join.
3. Add your SSH key to dropbear (`/etc/dropbear/authorized_keys`).
4. Drop the same public key into `files/ssh/` and reference it in `ssh_authorized_keys` (`inventory/group_vars/routers/ssh.yml`) — the role takes over `authorized_keys` authoritatively.
5. Check `owrt_lan_bridge_ports` (`inventory/group_vars/routers/network.yml`) against the hardware (`ip link` — DSA port names vary).
6. Point the inventory at the LAN directly, temporarily: `router-srt ansible_host=192.168.103.1 ansible_user=root`.
7. `ansible-playbook playbooks/openwrt.yml --limit router-srt` — the `openwrt_tailscale` role installs tailscale and joins the tailnet itself (auth key from the vault); no manual `tailscale up`.
8. In the Tailscale admin console: disable key expiry, approve the subnet route and exit node.
9. Switch the inventory line back to the MagicDNS form (`router-srt ansible_host="router-srt.{{ tailnet_domain }}" ...`) — from now on management is tailnet-only.

A fresh router has no Python: the play starts with `gather_facts: false` and `openwrt_common` installs full `python3` via `raw` (apk), then gathers facts.

**Exit nodes:** set `tailscale_advertise_exit_node: true` in the router's `host_vars` and re-run `playbooks/openwrt.yml` (role passes `--advertise-exit-node`, firewall gets `tailscale → wan` forwarding). Two one-time admin-console steps remain: approve the exit route and disable key expiry. No automatic failover — clients pick a node explicitly; place nodes at different sites for real redundancy.

**Exit-node client gateway** (inverse: a whole LAN behind an OpenWrt box exits via a chosen node): set `tailscale_exit_node: <node>` (+ `tailscale_exit_node_allow_lan_access: true`). The firewall role renders `lan → tailscale` masquerade automatically. Switch nodes by changing the var and re-running, or ad hoc: `tailscale set --exit-node=...`.

**Full-tunnel gateway + kill switch** (`router-gw`): with `tailscale_exit_node` set, tailscaled's blanket `5270: from all lookup 52` sends the whole LAN through the exit node (`router-srt`). The kill switch is at the firewall zone level: `owrt_firewall_lan_wan_forwarding: false` removes the `lan → wan` forwarding entirely, so a dead tailscaled or exit node means no internet at all — never a silent WAN fallback. DNS is pinned to the exit site's resolver (`owrt_dns_servers: [100.77.53.118]`, dnsmasq on router-srt over the tailnet) so resolver egress and CDN localization match the exit location. The node's own management traffic is pinned to the direct WAN with `owrt_network_rules`; only forwarded client traffic is forced into the tunnel.

## Gateway VM (router-gw)

`router-gw` is an x86-64 OpenWrt VM (VMID 102) on `great-hornbill`, not a hardware site router. Its only LAN client is the work laptop on the dedicated NIC `nic1`; the laptop gets DHCP/DNS from the VM and its entire internet path is the exit-node tunnel to `router-srt`. Nothing is installed on the laptop, and it has no route to the home LAN or the tailnet.

| Setting | Value |
| --- | --- |
| VMID / name | 102 / `router-gw` |
| CPU / RAM / disk | 2 vCPU / 1024 MB / the imported image (~126 MB, 79 MB free) |
| Firmware | SeaBIOS, serial console (`qm terminal 102`) |
| net0 | virtio, `vmbr0`, MAC `BC:24:11:72:00:01` (WAN) |
| net1 | virtio, `vmbr2` (LAN: the laptop port) |
| Boot | `onboot 1`, `startup order=2` |

`pve_host` owns `vmbr2` ([Proxmox host](pve-host.md)): `nic1` is its only port and it has no host address, so the host has no L3 path to the laptop. On a host without it, run `ansible-playbook playbooks/pve.yml --tags bootstrap --limit great-hornbill` first. Both I210s are single-device IOMMU groups, so passing `nic1` through instead of bridging it is possible and removes the host from the laptop's L2 domain entirely; the bridge is the default because virtio enumeration inside the guest is deterministic (`eth0` = net0, `eth1` = net1).

Image: `openwrt-25.12.6-x86-64-generic-ext4-combined.img.gz`, sha256 `f8538784d0288b4133a99ac2a68443e4922ffde6343e80df56a5882364b9d499`, from `downloads.openwrt.org/releases/25.12.6/targets/x86/64/`. Match the release to the site routers. The image has virtio-net and virtio-scsi built in, a serial console on `ttyS0`, and an **empty** `/etc/config/network`.

The VM is not provisioned by `pve_vm` (that role owns VM100 only); recreate it from this section after a PVE reinstall.

```bash
# on great-hornbill
cd /var/tmp
wget https://downloads.openwrt.org/releases/25.12.6/targets/x86/64/openwrt-25.12.6-x86-64-generic-ext4-combined.img.gz
sha256sum -c <<<"f8538784d0288b4133a99ac2a68443e4922ffde6343e80df56a5882364b9d499  openwrt-25.12.6-x86-64-generic-ext4-combined.img.gz"
gunzip -k openwrt-25.12.6-x86-64-generic-ext4-combined.img.gz
qm create 102 --name router-gw --memory 1024 --cores 2 --cpu host --bios seabios \
  --scsihw virtio-scsi-single --serial0 socket --vga serial0 \
  --net0 virtio,bridge=vmbr0,macaddr=BC:24:11:72:00:01 \
  --net1 virtio,bridge=vmbr2 --onboot 1 --startup order=2
qm importdisk 102 /var/tmp/openwrt-25.12.6-x86-64-generic-ext4-combined.img local-zfs
qm set 102 --scsi0 local-zfs:vm-102-disk-0 --boot order=scsi0
qm start 102 && qm terminal 102   # leave the console with Ctrl-O
```

Day-0 inside the VM — console only, because the controller is on the tailnet and this VM's LAN is not routed. The stock network config is empty; the firewall already defines the `wan` zone.

```bash
ip -br link   # eth0 = net0 WAN, eth1 = net1 LAN
uci set network.wan=interface
uci set network.wan.device='eth0'
uci set network.wan.proto='dhcp'
uci set network.wan6=interface
uci set network.wan6.device='eth0'
uci set network.wan6.proto='dhcpv6'
uci commit network && /etc/init.d/network restart
ping -c1 1.1.1.1 && nslookup openwrt.org

apk update && apk add tailscale tailscaled
/etc/init.d/tailscale start
tailscale up --hostname=router-gw   # open the URL; then disable key expiry in the console

# The stock firewall rejects input on unzoned interfaces, so the tailnet must
# be allowed before the playbook can reach dropbear. The role rewrites this
# file authoritatively on the first run.
uci add firewall zone
uci set firewall.@zone[-1].name='tailscale'
uci set firewall.@zone[-1].input='ACCEPT'
uci set firewall.@zone[-1].output='ACCEPT'
uci set firewall.@zone[-1].forward='REJECT'
uci add_list firewall.@zone[-1].device='tailscale0'
uci commit firewall && /etc/init.d/firewall restart
```

1. `ansible-playbook playbooks/openwrt.yml --limit router-gw -e owrt_update_check=false` over MagicDNS. The tailscale task enables `tailscale_ssh`, takes over port 22 and changes the node's host key: the run completes, then `ssh-keygen -R router-gw.<tailnet domain>`. From here fw4 closes the WAN input and management is tailnet-only.
2. Plug the laptop into `nic1`. The playbook has already deployed the /30 LAN (`10.99.0.1`, one DHCP lease), the kill switch and the exit-node client.

Verify from the laptop:

```bash
curl -s https://ifconfig.co/json   # router-srt's egress, not the home WAN
ping -c1 192.168.102.36            # must fail: no path to the home LAN
curl -o /dev/null -w '%{speed_download} B/s\n' \
  'https://speed.cloudflare.com/__down?bytes=50000000'   # large transfer completes
```

If small requests work but large transfers stall, the tunnel needs MSS clamping: the exit-node path is MTU 1280 and the LAN is 1500. The travel-router deployment ran without clamping, so try it before changing the shared firewall template — the fix is an `mtu_fix` on the `lan` zone, not an ad-hoc `iptables` rule the next deploy wipes.

Kill-switch check: run `tailscale set --exit-node=` on the VM, confirm the laptop loses internet, then re-run the playbook. With `lan → wan` disabled there is no path around the tunnel.

Known behaviour: the LAN advertises a ULA/RA like every role-managed router, so the laptop may try IPv6 first; egress follows the tunnel when the exit node has IPv6 and falls back otherwise. The travel-router deployment had the same shape.

## Home router (router-evn)

`router-evn` is the Cudy TR3000 that used to travel as `router-trvl`; after the 2026-11-15 reset it is the home router at the `great-hornbill` site. No exit-node client and no kill switch — it is the ordinary gateway for the home LAN, and the work laptop's tunnel is separate (`router-gw`).

- LAN `192.168.102.0/24`, gateway/DHCP/DNS `192.168.102.1`. `100` is the krm site, `101` the `router-alm` reserve image, `103` `router-srt`'s advertised LAN — never reuse them.
- Reservations: `docker-1` `.49` (MAC `BC:24:11:36:00:01`) and `router-gw`'s WAN `.50` (MAC `BC:24:11:72:00:01`); the PVE host keeps its own static `.36`.
- DNS: dnsmasq forwards everything to Technitium on `docker-1` (`.49`), which owns `home.arpa`; the router only claims `evn.lan` for DHCP names. LAN DNS therefore depends on `docker-1` being up.
- Tailnet: advertise `192.168.102.0/24` (approve the route once), no exit-node advertisement.
- Wi-Fi: the same MT7981 radios and the existing SSID/PSK; regulatory domain `AM`. Change the SSID in `host_vars` if the home AP should not be called `trvl`.
- The ISP router stays in front (bridge mode when it supports it); a double NAT does not change the rest of the scheme.

Day-0 is the hardware procedure above, with the reset as the flash step:

1. Reset the TR3000, set hostname `router-evn`, LAN `192.168.102.1/24`, add the SSH key.
2. Delete the stale `router-trvl` node in the Tailscale admin console before joining, otherwise MagicDNS registers the new install as `router-evn-1`.
3. `ansible-playbook playbooks/openwrt.yml --limit router-evn -e owrt_update_check=false`, then approve the subnet route in the console.
4. A re-flash creates a new tailnet node and IP — update any enabled collector entry in `roles/pve_backup/defaults/main.yml` and reapply the backup role. Planned/offline routers remain excluded until explicitly enabled.
5. Move the PVE host to `192.168.102.36/24`, gateway `.1`. Management is tailnet-only, so a wrong LAN address cannot lock you out; verify with `ip -br a` and the tailnet. VM100 keeps `.49` through the new reservation; update its authoritative `A` record in Technitium if it still carries the old address.

**Upgrades:** daily checks are notify-only (`openwrt_upgrades` → ntfy). Normal deployment and `--tags all` do not run maintenance upgrades. There is **one** upgrade path: `ansible-playbook playbooks/openwrt.yml --tags upgrade`. It resolves the installed package manifest with `owut check`, then has the Attended Sysupgrade server build a complete image and installs it with `sysupgrade` — kernel, kmods, base system and your packages all from one build. `apk upgrade` is deliberately not used: it mutates the running system package by package and can leave core daemons (tailscale, netifd, ucode/libubox) half-upgraded, which is how `router-krm` lost its IP stack. For a single leaf package, `apk add -u <pkg>` on the router is acceptable; never blanket-upgrade. The play is fire-and-forget: when a different version is available it starts `owut upgrade` asynchronously and returns; the router **reboots** and the **SSH session drops**. The new image can change netifd, firewall or tailscale behaviour, so **re-run `playbooks/openwrt.yml --limit <router>` once the node rejoins the tailnet** — skipping that leaves the gateway LAN without internet (the kill switch has no fallback). See the explicit maintenance play in the [canonical playbook](../playbooks/openwrt.yml).

**Remote recovery (Tailscale SSH):** `tailscale_ssh: true` in a host's vars makes tailscaled terminate port 22 on the tailnet in userspace. Unlike dropbear it survives a broken `tailscale0`, broken kernel policy rules or a firewall that failed to load — the 2026-11-06 `router-krm` lockout. It requires the `ssh` block in `files/tailscale/policy.json` (without it every connection is denied; `dst` cannot be a wildcard, so it uses `autogroup:self`) and replaces key-based dropbear for tailnet clients, changing the node's SSH host key. Enable one router at a time with `-e owrt_update_check=false` — `tailscale set --ssh` takes over port 22 immediately, so any task after the tailscale role would hit the new host key — then `ssh-keygen -R <tailscale-hostname>.<tailnet_domain>` before the next run. LAN SSH keeps using dropbear. Order matters: apply the policy first, then enable the flag.

**Wi-Fi:** opt-in per host via `owrt_wireless_radios` (`inventory/group_vars/routers/wireless.yml` documents the format; radio `path` values are device-specific — copy them from the stock `/etc/config/wireless`). The PSK lives in the vault (`vault_wireless_psk`). The deploy is authoritative: uplink or test interfaces added by hand get wiped on the next run — keep those ad hoc.

| Role              | Configures                                                                                    |
| ----------------- | --------------------------------------------------------------------------------------------- |
| openwrt_common    | python3 bootstrap (via `raw`), hostname, timezone, NTP, sysctl                                |
| openwrt_packages  | extra apk packages (`owrt_packages`)                                                          |
| openwrt_ssh       | dropbear (key-only), root `authorized_keys`                                                   |
| openwrt_network   | `/etc/config/network` + `/etc/config/dhcp` (LAN bridge, WAN, DHCP, DNS)                       |
| openwrt_wireless  | `/etc/config/wireless` (radios + AP SSIDs, PSK from vault); opt-in per host                   |
| openwrt_firewall  | `/etc/config/firewall`, tailscale zone + subnet/exit forwarding, flow offloading, extra rules |
| openwrt_tailscale | tailscale via apk, tailnet auth, exit node (same var names as the Debian role)                |
| openwrt_upgrades  | daily notify-only update check (apk + owut) → ntfy                                            |

Notes: changing `owrt_lan_ip` drops a LAN-based SSH session mid-run — manage over the tailnet. For Gatus DNS checks, use the router's LAN IP through its advertised subnet route (approve the route in the admin console), and set `owrt_dns_localservice: false` to allow queries from non-local clients.

Dropbear is configured to listen on all interfaces for tailnet management, not only LAN; WAN access is controlled by the firewall. Its binding is defined by `ssh_dropbear_interface` in [router SSH variables](../inventory/group_vars/routers/ssh.yml). DNS listener settings are defined in the [dnsmasq template](../roles/openwrt_network/templates/dhcp.j2); do not infer them from the SSH binding.

## Reserve SD card

`router-alm` names an image written to a reserve SD card with day-0 setup, kept for use if `router-srt`'s active SD card fails. Its reserved LAN address is `192.168.101.1`. It is a bootstrap starting point, not a copy of `router-srt`'s current configuration or a fully managed spare.

The image remains outside the active inventory and backup collection; no desired-state overrides are defined in `inventory/host_vars/router-alm.yml`. Booting it does not automatically restore the current deployment. Use the day-0 procedure above and the current `router-srt` configuration to prepare the replacement; merely uncommenting `router-alm` in inventory is not a recovery procedure.

Related guides: [Tailscale](tailscale.md), [monitoring](monitoring.md), and [router backup collection and restore](backups-proxmox.md).
