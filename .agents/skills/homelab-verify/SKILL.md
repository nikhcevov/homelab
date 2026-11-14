---
name: homelab-verify
description: Use when validating changes in this homelab repository before commit, push, or claiming work is complete — including "verify", "run the gate", "is this ready", "did I break anything", or after edits to playbooks, roles, compose stacks, inventory, or docs. Runs the same offline Ansible, Compose, migration, and documentation checks as CI, reports command evidence, and never deploys or decrypts secrets.
---

# Homelab verify

Run the repository's pre-merge gate from the repository root. The Ansible and
Compose checks are offline: no SSH, no vault password, no production inventory,
and no Docker daemon for the Compose parse. That is deliberate: the gate proves
the change is internally consistent without touching hosts.

This skill reports; it does not fix. If a check fails, stop and hand back the
failing output so the fix can be a separate, reviewable change.

## Quick decision

| Changed | Minimum evidence before claiming done |
|---|---|
| `playbooks/`, `roles/`, `inventory/`, `vars/` | Ansible check + unittests |
| `compose/` | Compose check + unittests |
| `*.md`, `docs/`, `files/`, `.github/` | Documentation checks |
| Anything before push | All four checks |

When in doubt, run the whole gate; CI runs all of it anyway.

## Prerequisites

- Python 3.14 controller from `requirements-controller.txt` (the repo `.venv`).
- Pinned collections from `requirements.yml` (`community.general`, `ansible.posix`).
- Docker CLI with Compose v2 (`docker compose version`).
- Node.js 24 for Markdown lint; `lychee` v0.24.2 for local link checks.

Prefer the repo venv:

```bash
test -x .venv/bin/python && PY=.venv/bin/python || PY=python3.14
```

## Setup (only when missing)

This is the only networked step. Skip it when `.venv` and the pinned
collections already exist.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-controller.txt
ansible-galaxy collection install -r requirements.yml
```

If `check_ansible.py` reports `couldn't resolve module/action
'community.general.*'`, the collections are missing; run the last command and
retry. Do not substitute a different collection version.

## Gate (run in this order)

### 1. Ansible syntax and proxy render

```bash
"$PY" tests/check_ansible.py
```

Syntax-checks every `playbooks/*.yml`, renders the nginx templates from
`vars/proxy.example.yml`, and rejects invalid SNI, listener, upstream, and
backend-port fixtures. Fails if no playbooks are discovered.

### 2. Compose stacks and migration regressions

```bash
"$PY" tests/check_compose.py
"$PY" -m unittest discover -s tests -p 'test_*.py'
```

Every `compose/*/compose.yaml` is parsed with synthetic, never-decrypted
secrets. `check_compose.py` also verifies that every `vault_*` reference exists
in `inventory/**/vault.yml` and rejects plaintext `compose/**/.env`.
The unittest suite covers backup resume, PVE VM rendering, and tree
verification, using real `rsync` against isolated temporary files.

### 3. Documentation checks (when Markdown changed)

```bash
npx --yes markdownlint-cli2@0.23.3 '*.md' 'docs/**/*.md' 'files/**/*.md' '.github/**/*.md'
lychee --offline --include-fragments --no-progress '*.md' 'docs/**/*.md' 'files/**/*.md' '.github/**/*.md'
```

Markdown lint is required for documentation changes. Link checking validates
local files, directories, and heading fragments only; external URLs are
intentionally skipped. If `lychee` is not installed, report the link check as
NOT RUN. When the user wants that evidence anyway, fetch the pinned
`lychee-v0.24.2` release into `/tmp` and run it from there; do not install it
system-wide, add it to the repo, or claim the check passed without running it.

## Reporting

- State each command and its exit status.
- On failure, quote the failing assertion or output and stop. Do not claim the
  gate passed.
- Summarize as: Ansible PASS/FAIL, Compose PASS/FAIL, unittests N passed,
  Docs PASS/FAIL/NOT RUN.
- For an operational change, keep the commands and useful output with the
  commit, PR, or runbook.

## Boundaries and why

- The gate validates files, not hosts. Running `ansible-playbook` against
  `inventory/hosts.ini` would apply changes to live machines; static proof is
  where this skill stops.
- Vault decryption is unnecessary because `check_compose.py` substitutes
  synthetic values. Reading `.vault_pass` or creating `vars/proxy.yml` only
  exposes secrets for no extra signal.
- Committing a plaintext `compose/**/.env` to make a check pass trades a local
  green for a leaked credential.
- The unittest run writes `tests/__pycache__/`. That is a side effect, not part
  of the change: leave it untracked and keep it out of the commit. If it keeps
  showing up, propose adding `__pycache__/` and `*.pyc` to `.gitignore` as a
  separate change.
- These checks cannot prove deployed health: they do not run `nginx -t`, contact
  services, or compare a host's actual state. Say "static checks pass", not
  "the deployment works".

## Intentionally not covered

- `nginx -t` and live routing behavior.
- Applying playbooks, Tailscale policy, or Compose stacks.
- External link availability (lychee runs with `--offline`).
