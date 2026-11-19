"""Fail closed on stale upstream archives and yesterday's native VM backup."""
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import types
import unittest

from jinja2 import Environment, StrictUndefined
import yaml

ROOT = Path(__file__).resolve().parents[1]


def helper(**overrides):
    values = dict(
        pve_backup_collector="/unused", pve_backup_collector_dataset="rpool/backup-staging/collector",
        pve_backup_pbs_vmid=101, pve_backup_id="pve-recovery", pve_backup_vm_wait_seconds=86400,
        pve_pbs_backup_vm=100, pve_pbs_backup_schedule="02:00", pve_pbs_address="10.77.0.3",
        pve_pbs_datastore="vault-b", pve_pbs_secondary_datastore="", pve_pbs_storage_id="pbs-vault-b",
        pve_pbs_user="pve@pbs", pve_pbs_token="pve", pve_pbs_secret_path="/unused/token.json",
        bootstrap_timezone="Asia/Yerevan", pve_backup_sync_job="homelab-vault-a",
        pve_backup_local_max_age_hours=36, pve_backup_sync_max_age_hours=36,
    )
    values.update(overrides)
    values["pve_vm_data_disks"] = yaml.safe_load(
        (ROOT / "inventory/group_vars/pve/vm.yml").read_text()
    )["pve_vm_data_disks"]
    environment = Environment(undefined=StrictUndefined)
    environment.filters["to_json"] = json.dumps
    source = environment.from_string((ROOT / "roles/pve_backup/templates/pbs-file-backup.py.j2").read_text()).render(**values)
    module = types.ModuleType("pbs_file_backup")
    exec(compile(source, "pbs-file-backup", "exec"), module.__dict__)
    return module


class ArchiveAge(unittest.TestCase):
    def setUp(self):
        self.backup = helper()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def archive(self, name, age):
        path = self.root / name
        path.write_bytes(b"archive")
        os.utime(path, (100000 - age, 100000 - age))
        return path

    def test_fresh_unrelated_file_does_not_hide_stale_latest_archive(self):
        self.archive("vpn-backup-old.tar.gz", 9000)
        self.archive("rsync-status.txt", 0)
        with self.assertRaises(RuntimeError):
            self.backup.latest_archive(self.root, "vpn-backup-*.tar.gz", 7200, now=100000)

    def test_mtime_survives_collection_and_age_boundary_is_inclusive(self):
        archive = self.archive("vpn-backup-today.tar.gz", 7200)
        self.assertEqual(self.backup.latest_archive(self.root, "vpn-backup-*.tar.gz", 7200, now=100000), archive)

    def test_empty_missing_and_future_archives_are_not_current_backups(self):
        for name, age, contents in (("empty.tar", 0, b""), ("future.tar", -1, b"x")):
            with self.subTest(name=name):
                path = self.archive(name, age)
                path.write_bytes(contents)
                os.utime(path, (100000 - age, 100000 - age))
                with self.assertRaises(RuntimeError):
                    self.backup.latest_archive(self.root, name, 7200, now=100000)
        with self.assertRaises(RuntimeError):
            self.backup.latest_archive(self.root, "missing*", 7200, now=100000)


class NativeVmSuccess(unittest.TestCase):
    def setUp(self):
        self.backup = helper()

    def task(self, start, status="OK", end=11000):
        return {"type": "vzdump", "id": "100", "starttime": start, "endtime": end, "status": status, "upid": "UPID:test"}

    def test_yesterday_and_newer_failed_attempt_cannot_pass_old_success(self):
        for rows in ([self.task(100)], [self.task(10000), self.task(10500, "ERROR")]):
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                self.backup.current_vm_task(rows, 9000)

    def test_running_current_vm_task_requires_wait_instead_of_old_success(self):
        task = self.task(10500, "RUNNING")
        task.pop("endtime")
        self.assertIsNone(self.backup.current_vm_task([self.task(10000), task], 9000))

    def test_snapshot_must_belong_to_current_successful_task(self):
        task = self.backup.current_vm_task([self.task(10000)], 9000)
        with self.assertRaises(RuntimeError):
            self.backup.current_vm_snapshot([{"backup-time": 100}], task)
        self.assertEqual(self.backup.current_vm_snapshot([{"backup-time": 10030}], task), 10030)

    def test_native_night_uses_yerevan_day_not_utc_day(self):
        now = datetime.fromisoformat("2026-11-14T23:00:00+00:00").timestamp()
        expected = datetime.fromisoformat("2026-11-14T22:00:00+00:00").timestamp()
        self.assertEqual(self.backup.cycle_floor(now), expected)

    def test_before_nightly_schedule_uses_previous_due_cycle(self):
        now = datetime.fromisoformat("2026-11-15T00:30:00+04:00").timestamp()
        expected = datetime.fromisoformat("2026-11-14T02:00:00+04:00").timestamp()
        self.assertEqual(self.backup.cycle_floor(now), expected)


class FilePointProof(unittest.TestCase):
    def test_missing_new_point_or_archive_keeps_previous_freshness_receipt(self):
        for new_point, archive_names in (
            (False, []), (True, ["recovery.pxar.didx"]),
            (True, ["recovery.pxar.didx", "collector.pxar.didx"]),
        ):
            with self.subTest(new_point=new_point, archive_names=archive_names), tempfile.TemporaryDirectory() as directory:
                backup = helper()
                backup.STATE = Path(directory)
                receipt = backup.STATE / "pbs-file-last-success"
                receipt.write_text("123\n")
                backup.credentials = lambda: {}
                backup.time = types.SimpleNamespace(time=lambda: 100000)
                uploaded = False

                def native_client(environment, *args):
                    nonlocal uploaded
                    if args[0] == "backup":
                        uploaded = True
                        return ""
                    if args[:2] == ("snapshot", "list"):
                        points = [{"backup-type": "host", "backup-id": "pve-recovery", "backup-time": 100000}] if uploaded and new_point else []
                        return json.dumps(points)
                    if args[:2] == ("snapshot", "files"):
                        return json.dumps([{"filename": name} for name in archive_names])
                    raise AssertionError(args)

                backup.client = native_client
                if new_point and len(archive_names) == 2:
                    backup.backup_files()
                    self.assertEqual(receipt.read_text(), "100000\n")
                    self.assertEqual(json.loads((backup.STATE / "pbs-file-latest.json").read_text())["backup-time"], 100000)
                else:
                    with self.assertRaises(RuntimeError):
                        backup.backup_files()
                    self.assertEqual(receipt.read_text(), "123\n")
                    self.assertFalse((backup.STATE / "pbs-file-latest.json").exists())


class CycleCompletion(unittest.TestCase):
    def setUp(self):
        self.backup = helper()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.backup.STATE = Path(self.directory.name)
        self.now = int(datetime.fromisoformat("2026-11-15T12:00:00+00:00").timestamp())
        self.file_epoch, self.vm_epoch = self.now - 120, self.now - 590
        self.backup.time = types.SimpleNamespace(time=lambda: self.now, monotonic=lambda: self.now)
        self.backup.credentials = lambda: {"PBS_REPOSITORY": "pve@pbs!pve@10.77.0.3:vault-b"}
        self.backup.WAIT_SECONDS = 0
        self.task = {
            "type": "vzdump", "id": "100", "starttime": self.now - 600,
            "endtime": self.now - 300, "status": "OK", "upid": "UPID:test:vm",
        }
        self.tasks = [self.task]
        self.backup.pve = lambda *args: self.tasks
        complete = {
            "qemu-server.conf.blob", "drive-efidisk0.img.fidx",
            "drive-scsi0.img.fidx", "drive-scsi1.img.fidx",
            "drive-scsi2.img.fidx", "drive-scsi3.img.fidx",
        }
        self.points = {}
        self.archives = {}
        for store in ("vault-a", "vault-b"):
            self.points[store] = [
                {"backup-type": "host", "backup-id": "pve-recovery", "backup-time": self.file_epoch},
                {"backup-type": "vm", "backup-id": "100", "backup-time": self.vm_epoch},
            ]
            self.archives[store] = {
                "host": {"recovery.pxar.didx", "collector.pxar.didx"},
                "vm": set(complete),
            }
        self.config = {
            "store": "vault-a", "remote-store": "vault-b",
            "owner": "pve@pbs!pve", "remove-vanished": False,
        }
        self.sync_tasks = [{"upid": "UPID:test:sync", "endtime": self.now, "status": "OK"}]
        self.manager_calls = []
        self.backup.client, self.backup.manager = self.native_client, self.native_manager
        self.save("pbs-file-latest.json", {
            "backup-time": self.file_epoch, "store": "vault-b",
            "snapshot": "host/pve-recovery/2026-11-15T11:58:00Z",
        })
        self.marker("pbs-file-last-success", self.now)

    def save(self, name, value):
        (self.backup.STATE / name).write_text(json.dumps(value))

    def load(self, name):
        return json.loads((self.backup.STATE / name).read_text())

    def marker(self, name, value):
        (self.backup.STATE / name).write_text(str(value) + "\n")

    def native_client(self, environment, *args):
        store = environment["PBS_REPOSITORY"].rsplit(":", 1)[1]
        if args[:2] == ("snapshot", "list"):
            return json.dumps(self.points[store])
        if args[:2] == ("snapshot", "files"):
            group = args[2].split("/", 1)[0]
            return json.dumps([{"filename": name} for name in self.archives[store][group]])
        raise AssertionError(args)

    def native_manager(self, *args):
        self.manager_calls.append(args)
        if args[:2] == ("sync-job", "show"):
            return json.dumps(self.config)
        if args[:2] == ("sync-job", "run"):
            return json.dumps("UPID:test:sync")
        if args[:2] == ("task", "list"):
            return json.dumps(self.sync_tasks)
        raise AssertionError(args)

    def assert_no_primary(self):
        self.assertFalse((self.backup.STATE / "pbs-primary-latest.json").exists())
        self.assertFalse((self.backup.STATE / "pbs-primary-last-success").exists())

    def test_primary_only_proves_both_points_without_replica_markers(self):
        self.backup.sys = types.SimpleNamespace(argv=["pbs-file-backup", "complete-cycle"])
        self.backup.main()
        self.assertEqual(self.load("pbs-primary-latest.json"), {
            "task": "UPID:test:vm", "file-time": self.file_epoch, "vm-time": self.vm_epoch,
            "store": "vault-b", "completed-at": self.now,
        })
        self.assertEqual((self.backup.STATE / "pbs-primary-last-success").read_text(), str(self.now) + "\n")
        self.assertFalse((self.backup.STATE / "pbs-sync-latest.json").exists())
        self.assertFalse((self.backup.STATE / "pbs-sync-last-success").exists())
        self.assertEqual(self.manager_calls, [])

    def test_every_managed_vm_disk_is_mandatory_with_or_without_secondary(self):
        for secondary in ("", "vault-a"):
            for disk in ("scsi0", "scsi1", "scsi2", "scsi3"):
                with self.subTest(secondary=secondary, disk=disk):
                    self.backup.SECONDARY = secondary
                    archive = "drive-" + disk + ".img.fidx"
                    self.archives["vault-b"]["vm"].remove(archive)
                    with self.assertRaisesRegex(RuntimeError, "required backup archives"):
                        self.backup.complete_cycle()
                    self.assert_no_primary()
                    self.assertEqual(self.manager_calls, [])
                    self.archives["vault-b"]["vm"].add(archive)

    def test_latest_failed_or_running_task_cannot_publish_primary(self):
        for status in ("ERROR", "RUNNING"):
            with self.subTest(status=status):
                self.tasks = [self.task, dict(self.task, starttime=self.now - 200, status=status, endtime=0 if status == "RUNNING" else self.now)]
                with self.assertRaises(RuntimeError):
                    self.backup.complete_cycle()
                self.assert_no_primary()

    def test_old_vm_point_cannot_satisfy_current_successful_task(self):
        self.points["vault-b"][1]["backup-time"] = self.now - 86400
        with self.assertRaisesRegex(RuntimeError, "matching primary PBS point"):
            self.backup.complete_cycle()
        self.assert_no_primary()

    def test_missing_or_future_native_task_cannot_publish_primary(self):
        for rows in ([], [dict(self.task, starttime=self.now + 1, endtime=self.now + 2)]):
            with self.subTest(rows=rows):
                self.tasks = rows
                with self.assertRaises(RuntimeError):
                    self.backup.complete_cycle()
                self.assert_no_primary()

    def test_missing_host_point_or_archive_cannot_publish_primary(self):
        for missing_point in (True, False):
            with self.subTest(missing_point=missing_point):
                if missing_point:
                    self.points["vault-b"][0]["backup-time"] = self.file_epoch - 1
                else:
                    self.points["vault-b"][0]["backup-time"] = self.file_epoch
                    self.archives["vault-b"]["host"].remove("collector.pxar.didx")
                with self.assertRaises(RuntimeError):
                    self.backup.complete_cycle()
                self.assert_no_primary()

    def test_stale_wrong_store_or_wrong_snapshot_file_proof_cannot_publish_primary(self):
        original = self.load("pbs-file-latest.json")
        for change in ({"backup-time": self.now - 86400}, {"backup-time": self.now + 1},
                       {"store": "vault-a"}, {"snapshot": "host/another/2026-11-15T11:58:00Z"}):
            with self.subTest(change=change):
                self.save("pbs-file-latest.json", dict(original, **change))
                with self.assertRaises(RuntimeError):
                    self.backup.complete_cycle()
                self.assert_no_primary()

    def test_configured_secondary_receipts_match_exact_primary_points(self):
        self.backup.SECONDARY = "vault-a"
        self.backup.complete_cycle()
        self.assertEqual(self.load("pbs-sync-latest.json"), {
            "task": "UPID:test:sync", "file-time": self.file_epoch, "vm-time": self.vm_epoch,
            "store": "vault-a", "primary-store": "vault-b", "completed-at": self.now,
        })
        self.assertEqual((self.backup.STATE / "pbs-sync-last-success").read_text(), str(self.now) + "\n")
        self.assertEqual(self.load("pbs-primary-latest.json")["store"], "vault-b")
        self.backup.freshness()

    def test_unsafe_secondary_policy_never_publishes_replica_success(self):
        self.backup.SECONDARY = "vault-a"
        original = dict(self.config)
        for change in (
            {"remote": "elsewhere"}, {"remove-vanished": True}, {"owner": "root@pam"},
            {"ns": "nested"}, {"remote-ns": "nested"}, {"sync-direction": "push"},
            {"store": "vault-b"}, {"remote-store": "vault-a"},
        ):
            with self.subTest(change=change):
                self.config = dict(original, **change)
                with self.assertRaises(RuntimeError):
                    self.backup.complete_cycle()
                self.assertFalse((self.backup.STATE / "pbs-sync-last-success").exists())
                self.assertEqual(self.load("pbs-primary-latest.json")["store"], "vault-b")

    def test_failed_or_unrelated_sync_task_cannot_publish_replica_success(self):
        self.backup.SECONDARY = "vault-a"
        for rows in (
            [{"upid": "UPID:test:sync", "endtime": self.now, "status": "ERROR"}],
            [{"upid": "UPID:other:sync", "endtime": self.now, "status": "OK"}],
        ):
            with self.subTest(rows=rows):
                self.sync_tasks = rows
                with self.assertRaises(RuntimeError):
                    self.backup.complete_cycle()
                self.assertFalse((self.backup.STATE / "pbs-sync-latest.json").exists())
                self.assertFalse((self.backup.STATE / "pbs-sync-last-success").exists())

    def test_replica_requires_exact_host_and_vm_points_and_all_archives(self):
        self.backup.SECONDARY = "vault-a"
        for group in ("host", "vm"):
            with self.subTest(group=group):
                index = 0 if group == "host" else 1
                point = self.points["vault-a"][index]["backup-time"]
                self.points["vault-a"][index]["backup-time"] -= 1
                with self.assertRaises(RuntimeError):
                    self.backup.complete_cycle()
                self.points["vault-a"][index]["backup-time"] = point
                archive = "collector.pxar.didx" if group == "host" else "drive-scsi3.img.fidx"
                self.archives["vault-a"][group].remove(archive)
                with self.assertRaises(RuntimeError):
                    self.backup.complete_cycle()
                self.archives["vault-a"][group].add(archive)
                self.assertFalse((self.backup.STATE / "pbs-sync-last-success").exists())

    def test_primary_freshness_ignores_historical_replica_but_not_missing_primary(self):
        self.marker("pbs-sync-last-success", self.now)
        self.save("pbs-sync-latest.json", {"store": "vault-a"})
        with self.assertRaises(RuntimeError):
            self.backup.freshness()
        self.backup.complete_cycle()
        self.backup.freshness()
        self.assertEqual(self.load("pbs-sync-latest.json"), {"store": "vault-a"})
        self.assertEqual(self.manager_calls, [])

    def test_primary_freshness_rejects_old_store_or_mismatched_evidence(self):
        self.backup.complete_cycle()
        for name, change in (
            ("pbs-file-latest.json", {"store": "vault-a"}),
            ("pbs-primary-latest.json", {"store": "vault-a"}),
            ("pbs-primary-latest.json", {"file-time": self.file_epoch - 1}),
            ("pbs-primary-latest.json", {"vm-time": self.now + 1}),
            ("pbs-primary-latest.json", {"completed-at": self.now + 1}),
        ):
            with self.subTest(name=name, change=change):
                original = self.load(name)
                self.save(name, dict(original, **change))
                with self.assertRaises(RuntimeError):
                    self.backup.freshness()
                self.save(name, original)

    def test_point_age_limit_is_inclusive_and_oldest_vm_point_controls_freshness(self):
        self.backup.complete_cycle()
        self.now += 36 * 3600 - 590
        self.backup.sys = types.SimpleNamespace(argv=["pbs-file-backup", "freshness"])
        self.backup.main()
        self.now += 1
        with self.assertRaises(RuntimeError):
            self.backup.main()

    def test_old_points_cannot_be_refreshed_by_recent_success_timestamps(self):
        self.backup.complete_cycle()
        self.now += 36 * 3600
        self.marker("pbs-file-last-success", self.now)
        self.marker("pbs-primary-last-success", self.now)
        receipt = self.load("pbs-primary-latest.json")
        self.save("pbs-primary-latest.json", dict(receipt, **{"completed-at": self.now}))
        with self.assertRaises(RuntimeError):
            self.backup.freshness()

    def test_missing_future_stale_or_torn_success_markers_fail_freshness(self):
        self.backup.complete_cycle()
        for name in ("pbs-file-last-success", "pbs-primary-last-success"):
            original = (self.backup.STATE / name).read_text()
            for value in (None, "not-an-epoch", str(self.now + 1), str(self.now - 36 * 3600 - 1)):
                with self.subTest(name=name, value=value):
                    if value is None:
                        (self.backup.STATE / name).unlink()
                    else:
                        (self.backup.STATE / name).write_text(value + "\n")
                    with self.assertRaises(RuntimeError):
                        self.backup.freshness()
            (self.backup.STATE / name).write_text(original)

    def test_configured_secondary_rejects_missing_stale_or_wrong_primary_replica(self):
        self.backup.complete_cycle()
        self.backup.SECONDARY = "vault-a"
        with self.assertRaises(RuntimeError):
            self.backup.freshness()
        self.backup.complete_cycle()
        original = self.load("pbs-sync-latest.json")
        for change in (
            {"store": "other"}, {"primary-store": "vault-a"},
            {"file-time": self.file_epoch - 1}, {"vm-time": self.vm_epoch - 1},
            {"completed-at": self.now - 36 * 3600 - 1},
        ):
            with self.subTest(change=change):
                self.save("pbs-sync-latest.json", dict(original, **change))
                with self.assertRaises(RuntimeError):
                    self.backup.freshness()


if __name__ == "__main__":
    unittest.main()
