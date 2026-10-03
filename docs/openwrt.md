# OpenWrt routers

[Repository overview](../README.md)

Sources: [openwrt.yml](../openwrt.yml), [openwrt-upgrade.yml](../openwrt-upgrade.yml), [router variables](../group_vars/routers/).

Run commands from the repository root.

Identical OpenWrt routers (`routers` group), managed end-to-end by `openwrt.yml` over the tailnet. Config is authoritative — roles deploy whole `/etc/config/*` files, manual `uci` edits get overwritten. Per-host deltas (LAN IP, exit-node flags) live in `host_vars/router-*.yml`.

Day-0 (manual, over LAN — no tailnet yet):

1. Flash OpenWrt, set root password.
2. Set the hostname to the inventory name (`router-srt`) and the LAN IP/subnet from the host's `host_vars` (`owrt_lan_ip`) — LuCI or `uci`, your choice. The roles will re-apply both authoritatively, but a correct hostname now means the tailnet node gets the right name on first join.
3. Add your SSH key to dropbear (`/etc/dropbear/authorized_keys`).
4. Drop the same public key into `files/ssh/` and reference it in `ssh_authorized_keys` (`group_vars/routers/ssh.yml`) — the role takes over `authorized_keys` authoritatively.
5. Check `owrt_lan_bridge_ports` (`group_vars/routers/network.yml`) against the hardware (`ip link` — DSA port names vary).
6. Point the inventory at the LAN directly, temporarily: `router-srt ansible_host=192.168.103.1 ansible_user=root`.
7. `ansible-playbook openwrt.yml --limit router-srt` — the `openwrt_tailscale` role installs tailscale and joins the tailnet itself (auth key from the vault); no manual `tailscale up`.
8. In the Tailscale admin console: disable key expiry, approve the subnet route and exit node.
9. Switch the inventory line back to the MagicDNS form (`router-srt ansible_host="router-srt.{{ tailnet_domain }}" ...`) — from now on management is tailnet-only.

A fresh router has no Python: the play starts with `gather_facts: false` and `openwrt_common` installs full `python3` via `raw` (apk), then gathers facts.

**Exit nodes:** set `tailscale_advertise_exit_node: true` in the router's `host_vars` and re-run `openwrt.yml` (role passes `--advertise-exit-node`, firewall gets `tailscale → wan` forwarding). Two one-time admin-console steps remain: approve the exit route and disable key expiry. No automatic failover — clients pick a node explicitly; place nodes at different sites for real redundancy.

**Exit-node client gateway** (inverse: a whole LAN behind an OpenWrt box exits via a chosen node): set `tailscale_exit_node: <node>` (+ `tailscale_exit_node_allow_lan_access: true`). The firewall role renders `lan → tailscale` masquerade automatically. Switch nodes by changing the var and re-running, or ad hoc: `tailscale set --exit-node=...`.

**Full-tunnel exit node + kill switch** (router-trvl): with `tailscale_exit_node` set, tailscaled's blanket `5270: from all lookup 52` sends the whole LAN through the exit node (router-srt). The kill switch is at the firewall zone level: `owrt_firewall_lan_wan_forwarding: false` removes the `lan → wan` forwarding entirely, so a dead tailscaled or exit node means no internet at all — never a silent WAN fallback. DNS is pinned to the exit site's resolver (`owrt_dns_servers: [100.77.53.118]`, dnsmasq on router-srt over the tailnet) so resolver egress and CDN localization match the exit location. For per-device policy routing instead, `owrt_network_rules` renders netifd `ip rule`s that slot in front of `5270`.

**Upgrades:** daily checks are notify-only (`openwrt_upgrades` → ntfy). To apply: `ansible-playbook openwrt-upgrade.yml` (apk packages); add `-e owrt_firmware_upgrade=true` to check firmware via `owut`. When a different available version is detected, the play starts the upgrade asynchronously and returns without waiting for completion; the router **reboots**. Confirm it comes back before re-running `openwrt.yml` if configs drifted. See the [upgrade playbook](../openwrt-upgrade.yml).

**Wi-Fi:** opt-in per host via `owrt_wireless_radios` (`group_vars/routers/wireless.yml` documents the format; radio `path` values are device-specific — copy them from the stock `/etc/config/wireless`). The PSK lives in the vault (`vault_wireless_psk`). The deploy is authoritative: uplink sta interfaces added on the road (travelmate, hotel Wi-Fi) get wiped on the next run — keep those ad hoc.

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

Notes: changing `owrt_lan_ip` drops a LAN-based SSH session mid-run — manage over the tailnet. For Kuma DNS monitors, use the router's LAN IP through its advertised subnet route (approve the route in the admin console), and set `owrt_dns_localservice: false` to allow queries from non-local clients.

Dropbear is configured to listen on all interfaces for tailnet management, not only LAN; WAN access is controlled by the firewall. Its binding is defined by `ssh_dropbear_interface` in [router SSH variables](../group_vars/routers/ssh.yml). DNS listener settings are defined in the [dnsmasq template](../roles/openwrt_network/templates/dhcp.j2); do not infer them from the SSH binding.

## Reserve SD card

`router-alm` names an image written to a reserve SD card with day-0 setup, kept for use if `router-srt`'s active SD card fails. Its reserved LAN address is `192.168.101.1`. It is a bootstrap starting point, not a copy of `router-srt`'s current configuration or a fully managed spare.

The image remains outside the active inventory and backup collection; no desired-state overrides are defined in `host_vars/router-alm.yml`. Booting it does not automatically restore the current deployment. Use the day-0 procedure above and the current `router-srt` configuration to prepare the replacement; merely uncommenting `router-alm` in inventory is not a recovery procedure.

Related guides: [Tailscale](tailscale.md), [monitoring](monitoring.md), and [router backup collection and restore](backups-unraid.md).
