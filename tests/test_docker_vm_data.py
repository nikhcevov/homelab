"""Exercise the guest's explicit, non-destructive data-disk initialization guard."""

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jinja2 import Environment, StrictUndefined
import yaml


ROOT = Path(__file__).resolve().parents[1]


class GuestDataSafety(unittest.TestCase):
    def setUp(self):
        values = yaml.safe_load((ROOT / "roles/docker_vm/defaults/main.yml").read_text())
        values.update(yaml.safe_load((ROOT / "inventory/group_vars/docker/docker_vm.yml").read_text()))
        environment = Environment(undefined=StrictUndefined)
        environment.filters["to_json"] = json.dumps
        template = environment.from_string((ROOT / "roles/docker_vm/templates/prepare-data.py.j2").read_text())
        self.program = compile(template.render(**values), "prepare-data.py", "exec")
        self.disks = {}
        self.signatures = {}
        for disk in values["docker_vm_data_disks"]:
            device = disk["device"]
            self.disks[device] = {
                "path": "/dev/test-" + disk["serial"], "type": "disk", "serial": disk["serial"],
                "size": disk["size_gib"] * 1024 ** 3, "fstype": None, "label": None,
                "mountpoints": [None],
            }
            self.signatures[device] = []
        self.mounts = {}
        self.mutations = []
        self.photos = next(iter(self.disks))
        self.files = list(self.disks)[1]
        self.udev_stale = False

    def inspect(self, args, **kwargs):
        if args[0] == "lsblk":
            self.assertIn("--bytes", args)
            device = self.disks[args[-1]].copy()
            if self.udev_stale:
                device.update(fstype=None, label=None)
            return json.dumps({"blockdevices": [device]})
        if args[0] == "wipefs":
            self.assertEqual(args[1], "--json")
            return json.dumps({"signatures": self.signatures[args[-1]]})
        raise AssertionError(f"Unexpected read (whole-disk scans are forbidden): {args}")

    def find_mount(self, args, **kwargs):
        self.assertEqual(args[:3], ["findmnt", "--json", "--mountpoint"])
        mount = self.mounts.get(args[3])
        return SimpleNamespace(returncode=0 if mount else 1,
                               stdout=json.dumps({"filesystems": [mount]}) if mount else "", stderr="")

    def format(self, args):
        self.assertEqual(args[:4], ["mkfs.ext4", "-m", "0", "-L"])
        self.assertNotIn("-F", args)
        self.assertIn("nodiscard,lazy_itable_init=1,lazy_journal_init=1", args)
        device = args[-1]
        self.assertEqual(self.signatures[device], [])
        self.mutations.append(args)
        self.disks[device].update(fstype="ext4", label=args[4])
        self.signatures[device] = [{"device": device, "offset": "0x438", "type": "ext4", "label": args[4]}]

    def execute(self, *args):
        with patch("sys.argv", ["prepare-data.py", *args]), \
             patch("subprocess.check_output", side_effect=self.inspect), \
             patch("subprocess.check_call", side_effect=self.format), \
             patch("subprocess.run", side_effect=self.find_mount):
            exec(self.program, {"__name__": "__main__"})

    def initialize(self):
        self.execute("--initialize")

    def test_blank_disks_need_explicit_fresh_allocation_authorization(self):
        with self.assertRaisesRegex(SystemExit, "freshly allocated"):
            self.execute()
        self.assertEqual(self.mutations, [])

    def test_authorized_blank_disks_initialize_without_scanning_data(self):
        self.initialize()
        self.assertEqual([command[-1] for command in self.mutations], [self.photos, self.files])
        self.assertEqual(self.disks[self.photos]["label"], "HOMELAB_PHOTOS")
        self.assertEqual(self.disks[self.files]["label"], "HOMELAB_FILES")

    def test_rerun_never_reformats_or_relabels_existing_filesystems(self):
        self.initialize()
        self.mutations.clear()
        self.initialize()
        self.assertEqual(self.mutations, [])

    def test_initialization_and_rerun_work_with_stale_udev_filesystem_metadata(self):
        self.udev_stale = True
        self.initialize()
        self.assertEqual([command[-1] for command in self.mutations], [self.photos, self.files])
        self.mutations.clear()
        self.initialize()
        self.assertEqual(self.mutations, [])

    def test_preflight_rejects_wrong_identity_size_partitions_or_mounted_blank(self):
        for changed in ({"serial": "foreign"}, {"size": 64 * 1024 ** 3},
                        {"children": [{"type": "part"}]}, {"mountpoints": ["/somewhere"]}):
            with self.subTest(changed=changed):
                before = self.disks[self.photos].copy()
                self.disks[self.photos].update(changed)
                with self.assertRaises(SystemExit):
                    self.initialize()
                self.assertEqual(self.mutations, [])
                self.disks[self.photos] = before

    def test_unknown_signature_on_second_disk_blocks_all_formatting(self):
        self.signatures[self.files] = [{"type": "gpt", "offset": "0x200"}]
        with self.assertRaisesRegex(SystemExit, "signature"):
            self.initialize()
        self.assertEqual(self.mutations, [])

    def test_existing_foreign_filesystem_or_label_is_not_replaced(self):
        for fstype, label in (("xfs", "HOMELAB_PHOTOS"), ("ext4", "foreign")):
            with self.subTest(fstype=fstype, label=label):
                self.disks[self.photos].update(fstype=fstype, label=label)
                with self.assertRaises(SystemExit):
                    self.initialize()
                self.assertEqual(self.mutations, [])

    def test_stale_udev_cannot_hide_an_actual_foreign_filesystem_label(self):
        self.udev_stale = True
        self.signatures[self.photos] = [{"type": "ext4", "label": "foreign"}]
        with self.assertRaisesRegex(SystemExit, "foreign label or signature"):
            self.initialize()
        self.assertEqual(self.mutations, [])

    def test_initialization_preserves_live_nfs_and_normal_cutover_refuses_it(self):
        self.mounts["/mnt/photos"] = {"source": "10.77.0.1:/tank/photos", "fstype": "nfs4", "options": "rw,noatime"}
        self.initialize()
        self.mutations.clear()
        with self.assertRaisesRegex(SystemExit, "mount"):
            self.execute()
        self.assertEqual(self.mutations, [])
        self.assertEqual(self.mounts["/mnt/photos"]["fstype"], "nfs4")

    def test_docker_start_requires_correct_rw_noatime_local_mounts(self):
        self.initialize()
        with self.assertRaisesRegex(SystemExit, "mount"):
            self.execute("--mounted")
        for path, device in (("/mnt/photos", self.photos), ("/mnt/files", self.files)):
            self.mounts[path] = {"source": self.disks[device]["path"], "fstype": "ext4", "options": "rw,noatime"}
        self.execute("--mounted")
        for bad in ({"source": "/dev/foreign"}, {"fstype": "nfs4"},
                    {"options": "ro,noatime"}, {"options": "rw,relatime"}):
            with self.subTest(bad=bad):
                before = self.mounts["/mnt/photos"].copy()
                self.mounts["/mnt/photos"].update(bad)
                with self.assertRaisesRegex(SystemExit, "mount"):
                    self.execute("--mounted")
                self.mounts["/mnt/photos"] = before


if __name__ == "__main__":
    unittest.main()
