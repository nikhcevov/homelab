from __future__ import annotations

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALERTING = ROOT / "compose/observability/alerting"


class GrafanaProvisioningTest(unittest.TestCase):
    def test_alerting_yaml_is_parseable_and_complete(self) -> None:
        rules = yaml.safe_load((ALERTING / "rules.yml").read_text())
        policies = yaml.safe_load((ALERTING / "policies.yml").read_text())

        group = rules["groups"][0]
        self.assertEqual(group["folder"], "Homelab Alerts")
        self.assertEqual(len(group["rules"]), 11)
        self.assertTrue(
            all(
                rule["labels"]["severity"] in {"critical", "warning"}
                for rule in group["rules"]
            )
        )
        self.assertEqual(policies["policies"][0]["receiver"], "ntfy-alerts")
        self.assertEqual(
            policies["policies"][0]["routes"][0]["receiver"], "ntfy-critical"
        )

    def test_contact_points_do_not_commit_plaintext_topics(self) -> None:
        template = (ALERTING / "contact-points.yml.j2").read_text()
        self.assertIn("{{ ntfy_url }}", template)
        self.assertIn("{{ ntfy_topic_alerts }}", template)
        self.assertIn("{{ ntfy_topic_critical }}", template)
        self.assertNotIn("ntfy.sh/han-", template)
