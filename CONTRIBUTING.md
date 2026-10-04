# Homelab maintenance

[Repository overview](README.md)

## Solo-first workflow

This is primarily a single-maintainer homelab. The guides are runbooks for
future-you: how to deploy, verify, and recover without relying on memory.

- Routine changes do not need a PR or a second reviewer. Direct updates to
  `main` are fine where repository branch rules allow them; check the CI result.
- Use a branch/PR when you want checks before merging, a reviewable checkpoint,
  or help from an occasional contributor. Self-review is enough for your own changes.
- Keep the branch/PR checkpoint for [Tailscale policy changes](docs/tailscale.md#normal-policy-changes):
  pushing policy changes to `main` triggers a live apply, not just a check.
- Update the relevant guide in the same behavior change. Internal-only changes
  need neither a documentation edit nor an explanation of why docs were unchanged.

Use the [README guide map](README.md#documentation) to find the affected guide.
Document changes to deployment, configuration interfaces, verification, manual
setup, or recovery behavior—not every YAML value adjustment.

## One authority per fact

- Hosts and connection settings: [inventory](inventory/hosts.ini).
- Role composition and tags: playbooks in `playbooks/`.
- Current configurable values and schemas: role defaults, group/host variables,
  and annotated examples such as [proxy.example.yml](vars/proxy.example.yml).
- Implemented behavior: tasks, templates, scripts, and workflows.
- Rationale, manual responsibilities, apply/verify/recovery procedures: guides.
- Historical measurements: retain the settings used, run date, commit/config,
  software versions, commands, and output; do not rewrite results when defaults change.

Link to authoritative configuration rather than duplicating complete lists or
schemas. Never commit plaintext credentials or private configuration to make a
check pass. Review desired configuration separately from observed deployed state.

## Guide structure

Keep README as the overview and navigation page. Focus each guide on a subsystem:

1. Scope and ownership: what automation overwrites and what remains manual.
2. Sources: clickable links to the playbooks and configuration.
3. Apply: prerequisites and commands, run from the repository root.
4. Verify: commands and the expected observable state.
5. Recover: rollback/restore instructions and their limitations.

Update backlinks and repository comment references when moving a section.
Use relative links for repository files and heading fragments for specific steps.
Keep measurements clearly separate from current configuration authority.

## Local Ansible checks

Use Python 3.14, matching the [Ansible workflow](.github/workflows/ansible.yml).
Controller and collection versions are pinned in
[requirements-controller.txt](requirements-controller.txt) and
[requirements.yml](requirements.yml). Prepare the environment from the repository root:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-controller.txt
ansible-galaxy collection install -r requirements.yml
python tests/check_ansible.py
```

Dependency installation downloads packages from PyPI and Ansible Galaxy. Once installed,
[the gate](tests/check_ansible.py) runs locally without network access, `.vault_pass`,
private `vars/proxy.yml`, production credentials, or SSH:

- Syntax-check every entrypoint in the flat `playbooks/` directory (currently 14);
  fail if no playbooks are discovered. Root `requirements.yml` is collection metadata.
- Render the existing nginx templates with [the public routing example](vars/proxy.example.yml).
- Reject duplicate SNI names, SNI over UDP, mixed SNI/plain listeners, multiple defaults,
  empty upstreams, missing backend ports, and missing listeners before rendering.

Each run creates and removes a temporary Ansible configuration, localhost-only inventory,
and render directory. It ignores inherited vault/controller overrides, preserves an
explicit `ANSIBLE_COLLECTIONS_PATH`, and does not use the production inventory.

The workflow runs `Ansible checks` on PRs targeting `main`, pushes to `main`, and manual
dispatches. Action revisions and tooling versions are pinned; repository permissions are
read-only and checkout credentials are not persisted. It never deploys hosts.
The gate checks Ansible syntax and template/definition behavior, not `nginx -t` or deployed health.

Access gathered facts through `ansible_facts['os_family']`,
`ansible_facts['distribution']`, etc., rather than injected top-level variables
such as `ansible_os_family`. Automatic fact injection is deprecated; use
`inject_facts_as_vars = false` in isolated role smoke checks to catch reliance on it.

## Local documentation checks

Use Node.js 24 with npm, and [lychee](https://github.com/lycheeverse/lychee/releases/tag/lychee-v0.24.2)
version 0.24.2. Run from the repository root:

```bash
npx --yes markdownlint-cli2@0.23.3 '*.md' 'docs/**/*.md' 'files/**/*.md' '.github/**/*.md'
lychee --offline --include-fragments --no-progress '*.md' 'docs/**/*.md' 'files/**/*.md' '.github/**/*.md'
```

The [Documentation workflow](.github/workflows/docs.yml) runs these checks on
PRs targeting `main` and pushes to `main`, including source-only changes that might rename a
linked file. It uses pinned action revisions and checker versions, read-only
repository access, and no deployment credentials.

Formatting follows [.markdownlint.jsonc](.markdownlint.jsonc); long operational
commands, source links, and tables are allowed. Link checks validate local files,
directories, and Markdown headings. External URLs are intentionally skipped to
keep the merge gate independent of external-site availability and authenticated pages.

These checks do not prove semantic accuracy or deployed health. For an operational
change, exercise the affected path and keep useful evidence in the commit, optional
PR, or runbook; do not create paperwork for internal-only changes. Review apply,
verify, and recovery guidance against the implementation.

Required review approvals are not part of this solo workflow. Branch protection
is optional: require `Documentation checks` and `Ansible checks` if you want enforced
pre-merge checks. The workflows themselves do not configure repository branch rules.
