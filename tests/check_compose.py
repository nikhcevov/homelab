#!/usr/bin/env python3
"""Validate every stack with Compose and synthetic, never decrypted, secrets."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
VAULT_REFERENCE = re.compile(r"\bvault_[A-Za-z0-9_]+\b")


class VaultNamesLoader(yaml.SafeLoader):
    pass


VaultNamesLoader.add_constructor("!vault", lambda loader, node: None)


def main():
    vault_names = set()
    for path in (ROOT / "inventory").rglob("vault.yml"):
        vault_names.update(yaml.load(path.read_text(), Loader=VaultNamesLoader) or {})
    stacks = sorted(path.parent for path in (ROOT / "compose").glob("*/compose.yaml"))
    if not stacks:
        raise SystemExit("No Compose stacks found")
    references = set()
    for path in (ROOT / "compose").rglob("*.j2"):
        references.update(VAULT_REFERENCE.findall(path.read_text()))
    missing = references - vault_names
    if missing:
        raise SystemExit("Undefined vaulted values: " + ", ".join(sorted(missing)))
    plaintext = list((ROOT / "compose").rglob(".env"))
    if plaintext:
        raise SystemExit("Plaintext Compose environments must not live in the repository")
    fixture_secret = "fixture-$dollar${variable}#quote\" slash\\end'"
    with tempfile.TemporaryDirectory(prefix="homelab-compose-check-") as directory:
        work = Path(directory)
        variables = {name: fixture_secret for name in references}
        variables.update(
            vault_caddy_acme_email="admin@example.net",
            vault_caddy_public_domain="public.example.net",
            vault_caddy_notes_domain="notes.example.net",
        )
        tasks = []
        for stack in stacks:
            target = work / stack.name
            target.mkdir()
            for source in stack.iterdir():
                if source.suffix in (".yaml", ".yml"):
                    shutil.copy2(source, target / source.name)
            tasks.append({
                "name": "Render synthetic " + stack.name,
                "ansible.builtin.template": {
                    "src": str(stack / ".env.j2"),
                    "dest": str(target / ".env"),
                    "mode": "0600",
                },
            })
        playbook = work / "render.yml"
        playbook.write_text(yaml.safe_dump([{
            "hosts": "localhost", "gather_facts": False,
            "vars_files": [str(ROOT / "inventory/group_vars/docker/compose.yml")],
            "vars": variables,
            "tasks": tasks,
        }]))
        inventory = work / "inventory"
        inventory.write_text("localhost ansible_connection=local ansible_python_interpreter=" + sys.executable + "\n")
        config = work / "ansible.cfg"
        config.write_text("[defaults]\ninject_facts_as_vars=false\nretry_files_enabled=false\nlocal_tmp=" + str(work / "ansible-tmp") + "\n")
        environment = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_") or key == "ANSIBLE_COLLECTIONS_PATH"}
        environment.update(ANSIBLE_CONFIG=str(config), ANSIBLE_NOCOLOR="1")
        result = subprocess.run(
            [str(Path(sys.executable).with_name("ansible-playbook")), "-i", str(inventory), str(playbook)],
            cwd=ROOT, env=environment, capture_output=True, text=True,
        )
        if result.returncode:
            raise SystemExit(result.stdout + result.stderr)
        for stack in stacks:
            target = work / stack.name
            result = subprocess.run(
                ["docker", "compose", "--project-directory", str(target), "--env-file", str(target / ".env"), "-f", str(target / "compose.yaml"), "config", "--format", "json"],
                cwd=target, capture_output=True, text=True,
            )
            if result.returncode:
                raise SystemExit(f"FAIL {stack.name}: {result.stderr}")
            json.loads(result.stdout)
            if stack.name == "homelable":
                # Config serialization re-escapes dollars for roundtripping;
                # --environment exposes the actual dotenv interpolation values.
                values_result = subprocess.run(
                    ["docker", "compose", "--project-directory", str(target), "--env-file", str(target / ".env"), "-f", str(target / "compose.yaml"), "config", "--environment"],
                    cwd=target, capture_output=True, text=True, check=True,
                )
                values = dict(line.split("=", 1) for line in values_result.stdout.splitlines() if "=" in line)
                for name in ("AUTH_PASSWORD_HASH", "MCP_API_KEY", "MCP_SERVICE_KEY", "SECRET_KEY"):
                    if values.get(name) != fixture_secret:
                        raise SystemExit(f"FAIL {stack.name}: literal secret altered by dotenv interpolation ({name})")
            print("PASS Compose configuration: " + stack.name, flush=True)
    print(f"PASS {len(stacks)} stacks; {len(references)} vaulted references exist; no plaintext Compose .env")


if __name__ == "__main__":
    main()
