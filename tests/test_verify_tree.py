"""Exercise the destructive-migration gate against real rsync comparisons."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify-tree.py"


class TreeComparison(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="homelab-tree-test-")
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / "source"
        self.destination = Path(self.directory.name) / "destination"
        self.source.mkdir()
        self.destination.mkdir()
        (self.source / "photo").write_bytes(b"original")
        os.link(self.source / "photo", self.source / "hardlink")
        (self.source / "symlink").symlink_to("photo")
        subprocess.run(
            ["rsync", "-aHAX", "--numeric-ids", str(self.source) + "/", str(self.destination) + "/"],
            check=True, capture_output=True,
        )

    def compare(self):
        stamp = self.source.stat()
        os.utime(self.destination, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.source), str(self.destination)],
            capture_output=True, text=True,
        )

    def test_identical_copy_passes(self):
        self.assertEqual(self.compare().returncode, 0)

    def test_same_size_same_timestamp_corruption_fails_without_repair(self):
        target = self.destination / "photo"
        stamp = target.stat()
        target.write_bytes(b"corrupt!")
        os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertEqual(self.compare().returncode, 1)
        self.assertEqual(target.read_bytes(), b"corrupt!")

    def test_destination_only_file_fails_without_deletion(self):
        extra = self.destination / "extra"
        extra.write_text("must not be silently ignored")
        self.assertEqual(self.compare().returncode, 1)
        self.assertTrue(extra.exists())

    def test_missing_file_fails(self):
        (self.destination / "photo").unlink()
        self.assertEqual(self.compare().returncode, 1)

    def test_broken_hardlink_topology_fails(self):
        target = self.destination / "hardlink"
        stamp = target.stat()
        target.unlink()
        target.write_bytes(b"original")
        os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertEqual(self.compare().returncode, 1)

    def test_symlink_target_difference_fails(self):
        target = self.destination / "symlink"
        target.unlink()
        target.symlink_to("hardlink")
        self.assertEqual(self.compare().returncode, 1)

    def test_same_directory_cannot_falsely_verify_staging(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.source), str(self.source)],
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
