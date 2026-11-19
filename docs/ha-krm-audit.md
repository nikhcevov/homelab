# HA KRM audit

[Repository overview](../README.md)

Snapshot: 2026-11-16. Scope: `ha-krm` (Raspberry Pi 4B, 4 GB, HAOS 18.3,
HA Core 2026.9.4) and its Home Assistant stack. Read-only audit; the safe
remote changes already applied are listed below. This page is the checklist for
the remaining work that needs local/physical access or a planned maintenance
window. It is not a product/UX review.

## Weekend checklist

### Needs local access or power-cycle risk

1. **HAOS 18.3 -> 18.5 and HA Core 2026.9.4 -> 2026.11.1.** Take a manual
   backup first, keep local access, update OS then Core, verify add-ons,
   HACS/custom components and both Frigate cameras. A failed OS boot needs a
   physical power cycle.
2. **Tailscale add-on 0.30.6 -> 0.30.7.** This add-on caused the 2026-11-15
   outage (see below). Update only with local access; immediately verify
   `192.168.100.30:22/8123/443` from `router-krm`. If LAN access is lost, power
   cycle the Pi. Consider disabling the add-on watchdog or `accept_dns` if the
   flapping returns.
3. **Rotate the weak MQTT credential and add ACL.** Zigbee2MQTT currently uses a
   weak password configured in the add-on options. Change it in Mosquitto
   (`core_mosquitto`), Zigbee2MQTT, Frigate and the HA MQTT integration at the
   same time. Verify Zigbee2MQTT, Frigate and HA MQTT before leaving. Keep a
   local recovery path; a mistake breaks Zigbee/Frigate/HA MQTT.
4. **Backup retention and restore test.** Automatic backups run daily at 03:00
   with retention 3 and protected/encrypted storage. The external collector
   mirrors the same 3 copies. Raise retention to 7-14 and perform a real restore
   test; keep the encryption key outside the Pi.
5. **SMART, USB SSD, power and thermal.** `ha host disks` has no SMART data; the
   root is a USB-SATA SSD behind an ASMT bridge. Check `smartctl -a -d sat` from
   a Linux laptop, the official PSU, USB cables and cooling. Kernel logs, voltage
   alarms and temperatures are clean today, but the disk is the only component
   without telemetry.
6. **Zigbee channel only if needed.** Zigbee2MQTT is on channel 11; Wi-Fi is
   2.4 GHz channel 6. They are separated, but channel 11 overlaps Wi-Fi channel
   1 and neighbours. Do not change it without a reason; if interference appears,
   test channel 25 and keep the coordinator/network-key backups.

### HA UI / local maintenance, no power cycle expected

1. **Remove the ONVIF integration for the kitchen camera at
   `192.168.100.164`.** This is the compromised Dahua OEM camera under router
   quarantine; the integration still stores credentials and polls it. Remove it
   until the camera is factory-reset or replaced.
2. **Remove the dead ZHA integration.** It is enabled, uses the same Sonoff
   Zigbee 3.0 dongle as Zigbee2MQTT and has no entities. Keep Zigbee2MQTT.
3. **Trim the Frigate integration.** It creates 190 entities; many object/image/
   update entities are not needed. Keep the four camera entities and the
   detect/record switches. The historical 18k API errors were the old Unraid URL
   and the add-on restart window; current API calls are clean.
4. **Clean stale mobile-app and disabled entities.** There are 7 mobile-app
   registrations, 393 mobile-app entities and 493 disabled entities. Remove old
   phones/devices and review the 11 refresh tokens/10 users.
5. **Fix log noise.** `rele_bolshaia_spalnia_action` produces ~178 `Invalid event
   type` warnings; two Tuya cover motors report `%` with `illuminance`; the
   infrared template raises `LoggingUndefined`. `met.no`/`ntfy` timeouts and
   `front_yard` stream errors should be checked after the DNS/Tailscale work.
6. **Nginx/security follow-up.** Verify real client IPs after
   `use_x_forwarded_for`; inspect the Nginx `bad record mac` messages; restrict
   the unauthenticated HAOS observer on 4357 and MQTT on 1883 if not needed on
   LAN/tailnet; decide whether the running File editor add-on is still needed.
7. **Backup/retention and media.** Automatic backups include HA config/db, all
   add-ons and `media`, `ssl`, `share`. If Frigate recording is ever enabled,
   exclude Frigate media from backups.

### Deferred architecture

- **Caddy** can auto-renew but has no official HAOS add-on with Cloudflare
  DNS-01; the community `cinderblock/caddy-dns01` add-on is young. A separate
  Docker host/LXC with Caddy + Cloudflare DNS-01 is the cleaner option.
- **Cloudflare Tunnel** (`cloudflared`) removes certificate files and renewal
  from the Pi, but changes ingress; the `.uk` name currently resolves to the
  edge VPS (`194.87.254.116`), not Cloudflare.
- **Cloudflare Origin Certificate** is a 15-year no-renewal option only if the
  name is behind the Cloudflare proxy; it is currently DNS-only.

The weekly Let's Encrypt automation already removes manual renewal; these
architectural options are not required now.

## Audit snapshot

| Item | Value |
| --- | --- |
| Hardware | Raspberry Pi 4B, 4 GB, 4x Cortex-A72, USB SSD 111.8 GB |
| Disk | 12.7 GB used, 90.6 GB free; root on `/dev/sda` |
| HAOS / Core / Supervisor | 18.3 / 2026.9.4 / 2026.11.0; updates available |
| Load / RAM / swap | ~0.9; 1.9 GB used / 1.9 GB available; 502 MB swap, inactive |
| Thermal / power | 39.9 C; `rpi_volt` alarm 0; no undervoltage in dmesg |
| Network | 1 Gbps full, 0 errors/drops |
| Main consumers | Frigate 1.1 GB / 15.5% CPU; HA Core 460 MB; Zigbee2MQTT 105 MB; Tailscale 72 MB |
| HA registry | 979 entities (493 disabled), 32 config entries, 81 devices, 10 users |
| Database | 69 MB; 110k states; 463k statistics; SQLite WAL |
| Backups | 3 daily automatic, retention 3, protected; 9 add-ons at the audit snapshot + config/db + media/ssl/share (Get HACS has since been removed) |
| Certificate | Let's Encrypt `ha-krm.han-diatonic.uk`, valid to 2027-02-06 |
| Add-ons | Frigate 0.18.2, Zigbee2MQTT 2.14.3-1, Mosquitto 7.1.3, Nginx 4.5.1, SSH 24.2.1, Tailscale 0.30.6, Let's Encrypt 6.5.0 (one-shot), File editor 6.3.1 |

The Pi is not resource-bound: CPU/memory/IO pressure is low, the disk has 90 GB
free, and the CPU governor is `ondemand` at 1.3/1.5 GHz. Overclocking or zram is
not justified.

## Root cause of the 2026-11-15 outage

The host stayed up; HA Core, SSH, NGINX and Frigate containers did not restart.
The Tailscale add-on's Supervisor watchdog marked it unhealthy and restarted it
at 23:57, 00:22 and 00:30; its host-network iptables/MagicDNS/forwarding rules
left LAN TCP ports rejected while ICMP still worked. The 00:30 restart reached
the control plane (`health(warming-up): ok`) and restored access. This is why
the Tailscale update and local-access window are the first weekend item.

## Applied safely during the audit

- `configuration.yaml`: `recorder` excludes `camera.*`, `image.*`, `update.*`,
  `commit_interval: 5`; `http` trusts `172.30.32.0/23` and uses
  `use_x_forwarded_for`.
- `automations.yaml`: weekly `TLS: weekly certificate renew` (Sunday 03:30)
  starts `core_letsencrypt`, waits 10 minutes, then restarts
  `core_nginx_proxy`. Actions were tested; the certificate was not due.
- NGINX `client_max_body_size_megabytes` raised from 1 to 50; 443 with the
  `.uk` SNI returns 200.
- Stopped `Get HACS` add-on uninstalled.
- Configuration backups:
  `/config/configuration.yaml.bak-20261116T140433` and
  `/config/automations.yaml.bak-20261116T152739`.
- No changes to Tailscale, HAOS/Core, MQTT, Zigbee, ONVIF or Frigate.

## Procedure notes

### HAOS and Core update

1. `ha backups --raw-json` and confirm a fresh protected backup.
2. Update HAOS to 18.5, wait for the reboot, then Core to 2026.11.1.
3. Run `ha core check`; verify `ha apps`, HACS/custom components, Frigate API and
   all four Frigate cameras.
4. Keep the backup and local access until the next reboot passes.

### Tailscale update and verification

Update `a0d7b954_tailscale` to 0.30.7 with local access available. Verify from
`router-krm`:

```sh
for p in 22 8123 443 8555; do
  timeout 2 bash -c "cat < /dev/null > /dev/tcp/192.168.100.30/$p" \
    && echo "$p open" || echo "$p closed"
done
```

If the ports close, power cycle the Pi. If the add-on remains unhealthy, disable
its watchdog to stop the restart storm; LAN remains reachable, tailnet recovery
becomes manual.

### MQTT

The broker has no anonymous access (a bogus user gets CONNACK 5) but no ACL and a
weak Zigbee2MQTT credential. Rotate the password in Mosquitto, Zigbee2MQTT,
Frigate and HA's MQTT integration in one window; add topic ACLs for
`zigbee2mqtt/#`, `frigate/#` and `homeassistant/#`. Do not commit credentials.

### Backup restore

Backups are protected and include HA config/db, all add-ons and `media`, `ssl`,
`share`. Raise retention, copy the encryption key off-device and restore to a
test target before relying on the copy. The external collector mirrors
`/backup`; it does not add retention.

## Verification

```sh
# HA core and cameras
curl -sS -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  http://supervisor/core/api/
for c in front_yard back_yard road_view front_door; do
  curl -sS -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
    "http://supervisor/core/api/states/camera.$c"
done

# TLS and Nginx
curl -skS --resolve ha-krm.han-diatonic.uk:443:127.0.0.1 \
  -o /dev/null -w '%{http_code}\n' https://ha-krm.han-diatonic.uk/
openssl x509 -in /ssl/fullchain.pem -noout -enddate
```

Run `ha core check` before any Core restart. Do not use the Frigate add-on IP in
the HA integration: it changes across restarts; keep the add-on hostname and fix
DNS/Tailscale instead.

## Do not

- Do not enable Frigate recording/detection on this Pi without a Coral and
  external storage; four 1080p cameras at ~4 Mbps would fill the free space in
  under a day.
- Do not add zram or overclock; the current headroom is sufficient.
- Do not print MQTT, backup or API secrets in logs or repository files.

## Sources

- [OpenWrt routers](openwrt.md) for `router-krm` LAN/WAN and quarantine rules.
- [Docker stacks](docker-stacks.md) for the remaining Docker VM workloads;
  Frigate now runs on the krm HA host and its server-side stack is removed.
- [Tailscale policy](tailscale.md) for tags, grants and route approvals.
- [Proxmox backups](backups-proxmox.md) for the HA `/backup` collector.
