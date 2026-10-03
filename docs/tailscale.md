# Tailscale access policy

[Repository overview](../README.md) · [Getting started](getting-started.md) · [Edge VPS](edge.md) · [OpenWrt](openwrt.md)

Sources: [policy file](../files/tailscale/policy.json), [policy workflow](../.github/workflows/tailscale.yml), and [shared Tailscale variables](../inventory/group_vars/all/tailscale.yml).

`files/tailscale/policy.json` is a standalone policy for the trusted-home model:
member-owned devices, trusted home servers, and the approved routed home LANs
retain full access; the edge can initiate only the proxy/game connections below.
It is ordinary JSON, which the Tailscale policy editor accepts as HuJSON.
Ansible does **not** apply this file. The [Tailscale policy workflow](../.github/workflows/tailscale.yml) is configured to validate pull requests and apply changes from `main`; it requires the Actions variables and Tailscale identity setup below.

| Desired machine | Required tag | Edge access |
| --------------- | ------------ | ----------- |
| `edge` | `tag:edge` | Source of the restricted grants |
| `great-hornbill` | `tag:home` | TCP 443, TCP 25565, UDP 24454 |
| `ha-krm` | `tag:homeassistant` | TCP 443 |

The operator confirmed no device uses the retired `tag:vps`; the repository
policy now declares only `tag:edge` for the restricted edge grants. Four native
policy tests remain: edge TCP/UDP accept/deny tests and trusted-home SSH tests
targeting the edge. This does not prove policy apply, machine-name or OS-hostname
changes, or deployment health.
Reserve `tag:edge` for restricted edge machines and `tag:home` for trusted Unraid
backends. Never put a trusted-home tag on the edge: permissions from multiple
tags are additive. Empty `tagOwners` lists leave assignment to tailnet
owners/admins/network admins.

Follow the [existing-node identity cutover](edge.md#existing-node-identity-cutover):
validate the policy PR, merge/apply, wait for **Apply policy** success, confirm
the existing node's restricted `tag:edge`, verify restrictions, then complete
any pending machine rename to `edge` and verify MagicDNS before updated Ansible.
No automatic tag advertising or re-authentication is introduced. Provider
policy validation needs the user-managed GitOps credentials; local JSON and
structural preservation checks are not provider test results.

The broad trusted grant deliberately includes **all invited tailnet members**,
the two home tags, and the currently advertised LANs `192.168.100.0/24` through
`192.168.103.0/24`. It also permits exit-node internet access. It does not approve
new routes, grant shared outsiders access, or enable Tailscale SSH; native
OpenSSH/Dropbear access remains subject to network grants and host SSH keys.
Direct LAN traffic is outside Tailscale policy enforcement.

## Installation platforms

The shared `tailscale` role supports Debian 12/13 and Ubuntu 24.04+, provided
Tailscale publishes a repository for the host's release. Distribution and
release codename facts select the repository; supported distribution/version
facts are checked before setup. These published paths have been verified:

| Host | Repository URI | Suite | Published key and repository definition |
| ---- | -------------- | ----- | --------------------------------------- |
| Debian 12 | `https://pkgs.tailscale.com/stable/debian` | `bookworm` | [key](https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg), [repository](https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list) |
| Debian 13 | `https://pkgs.tailscale.com/stable/debian` | `trixie` | [key](https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg), [repository](https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list) |
| Ubuntu 24.04 LTS | `https://pkgs.tailscale.com/stable/ubuntu` | `noble` | [key](https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg), [repository](https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list) |

The repository remains named `tailscale`, with its key at
`/usr/share/keyrings/tailscale-archive-keyring.gpg`. Existing installs are
reconciled to the matching repository without removing or upgrading the package.
For rollback, revert the role change and rerun only on Debian 12; the previous
Bookworm-only implementation is not a valid rollback for Debian 13 or Ubuntu.

Other Debian-family distributions (including derivatives), Debian versions
outside 12/13, and Ubuntu releases older than 24.04 fail before repository or
package changes. Ubuntu 24.04+ uses its own release codename, not a fixed Noble
repository; only 24.04/Noble was verified here. An unknown or unpublished release
fails when downloading its release-specific key, before repository setup, rather
than falling back to Debian Bookworm or another Ubuntu suite.

Arch/CachyOS still installs the official `tailscale` package through pacman,
without an APT repository. OpenWrt uses the separate `openwrt_tailscale` role;
its installation path is unchanged. Authentication and authorized-node settings
reconciliation are unchanged on all supported hosts.

## Initial GitOps setup (manual, once)

1. Export the current policy from the [Access controls console](https://console.tailscale.com/admin/acls) and keep it outside the repo for emergency recovery. Before enabling automatic apply, preserve any required unrelated `ssh`, `autoApprovers`, or `nodeAttrs` settings in the repository policy. Remove old broad `acls`/`grants` that would also allow the edge; do not combine this policy with an allow-all rule.
2. Configure separate Tailscale test/apply clients with GitHub OIDC federation and the permissions needed by the [GitOps action](https://github.com/tailscale/gitops-acl-action). Set repository Actions variables `TS_TAILNET`, `TS_TEST_CLIENT_ID`, `TS_TEST_AUDIENCE`, `TS_APPLY_CLIENT_ID`, and `TS_APPLY_AUDIENCE` to match those clients and their trust configuration.
3. If `tag:homeassistant` is not yet available, add `"tag:homeassistant": []` to the **current** policy's `tagOwners` in the console, retaining its other settings. In [Machines](https://console.tailscale.com/admin/machines), assign it to `ha-krm`. Tagging replaces its user identity; check existing user-specific rules first. Check the other machine tags against the table above.

## Normal policy changes

For this solo-maintainer repository, the PR is a pre-apply checkpoint;
self-review is sufficient for your own changes. Keep this branch/PR path even
when working alone: pushing policy changes to `main` triggers a live apply.

1. Edit [files/tailscale/policy.json](../files/tailscale/policy.json) on a branch in this repository and open a PR targeting `main`. The workflow rejects fork PRs.
2. Require the **Validate policy** job and included policy tests to pass before merging. This is an operator requirement; the workflow file does not itself configure branch protection.
3. Merge the PR, then check the **Apply policy** job. Pushes to `main` apply when the policy or workflow changes. Manual dispatch on `main` also applies, but does not run the PR validation job.
4. Verify from the edge that backend 4743, SSH 22, SMB 445, and Unraid management 18080/18443 are unreachable, while proxy/game traffic and trusted-device SSH/direct access still work. Keep the HTTPS `/admin` restriction in Caddy: tailnet policy cannot filter HTTP paths.

## Rollback

For the edge identity migration, follow the
[identity rollback](edge.md#identity-rollback). Before any device can be
retagged to `tag:vps`, **first** restore its declaration and restricted grants
through a validated PR and successful **Apply policy** job. Keep `tag:edge` and
its restricted grants while any device uses it. A machine-name rollback can
retain `tag:edge` independently.

Restore the previous policy in Git through the same validated PR/apply
path. For emergency console recovery, restore the exported policy and reconcile
the repository before another apply; otherwise automation can overwrite the
recovery. If also reverting `ha-krm` to its original user-owned identity,
re-authenticate it as that user; removing its final tag requires re-authentication,
not merely deleting a tag in the console.

Reference: [grants syntax](https://tailscale.com/docs/reference/syntax/grants),
[policy tests](https://tailscale.com/docs/reference/syntax/policy-file#tests),
and [tag identity](https://tailscale.com/docs/features/tags).
Machine-name changes affect [MagicDNS](https://tailscale.com/docs/concepts/machine-names).
