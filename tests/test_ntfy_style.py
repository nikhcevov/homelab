from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTIFY = ROOT / "roles/monitoring/files/scripts/notify.sh"


class NotificationStyleTest(unittest.TestCase):
    def render(self, severity: str, component: str, event: str) -> tuple[list[str], str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env_file = root / "env"
            env_file.write_text(
                "\n".join(
                    [
                        "NTFY_URL=https://ntfy.example",
                        "NTFY_TOPIC_CRITICAL=critical-topic",
                        "NTFY_TOPIC_ALERTS=alerts-topic",
                        "NTFY_TOPIC_INFO=info-topic",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_curl = root / "curl"
            fake_curl.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$@\" > \"$CAPTURE_ARGS\"\n"
                "while [ $# -gt 0 ]; do\n"
                "  case \"$1\" in\n"
                "    -d|--data|--data-binary)\n"
                "      shift\n"
                "      printf '%s' \"$1\" > \"$CAPTURE_BODY\"\n"
                "      ;;\n"
                "  esac\n"
                "  shift\n"
                "done\n",
                encoding="utf-8",
            )
            fake_curl.chmod(0o755)

            script = root / "notify.sh"
            script.write_text(NOTIFY.read_text(encoding="utf-8"), encoding="utf-8")

            env = os.environ.copy()
            env["PATH"] = f"{root}:{env['PATH']}"
            env["NTFY_ENV_FILE"] = str(env_file)
            env["NTFY_STATE_DIR"] = str(root / "state")
            env["CAPTURE_ARGS"] = str(root / "args")
            env["CAPTURE_BODY"] = str(root / "body")
            subprocess.run(
                [
                    "bash",
                    "-c",
                    f'source "{script}" && send_ntfy "{severity}" "{component}" "{event}" "summary" "details" "action"',
                ],
                check=True,
                env=env,
                capture_output=True,
                text=True,
            )
            return (
                (root / "args").read_text(encoding="utf-8").splitlines(),
                (root / "body").read_text(encoding="utf-8"),
            )

    def test_critical_envelope(self) -> None:
        args, body = self.render("critical", "Disk", "test at 90%")
        self.assertIn("Title: 🚨 Homelab · Disk · test at 90%", args)
        self.assertIn("Priority: urgent", args)
        self.assertIn("Tags: rotating_light,disk", args)
        self.assertIn("Markdown: yes", args)
        self.assertTrue(body.startswith("**summary**\n\n"))
        self.assertIn("- **Component:** `Disk`", body)
        self.assertIn("- **State:** `test at 90%`", body)
        self.assertIn("- **Details:** details", body)
        self.assertIn("- **Action:** action", body)

    def test_resolved_envelope(self) -> None:
        args, _ = self.render("resolved", "Backup", "fresh again")
        self.assertIn("Title: ✅ Homelab · Backup · fresh again", args)
        self.assertIn("Priority: default", args)
        self.assertIn("Tags: white_check_mark,backup", args)
