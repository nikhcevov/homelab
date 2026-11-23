"""Managed imports resume without duplicating disks or adopting foreign volumes."""

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jinja2 import Environment, StrictUndefined
import yaml


ROOT = Path(__file__).resolve().parents[1]


class ManagedVMResume(unittest.TestCase):
    def setUp(self):
        values = yaml.safe_load((ROOT / "roles/pve_vm/defaults/main.yml").read_text())
        values.update(yaml.safe_load((ROOT / "inventory/group_vars/pve/vm.yml").read_text()))
        self.values = values
        self.render()
        self.data_storage = values["pve_vm_data_storage"]
        self.storage = values["pve_vm_storage"]
        self.root_volume = f"{self.storage}:vm-{values['pve_vm_id']}-disk-0"
        self.volumes = {self.root_volume: {"size": "3G", "data": b"existing imported operating system"}}
        self.configuration = {
            "description": "homelab-managed-docker-vm", "name": values["pve_vm_name"],
            "onboot": "0", "memory": str(values["pve_vm_memory"]), "cores": str(values["pve_vm_cores"]),
            "cpu": "host", "machine": "q35", "bios": "seabios", "scsihw": "virtio-scsi-single",
            "unused0": self.root_volume,
        }
        self.exists = True
        self.running = False
        self.mutations = []

    def render(self):
        environment = Environment(undefined=StrictUndefined)
        environment.filters["to_json"] = json.dumps
        environment.filters["bool"] = bool
        template = environment.from_string((ROOT / "roles/pve_vm/templates/provision.py.j2").read_text())
        self.program = compile(template.render(**self.values), "provision.py", "exec")

    def inspect(self, args, **kwargs):
        args = [str(value) for value in args]
        if args[0] == "pvesm":
            raise subprocess.CalledProcessError(2, args, stderr="Unknown option: output-format")
        if args[:2] == ["pvesh", "get"]:
            storage = args[2].split("/")[-2]
            expected = f"/nodes/localhost/storage/{storage}/content"
            if args[2] != expected or args[3:] != ["--vmid", str(self.values["pve_vm_id"]), "--output-format", "json"]:
                raise subprocess.CalledProcessError(2, args)
            return json.dumps([{"volid": volume, "content": "images", "format": "raw"}
                               for volume in self.volumes if volume.startswith(storage + ":")])
        if args[:2] == ["qm", "config"]:
            return "\n".join(f"{key}: {value}" for key, value in self.configuration.items())
        if args[:2] == ["qm", "status"]:
            return "status: " + ("running" if self.running else "stopped")
        if args[:2] == ["readlink", "-f"]:
            return "/sys/bus/pci/drivers/vfio-pci"
        raise AssertionError(f"Unexpected inspection: {args}")

    def mutate(self, args):
        args = [str(value) for value in args]
        self.mutations.append(args)
        if args[:2] == ["qm", "set"]:
            key, value = args[3][2:], args[4]
            if key == "scsi0":
                self.assertEqual(value.split(",")[0], self.root_volume)
                self.configuration.pop("unused0")
                value += ",size=" + self.volumes[self.root_volume]["size"]
            elif key in ("scsi1", "scsi2", "scsi3") and value.split(",")[0].split(":")[-1].isdigit():
                allocation, options = value.split(",", 1)
                storage, size = allocation.split(":")
                size += "G"
                volume = f"{storage}:vm-{self.values['pve_vm_id']}-disk-{key[4:]}"
                self.volumes[volume] = {"size": size, "data": b""}
                value = volume + "," + options + ",size=" + size
            elif key == "ide2":
                value = self.storage + ":vm-" + str(self.values["pve_vm_id"]) + "-cloudinit,media=cdrom"
            elif key == "efidisk0":
                volume = f"{self.storage}:vm-{self.values['pve_vm_id']}-disk-2"
                self.volumes[volume] = {"size": "4M", "data": b"EFI variable storage"}
                value = volume + "," + value.split(",", 1)[1] + ",size=4M"
            self.configuration[key] = value
        elif args[:2] == ["qm", "resize"]:
            old_size = self.volumes[self.root_volume]["size"]
            self.volumes[self.root_volume]["size"] = args[4]
            self.configuration["scsi0"] = self.configuration["scsi0"].replace("size=" + old_size, "size=" + args[4])
        elif args[:2] == ["qm", "start"]:
            self.running = True
        else:
            raise AssertionError(f"Unexpected mutation of an existing import: {args}")

    def execute(self):
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=0 if self.exists else 1)), \
             patch("subprocess.check_output", side_effect=self.inspect), \
             patch("subprocess.check_call", side_effect=self.mutate):
            exec(self.program, {})

    def test_existing_import_is_attached_without_duplicate_or_overwrite(self):
        self.execute()
        self.assertTrue(self.running)
        self.assertEqual(self.configuration["scsi0"].split(",")[0], self.root_volume)
        self.assertEqual(self.volumes[self.root_volume]["data"], b"existing imported operating system")
        attached = {self.configuration[key].split(",")[0] for key in ("scsi0", "scsi1", "scsi2", "scsi3", "efidisk0")}
        self.assertEqual(set(self.volumes), attached)
        self.assertNotIn("unused0", self.configuration)

    def test_efi_variables_cannot_overwrite_the_os_volume(self):
        self.configuration["efidisk0"] = self.root_volume + ",efitype=4m,pre-enrolled-keys=0"
        with self.assertRaises(SystemExit):
            self.execute()
        self.assertFalse(self.running)
        self.assertEqual(self.volumes[self.root_volume]["data"], b"existing imported operating system")

    def test_orphan_volume_is_not_adopted_by_a_new_vm(self):
        self.exists = False
        with self.assertRaises(SystemExit):
            self.execute()
        self.assertEqual(self.mutations, [])
        self.assertEqual(self.volumes[self.root_volume]["data"], b"existing imported operating system")

    def test_new_data_disks_use_dedicated_storage_and_are_backed_up(self):
        self.execute()
        for slot, size, serial in (("scsi2", "3072G", "homelab-photos"),
                                   ("scsi3", "256G", "homelab-files")):
            self.assertEqual(self.configuration[slot],
                             f"tank-vm:vm-100-disk-{slot[4:]},serial={serial},discard=on,iothread=1,backup=1,size={size}")

    def test_staging_excludes_only_data_disks_from_backup(self):
        self.values["pve_vm_data_backup"] = False
        self.render()
        self.execute()
        self.assertIn(",backup=0,", self.configuration["scsi2"])
        self.assertIn(",backup=0,", self.configuration["scsi3"])
        self.assertNotIn("backup=0", self.configuration["scsi0"])
        self.assertNotIn("backup=0", self.configuration["scsi1"])

    def test_running_vm_hot_adds_only_authorized_missing_disks(self):
        self.execute()
        for slot in ("scsi2", "scsi3"):
            volume = self.configuration.pop(slot).split(",")[0]
            del self.volumes[volume]
        self.mutations.clear()
        self.execute()
        self.assertEqual([command[3] for command in self.mutations], ["--scsi2", "--scsi3"])
        self.assertTrue(self.running)

    def test_hot_add_refuses_unrelated_live_config_drift(self):
        self.execute()
        volume = self.configuration.pop("scsi2").split(",")[0]
        del self.volumes[volume]
        self.configuration["net0"] = "virtio=BC:24:11:36:00:01,bridge=foreign"
        self.mutations.clear()
        with self.assertRaisesRegex(SystemExit, "stop it"):
            self.execute()
        self.assertEqual(self.mutations, [])

    def test_hot_add_requires_disk_hotplug_without_enabling_it(self):
        self.execute()
        volume = self.configuration.pop("scsi2").split(",")[0]
        del self.volumes[volume]
        self.configuration["hotplug"] = "network,usb"
        self.mutations.clear()
        with self.assertRaisesRegex(SystemExit, "hotplug"):
            self.execute()
        self.assertEqual(self.mutations, [])

    def test_foreign_data_volume_or_identity_is_never_replaced(self):
        self.execute()
        for bad in ("other:vm-100-disk-2,serial=homelab-photos,size=3072G",
                    "tank-vm:vm-101-disk-2,serial=homelab-photos,size=3072G",
                    "tank-vm:vm-100-disk-2,serial=homelab-photos-old,size=3072G",
                    "tank-vm:vm-100-disk-2,serial=homelab-photos,size=3071G"):
            with self.subTest(disk=bad):
                self.configuration["scsi2"] = bad
                self.mutations.clear()
                with self.assertRaisesRegex(SystemExit, "Unknown data disk"):
                    self.execute()
                self.assertEqual(self.mutations, [])

    def test_unattached_data_volume_is_not_adopted_or_duplicated(self):
        self.execute()
        self.configuration.pop("scsi2")
        self.mutations.clear()
        with self.assertRaisesRegex(SystemExit, "orphan"):
            self.execute()
        self.assertEqual(self.mutations, [])

    def test_backup_cutover_preserves_volume_identity_and_contents(self):
        self.values["pve_vm_data_backup"] = False
        self.render()
        self.execute()
        photos_volume = self.configuration["scsi2"].split(",")[0]
        self.volumes[photos_volume]["data"] = b"precious photos"
        self.running = False
        self.values["pve_vm_data_backup"] = True
        self.render()
        self.execute()
        self.assertEqual(self.configuration["scsi2"].split(",")[0], photos_volume)
        self.assertEqual(self.volumes[photos_volume]["data"], b"precious photos")
        self.assertIn(",backup=1,", self.configuration["scsi2"])

    def test_equivalent_terabyte_size_is_accepted_without_resize(self):
        self.execute()
        self.configuration["scsi2"] = self.configuration["scsi2"].replace("size=3072G", "size=3T")
        self.mutations.clear()
        self.execute()
        self.assertEqual(self.mutations, [])

    def test_running_backup_flag_change_requires_stop_without_partial_hot_add(self):
        self.values["pve_vm_data_backup"] = False
        self.render()
        self.execute()
        volume = self.configuration.pop("scsi2").split(",")[0]
        del self.volumes[volume]
        self.values["pve_vm_data_backup"] = True
        self.render()
        self.mutations.clear()
        with self.assertRaisesRegex(SystemExit, "stop it"):
            self.execute()
        self.assertEqual(self.mutations, [])

    def test_pending_live_changes_block_hot_add(self):
        self.execute()
        volume = self.configuration.pop("scsi2").split(",")[0]
        del self.volumes[volume]
        self.mutations.clear()
        original_inspect = self.inspect

        def pending_inspect(args, **kwargs):
            result = original_inspect(args, **kwargs)
            if args == ["qm", "config", "100"]:
                result += "\nnet0: virtio=BC:24:11:36:00:01,bridge=foreign"
            return result

        with patch.object(self, "inspect", side_effect=pending_inspect):
            with self.assertRaisesRegex(SystemExit, "pending"):
                self.execute()
        self.assertEqual(self.mutations, [])

    def test_orphan_bulk_volume_blocks_new_vm_creation(self):
        self.exists = False
        self.volumes = {"tank-vm:vm-100-disk-0": {"size": "3072G", "data": b"unknown"}}
        with self.assertRaisesRegex(SystemExit, "orphan"):
            self.execute()
        self.assertEqual(self.mutations, [])


if __name__ == "__main__":
    unittest.main()
