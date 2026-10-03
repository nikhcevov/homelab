#!/usr/bin/env python3
"""Check playbook syntax and proxy validation without deployment credentials."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOKS = ROOT / "playbooks"
PROXY_EXAMPLE = ROOT / "vars/proxy.example.yml"


def invalid_services(services):
    cases = {}

    duplicate_sni = copy.deepcopy(services)
    duplicate_sni["homeassistant"]["sni"] = [services["unraid"]["sni"][0]]
    cases["duplicate-sni"] = duplicate_sni

    udp_sni = copy.deepcopy(services)
    udp_sni["voicechat"]["sni"] = ["voice.example.com"]
    cases["udp-sni"] = udp_sni

    mixed_listener = copy.deepcopy(services)
    del mixed_listener["homeassistant"]["sni"]
    cases["mixed-listener"] = mixed_listener

    multiple_defaults = copy.deepcopy(services)
    multiple_defaults["unraid"]["default"] = True
    multiple_defaults["homeassistant"]["default"] = True
    cases["multiple-defaults"] = multiple_defaults

    empty_upstream = copy.deepcopy(services)
    empty_upstream["minecraft"]["upstream"] = []
    cases["empty-upstream"] = empty_upstream

    missing_backend_port = copy.deepcopy(services)
    del missing_backend_port["minecraft"]["upstream"]["port"]
    cases["missing-backend-port"] = missing_backend_port

    missing_listener = copy.deepcopy(services)
    del missing_listener["minecraft"]["listen"]
    cases["missing-listener"] = missing_listener

    return cases


def main():
    playbooks = sorted(PLAYBOOKS.glob("*.yml"))
    if not playbooks:
        raise SystemExit(f"No playbooks found in {PLAYBOOKS}")
    with tempfile.TemporaryDirectory(prefix="homelab-ansible-check-") as directory:
        work = Path(directory)
        config = work / "ansible.cfg"
        config.write_text(
            "[defaults]\n"
            "retry_files_enabled = false\n"
            "collections_scan_sys_path = false\n"
            f"roles_path = {ROOT / 'roles'}\n"
            f"local_tmp = {work / 'ansible-tmp'}\n"
        )
        inventory = work / "inventory.ini"
        inventory.write_text(
            "localhost ansible_connection=local "
            f"ansible_python_interpreter={json.dumps(sys.executable)}\n"
        )
        # Ignore controller overrides that could load credentials or custom plugins.
        # Keep a dedicated collection path available for isolated dependency installs.
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("ANSIBLE_") or key == "ANSIBLE_COLLECTIONS_PATH"
        }
        environment.update(ANSIBLE_CONFIG=str(config), ANSIBLE_NOCOLOR="1")
        command = [str(Path(sys.executable).with_name("ansible-playbook")), "-i", str(inventory)]

        def run(arguments):
            return subprocess.run(
                command + arguments,
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
            )

        syntax = run(["--syntax-check", *map(str, playbooks)])
        if syntax.returncode:
            raise SystemExit(syntax.stdout + syntax.stderr)
        print(f"PASS syntax checks: {len(playbooks)} playbooks", flush=True)

        def render(case_name, services=None):
            output = work / case_name
            output.mkdir()
            variables = {
                "proxy_vars_file": str(PROXY_EXAMPLE),
                "proxy_render_dir": str(output),
            }
            if services is not None:
                variables["services"] = services
            result = run([str(PLAYBOOKS / "test-render.yml"), "-e", json.dumps(variables)])
            return result, output

        valid, _ = render("valid")
        if valid.returncode:
            raise SystemExit(valid.stdout + valid.stderr)
        print("PASS public fixture: shared SNI listener, plain TCP, and UDP rendering", flush=True)

        services = yaml.safe_load(PROXY_EXAMPLE.read_text())["services"]
        for case_name, invalid in invalid_services(services).items():
            result, output = render(case_name, invalid)
            if result.returncode != 2 or any(output.iterdir()):
                raise SystemExit(
                    f"FAIL {case_name}: expected rejection before rendering\n"
                    + result.stdout
                    + result.stderr
                )
            print(f"PASS reject {case_name} before rendering", flush=True)


if __name__ == "__main__":
    main()
