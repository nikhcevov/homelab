# Monitoring runbooks

[Repository overview](../../README.md)

Each Grafana alert carries a `runbook_url` pointing at the matching section.
Use the alert's `component`, `severity`, and `instance` labels to pick the host.

## Scrape target down

1. Open the Prometheus targets page and identify the failed `job`.
2. Check the exporter service and its loopback/private listener.
3. For `node-*`, check the host and the `node_exporter` unit.
4. For `pve`, check `pve-exporter` credentials and the PVE API token.
5. For `cadvisor`, check Docker and the cAdvisor container.
6. Do not remove the alert until a fresh scrape succeeds.

## Filesystem above 85%

1. Identify the `instance` and `mountpoint`.
2. Check large files, container images, logs, and snapshots.
3. Free space or deliberately raise the threshold; do not silence it permanently.
4. For the Docker VM, check `/mnt/appdata`, `/mnt/photos`, `/mnt/files`, `/mnt/data`, and `/`.

## Inode usage above 90%

1. Identify the `mountpoint`.
2. Find directories with many small files, especially container appdata.
3. Clean old logs, package caches, and temporary files.
4. Do not delete application state without a backup.

## Disk temperature above 50C

1. Identify the `device`.
2. Check airflow, fan state, and ambient temperature.
3. Check for a stuck process causing heavy I/O.
4. If temperature keeps rising, stop non-essential workloads.

## SMART health failed

1. Identify the disk by `device` and serial.
2. Run `smartctl -a` on the PVE host.
3. Check ZFS pool state and checksum errors.
4. Plan replacement; do not wait for the disk to fail completely.

## SMART pending or reallocated sectors

1. Record the current raw counters.
2. Re-run the check after a short interval to confirm the increase.
3. Check ZFS resilver/scrub state.
4. Replace the disk if the counter grows or the pool is degraded.

## SMART CRC errors increasing

1. Check the SATA/SAS cable and backplane.
2. Reseat the cable/disk.
3. Re-check the counter after a power cycle.
4. Replace the cable/disk if the counter continues to grow.

## PVE storage above 85%

1. Identify the storage ID.
2. Check VM disks, ISO/template storage, and backup retention.
3. Move data or expand the pool.
4. Do not delete the latest backup.

## ZFS pool not online

1. Run `zpool status -v` on the PVE host.
2. Check `dmesg` for disk errors.
3. If a disk is faulted/offline, replace it before clearing errors.
4. Do not start a scrub/resilver on a failing disk without checking the pool first.

## UPS on battery

1. Check mains power and the UPS display.
2. Expect the host shutdown policy to run if battery is low.
3. If power is back, confirm the UPS returned to online.
4. Do not acknowledge until `OL=1`, `OB=0`.

## UPS low battery

1. Save work and stop non-essential services.
2. Confirm the configured shutdown is proceeding.
3. If the UPS does not recover after mains return, inspect NUT logs.

## UPS overloaded

1. Remove non-essential load from the UPS.
2. Check the UPS load percentage.
3. Do not add more devices until load is below the safe threshold.

## UPS battery charge below 50%

1. Check whether the UPS is on battery or recharging.
2. If on battery, follow the UPS-on-battery runbook.
3. If online and charge is not recovering, test/replace the battery.

## Docker container unhealthy

1. Identify `compose_project` and `service`.
2. Run `docker inspect` for the healthcheck output.
3. Check `docker logs` and the service health endpoint.
4. Restart the container only after capturing the failure.

## Docker container restart loop

1. Identify the container and inspect its restart count.
2. Read `docker logs` and `docker inspect` for the exit reason.
3. Check OOM, missing secrets, and storage permissions.
4. Stop the looped container before it fills logs.

## Docker container OOM kill

1. Identify the container.
2. Check `docker stats` and the Compose memory limit.
3. Raise the limit only after measuring actual peak usage.
4. Check for a leak or an unbounded query.

## Container log volume spike

1. Identify `container` and `compose_project`.
2. Read the burst: `docker logs --since 15m <container>`.
3. Check whether a companion container is restarting:
   `docker inspect <container> --format '{{.RestartCount}} {{.State.OOMKilled}}'`.
4. For Immich, check `immich_redis` memory and the running job in the UI; an
   integrity or missing-file scan queues one job per asset.
5. Fix the source. Do not raise the log threshold to silence a crash loop.

## Container memory above 90% of limit

1. Identify `name` and `compose_project`.
2. Measure the peak: `docker stats --no-stream` and cgroup `memory.peak`.
3. Check the Compose limit and whether page cache or a fork (Redis/Valkey save,
   PostgreSQL maintenance) is counted in the same cgroup.
4. Raise the cap only with measured headroom on the VM; otherwise fix the
   unbounded work.
5. Verify `docker inspect <container> --format '{{.State.OOMKilled}}'` after the
   change.

## NTP not synchronized

1. Identify the host.
2. Run `timedatectl` and `chronyc tracking` (or the host's NTP client).
3. Check reachability of the configured time sources.
4. Restart the time sync service after fixing the source.

## NTP offset above 250ms

1. Check the offset direction and magnitude.
2. Compare with the host's time source.
3. If the offset persists, step the clock only during a controlled window.
4. Check virtualization host time sync if the guest cannot hold time.

## Maintenance procedure

There is no invented recurring maintenance window. For a planned change:

1. Add a short Gatus `maintenance` window for the affected endpoint, or
   temporarily disable that endpoint in the Git-tracked config.
2. Add a Grafana silence for the affected `component` and `instance`.
3. Record the reason and expected end time in the change notes.
4. Remove the silence/window after the check passes; do not leave it permanent.

Gatus alerts and Grafana alerts can overlap during a real host failure. That is
expected: Gatus answers "unreachable from outside"; Grafana answers "resource
or exporter degraded". Use `component` and `severity` to avoid treating them as
two independent incidents.
