"""A failed resume must retain the durable recovery marker, including in traps."""

from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from jinja2 import Environment, StrictUndefined
import yaml


ROOT = Path(__file__).resolve().parents[1]


class ResumeRecovery(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="homelab-resume-test-")
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name)
        self.marker = self.work / "guest-needs-resume"
        self.marker.touch()
        values = yaml.safe_load((ROOT / "roles/pve_backup/defaults/main.yml").read_text())
        values.update(ntfy_url="https://example.invalid", ntfy_topic_alerts="alerts", ntfy_topic_info="info")
        environment = Environment(undefined=StrictUndefined)
        environment.filters["quote"] = lambda value: shlex.quote(str(value))
        template = environment.from_string((ROOT / "roles/pve_backup/templates/common.sh.j2").read_text())
        self.common = self.work / "common.sh"
        self.common.write_text(template.render(**values))

    def test_failed_ssh_inside_conditional_retains_resume_marker(self):
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; STATE="$2"; SSH=(false); if resume_guest; then exit 99; fi; test -f "$STATE/guest-needs-resume"',
             "resume-test", str(self.common), str(self.work)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.exists())

    def test_successful_resume_clears_marker(self):
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; STATE="$2"; SSH=(true); resume_guest',
             "resume-test", str(self.common), str(self.work)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
