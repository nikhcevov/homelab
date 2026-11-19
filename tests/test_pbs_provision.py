"""Retire only exact managed PBS binds without requiring inactive disks at boot."""

import copy
import json
import shlex
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

from jinja2 import Environment, StrictUndefined
import yaml


ROOT = Path(__file__).resolve().parents[1]


def provision(**overrides):
    values = yaml.safe_load((ROOT / "inventory/group_vars/pve/pbs.yml").read_text())
    values.update(bootstrap_timezone="Asia/Yerevan", pve_pbs_schedules_enabled=False)
    values.update(overrides)
    values["pve_pbs_storage_id"] = "pbs-" + values["pve_pbs_datastore"]
    environment = Environment(undefined=StrictUndefined)
    environment.filters.update(to_json=json.dumps, bool=bool)
    template = environment.from_string((ROOT / "roles/pve_pbs/templates/provision.py.j2").read_text())
    module = types.ModuleType("pbs_provision")
    exec(compile(template.render(**values), "pbs-provision", "exec"), module.__dict__)
    return module


class NativeTopology:
    """Model the native command boundary, retaining real temporary CT config writes."""

    def __init__(self, configuration):
        self.configuration = configuration
        self.running = True
        self.tasks = []
        self.datastores = [
            {"name": "tank", "path": "/mnt/datastore/tank", "gc-schedule": "08:00", "prune-schedule": "07:00"},
            {"name": "vault-a", "path": "/mnt/datastore/vault-a", "gc-schedule": "08:00"},
        ]
        self.jobs = {
            "verify-job": [{"id": "old-verify", "store": "vault-a", "schedule": "sun 10:00"}],
            "prune-job": [{"id": "old-prune", "store": "tank", "disable": False}],
            "sync-job": [{"id": "homelab-vault-b", "store": "vault-b", "remote-store": "vault-a", "schedule": "09:00"}],
        }

    def run(self, args, **kwargs):
        args = [str(value) for value in args]
        output = ""
        if args[:3] == ["pct", "status", "101"]:
            output = "status: " + ("running" if self.running else "stopped")
        elif args[:5] == ["pct", "exec", "101", "--", "test"]:
            if not self.running:
                raise AssertionError("A stopped CT cannot execute guest commands")
        elif args[:5] == ["pct", "exec", "101", "--", "proxmox-backup-manager"]:
            if not self.running:
                raise AssertionError("A stopped CT cannot execute PBS commands")
            kind, action, *options = args[5:]
            if kind == "task" and action == "list":
                output = json.dumps(self.tasks)
            elif action == "list":
                output = json.dumps(self.datastores if kind == "datastore" else self.jobs[kind])
            elif action == "update":
                key = "name" if kind == "datastore" else "id"
                rows = self.datastores if kind == "datastore" else self.jobs[kind]
                row = next(row for row in rows if row[key] == options[0])
                for index in range(1, len(options), 2):
                    option, value = options[index:index + 2]
                    if option == "--delete":
                        row.pop(value, None)
                    else:
                        row[option[2:]] = value
            else:
                raise AssertionError(f"Unexpected PBS command: {args}")
        elif args[:3] == ["pct", "shutdown", "101"]:
            if self.tasks:
                raise AssertionError("The CT must not stop with active PBS tasks")
            for row in self.datastores:
                if not row.get("maintenance-mode", "").startswith("type=offline"):
                    raise AssertionError("Inactive stores must be offline before shutdown")
            self.running = False
        elif args[:3] == ["pct", "set", "101"]:
            if self.running:
                raise AssertionError("Bind configuration changes require a clean stopped CT")
            text = self.configuration.read_text()
            if args[3] == "--delete":
                text = re.sub(r"^" + re.escape(args[4]) + r":.*\n", "", text, flags=re.M)
            else:
                text += args[3][2:] + ": " + args[4] + "\n"
            self.configuration.write_text(text)
        else:
            raise AssertionError(f"Unexpected native command: {args}")
        return subprocess.CompletedProcess(args, 0, output, "")


class TopologyValidation(unittest.TestCase):
    def setUp(self):
        self.stores = copy.deepcopy(provision().STORES)

    def test_each_store_requires_an_actual_enabled_boolean(self):
        for value in (None, "false", 0, 1):
            with self.subTest(value=value):
                stores = copy.deepcopy(self.stores)
                if value is None:
                    stores[0].pop("enabled")
                else:
                    stores[0]["enabled"] = value
                with self.assertRaises(RuntimeError):
                    provision(pve_pbs_datastores=stores)

    def test_primary_must_be_enabled_and_secondary_is_optional_but_distinct_and_enabled(self):
        self.assertEqual(provision().SECONDARY, "")
        for primary, secondary in (("vault-a", ""), ("vault-b", "vault-b"),
                                   ("vault-b", "vault-a"), ("vault-b", "foreign"),
                                   ("vault-b", None), ("vault-b", False)):
            with self.subTest(primary=primary, secondary=secondary), self.assertRaises(RuntimeError):
                provision(pve_pbs_datastore=primary, pve_pbs_secondary_datastore=secondary)
        self.stores[1]["enabled"] = True
        enabled = provision(pve_pbs_datastores=self.stores, pve_pbs_secondary_datastore="vault-a")
        self.assertEqual(enabled.SECONDARY, "vault-a")


class BindRetirement(unittest.TestCase):
    def setUp(self):
        self.module = provision()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.configuration = Path(self.directory.name) / "101.conf"
        self.baseline = (
            "description: homelab-managed-pbs/v1\nunprivileged: 1\n"
            "mp0: /tank/pbs,mp=/mnt/datastore/tank,backup=0\n"
            "mp1: /mnt/vault/pbs,mp=/mnt/datastore/vault-a,backup=0\n"
            "mp9: /srv/foreign,mp=/srv/foreign,backup=0\n"
        )
        self.configuration.write_text(self.baseline)
        self.native = NativeTopology(self.configuration)

    def reconcile(self):
        with patch("subprocess.run", side_effect=self.native.run):
            self.module.reconcile_binds(self.configuration)

    def test_exact_inactive_binds_retire_and_foreign_bind_survives_clean_shutdown(self):
        self.reconcile()
        self.assertEqual(self.configuration.read_text(),
                         "description: homelab-managed-pbs/v1\nunprivileged: 1\n"
                         "mp9: /srv/foreign,mp=/srv/foreign,backup=0\n"
                         "mp2: /mnt/backup-b/pbs,mp=/mnt/datastore/vault-b,backup=0\n")
        self.assertFalse(self.native.running)
        self.assertEqual(len(self.native.datastores), 2)
        self.assertTrue(all("gc-schedule" not in row for row in self.native.datastores))
        self.assertTrue(all("prune-schedule" not in row for row in self.native.datastores))
        self.assertNotIn("schedule", self.native.jobs["verify-job"][0])
        self.assertEqual(self.native.jobs["prune-job"][0]["disable"], "true")
        self.assertNotIn("schedule", self.native.jobs["sync-job"][0])

    def test_foreign_bind_drift_refuses_before_any_native_command_or_mutation(self):
        for old, new in (
            ("/mnt/vault/pbs,", "/srv/foreign-a,"),
            ("mp=/mnt/datastore/vault-a", "mp=/srv/foreign-a"),
            ("vault-a,backup=0", "vault-a,backup=0,ro=1"),
            ("mp1:", "mp8:"),
            ("mp1:", "mp2:"),
        ):
            with self.subTest(new=new):
                before = self.baseline.replace(old, new)
                self.configuration.write_text(before)
                with patch("subprocess.run", side_effect=AssertionError("Mutation preceded complete bind preflight")):
                    with self.assertRaises(RuntimeError):
                        self.module.reconcile_binds(self.configuration)
                self.assertEqual(self.configuration.read_text(), before)

    def test_running_tasks_block_offlining_detach_and_restart(self):
        self.native.tasks = [{"upid": "UPID:busy", "worker-type": "backup"}]
        with self.assertRaises(RuntimeError):
            self.reconcile()
        self.assertTrue(self.native.running)
        self.assertEqual(self.configuration.read_text(), self.baseline)
        self.assertNotIn("maintenance-mode", self.native.datastores[0])

    def test_stopped_ct_can_drop_absent_inactive_disks_without_guest_commands(self):
        self.native.running = False
        self.reconcile()
        self.assertEqual(self.module.bind_changes(self.configuration.read_text()), ([], []))
        self.assertFalse(self.native.running)

    def test_registered_datastore_path_mismatch_blocks_retirement_without_changes(self):
        self.native.datastores[1]["path"] = "/foreign"
        with self.assertRaises(RuntimeError):
            self.reconcile()
        self.assertEqual(self.configuration.read_text(), self.baseline)
        self.assertTrue(self.native.running)
        self.assertNotIn("maintenance-mode", self.native.datastores[0])


    def test_reconciled_active_ct_needs_no_inactive_path_or_guest_probe(self):
        self.configuration.write_text(
            "mp2: /mnt/backup-b/pbs,mp=/mnt/datastore/vault-b,backup=0\n"
            "mp9: /srv/foreign,mp=/srv/foreign,backup=0\n"
        )
        with patch("subprocess.run", side_effect=AssertionError("Unneeded restart or inactive dependency")):
            self.module.reconcile_binds(self.configuration)


class PveStorageRetirement(unittest.TestCase):
    def setUp(self):
        self.module = provision()
        self.storages = [
            {"storage": "pbs-tank", "type": "pbs", "server": "10.77.0.3", "datastore": "tank", "disable": 0},
            {"storage": "pbs-vault-a", "type": "pbs", "server": "10.77.0.3", "datastore": "vault-a", "disable": 0},
            {"storage": "pbs-vault-b", "type": "pbs", "server": "10.77.0.3", "datastore": "vault-b", "disable": 0},
            {"storage": "foreign", "type": "dir", "disable": 0},
        ]
        self.jobs = [
            {"id": "homelab-vm100-pbs", "storage": "pbs-vault-a", "enabled": 1},
            {"id": "unrelated-backup", "storage": "foreign", "enabled": 1},
        ]

    def native_run(self, args, **kwargs):
        args = [str(value) for value in args]
        output = ""
        if args[:2] == ["pvesm", "set"] and args[3:] == ["--disable", "1"]:
            next(row for row in self.storages if row["storage"] == args[2])["disable"] = 1
        elif args == ["pvesh", "get", "/cluster/backup", "--output-format", "json"]:
            output = json.dumps(self.jobs)
        elif args[:2] == ["pvesh", "set"] and args[3:] == ["--enabled", "0"]:
            jobid = args[2].removeprefix("/cluster/backup/")
            next(row for row in self.jobs if row["id"] == jobid)["enabled"] = 0
        else:
            raise AssertionError(f"Unexpected storage retirement command: {args}")
        return subprocess.CompletedProcess(args, 0, output, "")

    def test_old_storages_and_their_backup_schedule_disable_without_removal(self):
        with patch("subprocess.run", side_effect=self.native_run):
            self.module.retire_pve_storages(self.storages)
        self.assertEqual([(row["storage"], row["disable"]) for row in self.storages],
                         [("pbs-tank", 1), ("pbs-vault-a", 1), ("pbs-vault-b", 0), ("foreign", 0)])
        self.assertEqual([(row["id"], row["enabled"]) for row in self.jobs],
                         [("homelab-vm100-pbs", 0), ("unrelated-backup", 1)])

    def test_foreign_old_storage_identity_refuses_before_disabling_any_storage(self):
        self.storages[1]["server"] = "192.0.2.99"
        with patch("subprocess.run", side_effect=AssertionError("Partial retirement before identity preflight")):
            with self.assertRaises(RuntimeError):
                self.module.retire_pve_storages(self.storages)
        self.assertTrue(all(row["disable"] == 0 for row in self.storages))


class InactiveBootIndependence(unittest.TestCase):
    @unittest.skipUnless(shutil.which("findmnt") and shutil.which("realpath"), "Linux mount tools required")
    def test_guard_uses_real_active_mount_without_requiring_absent_inactive_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            mount = json.loads(subprocess.check_output(
                ["findmnt", "--json", "--target", directory, "--output", "TARGET,SOURCE,FSTYPE,OPTIONS"],
                text=True,
            ))["filesystems"][0]
            if "rw" not in mount["options"].split(",") or "noatime" in mount["options"].split(","):
                self.skipTest("The test filesystem must satisfy the production RW/atime guard")
            stores = [
                {"name": "absent-a", "enabled": False, "mountpoint": directory + "/absent",
                 "source": "UUID=absent", "fstype": "xfs", "host_path": directory + "/absent/pbs"},
                {"name": "active-b", "enabled": True, "mountpoint": mount["target"],
                 "source": mount["source"], "fstype": mount["fstype"], "host_path": directory},
            ]
            environment = Environment(undefined=StrictUndefined)
            environment.filters["quote"] = shlex.quote
            template = environment.from_string((ROOT / "roles/pve_pbs/templates/pbs-mount-guard.sh.j2").read_text())
            script = template.render(pve_pbs_datastores=stores)
            subprocess.run(["sh", "-c", script], check=True, capture_output=True, text=True)
            stores[1]["source"] = "UUID=wrong-active-disk"
            rejected = subprocess.run(["sh", "-c", template.render(pve_pbs_datastores=stores)],
                                      capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)


if __name__ == "__main__":
    unittest.main()
