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
        environment = Environment(undefined=StrictUndefined)
        environment.filters["to_json"] = json.dumps
        template = environment.from_string((ROOT / "roles/pve_vm/templates/provision.py.j2").read_text())
        self.program = compile(template.render(**values), "provision.py", "exec")
        self.values = values
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

    def inspect(self, args, **kwargs):
        args = [str(value) for value in args]
        if args[0] == "pvesm":
            raise subprocess.CalledProcessError(2, args, stderr="Unknown option: output-format")
        if args[:2] == ["pvesh", "get"]:
            expected = f"/nodes/localhost/storage/{self.storage}/content"
            if args[2] != expected or args[3:] != ["--vmid", str(self.values["pve_vm_id"]), "--output-format", "json"]:
                raise subprocess.CalledProcessError(2, args)
            return json.dumps([{"volid": volume, "content": "images", "format": "raw"} for volume in self.volumes])
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
            elif key == "scsi1":
                allocation, options = value.split(",", 1)
                size = allocation.split(":")[1] + "G"
                volume = f"{self.storage}:vm-{self.values['pve_vm_id']}-disk-1"
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
        attached = {self.configuration[key].split(",")[0] for key in ("scsi0", "scsi1", "efidisk0")}
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


if __name__ == "__main__":
    unittest.main()
