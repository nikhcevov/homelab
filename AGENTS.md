# homelab

Repository overview and guide map: [README.md](README.md). Maintainer workflow: [CONTRIBUTING.md](CONTRIBUTING.md).

## Pre-merge gate

Run from the repository root with the Python 3.14 venv and pinned collections.

```bash
.venv/bin/python tests/check_ansible.py
.venv/bin/python tests/check_compose.py
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Markdown changes also run:

```bash
npx --yes markdownlint-cli2@0.23.3 '*.md' 'docs/**/*.md' 'files/**/*.md' '.github/**/*.md'
lychee --offline --include-fragments --no-progress '*.md' 'docs/**/*.md' 'files/**/*.md' '.github/**/*.md'
```

The checks are offline: no SSH, vault password, production inventory, or Docker daemon. Use the `homelab-verify` skill for the full procedure and evidence format.

## Invariants

- One authority per fact: inventory for hosts, playbooks for role composition, role defaults and vars for values, tasks and templates for behavior, guides for rationale and recovery.
- Update the affected guide in the same behavior change; internal-only changes need no documentation edit.
- Never commit plaintext credentials. Compose secrets use `vault_*` references; no `compose/**/.env`.
- Read facts through `ansible_facts['...']`, not injected top-level variables.
- Tailscale policy changes go through a branch or PR; pushing to `main` applies them live.

## Layout

`playbooks/` entrypoints, `roles/` role content, `compose/` stacks, `inventory/` hosts and variables, `docs/` runbooks, `tests/` offline gates.
