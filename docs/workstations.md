# Workstations (Arch/CachyOS)

[Repository overview](../README.md) · [Getting started](getting-started.md) · [Laptop power](laptop-power.md)

Sources: [playbooks/workstation.yml](../playbooks/workstation.yml), [workstation variables](../inventory/group_vars/workstations/), [host overrides](../inventory/host_vars/), and [inventory](../inventory/hosts.ini).

Run commands from the repository root.

Desktops (`workstations` group) managed by `playbooks/workstation.yml` — same model: declarative lists in `inventory/group_vars/workstations/`, deltas in `inventory/host_vars/`, management over the tailnet. Goal: **identical dev environment**, not identical systems. GUI/desktop/hardware packages are deliberately NOT managed.

Active managed workstations: `starling` (desktop) and `little-raven` (laptop — hosts this repository, management controller).

| Layer                              | Tool                                        |
| ---------------------------------- | ------------------------------------------- |
| Dev packages                       | Ansible (`arch_packages`, base + dev lists) |
| User config (fish, nvim, git, ...) | chezmoi + git (`dotfiles` role)             |
| Source code (`~/Projects`)         | git + GitHub                                |
| `~/Documents`                      | Machine-local; not synced or backed up      |
| Large/shared files                 | Unraid directly                             |

Roles: `arch_common` (optional `-Syu` via `-e arch_system_upgrade=true`, timezone/locale, NetworkManager → systemd-resolved fix for MagicDNS), `ssh`, `tailscale` (day-0 `tailscale up` is manual), `arch_packages` (official packages and AUR via yay; [package lists](../inventory/group_vars/workstations/packages.yml)), `docker` (re-login once for the group), `dotfiles` (sets the fish login shell, then chezmoi init or update; set `dotfiles_chezmoi_repo`), `kde_lock_layout` (US layout on screen lock), `kde_lock_immediate` (password prompt after resume), `laptop_power` (per-host gated battery tuning — [power guide](laptop-power.md)).

**Desktop shortcuts.** No remapping daemon: Caps Lock is a normal Caps Lock and every binding is an ordinary KDE global shortcut. The set is ordered by use — the two most frequent actions get one-hand combos, everything else stays on the stock KDE/default key:

| Shortcut       | Action                         | Where bound           |
| -------------- | ------------------------------ | --------------------- |
| `Meta+Space`   | Switch to next keyboard layout | KDE Layout Switcher   |
| `Meta+V`       | Clipboard history at cursor    | Klipper               |
| `Ctrl+Alt+T`   | Terminal (Ghostty)             | KDE service shortcut  |
| `Ctrl+Alt+D`   | Dictation (Handy transcribe)   | Handy settings        |
| `Alt+Tab`      | Walk through windows           | KWin (default)        |
| `Alt+Backtick` | Walk through app windows       | KWin (default)        |
| `Alt+F4`       | Close window                   | KWin (default)        |
| `Meta+PgUp`    | Maximize window                | KWin (default)        |
| `Print`        | Screenshot (Spectacle)         | KDE service shortcut  |
| `Meta`         | Application launcher           | plasmashell (default) |
| `Alt+F2`       | KRunner (rarely used)          | KRunner (default)     |

Source of truth: chezmoi-managed `~/.config/kglobalshortcutsrc` and Handy's `settings_store.json`; this table is a reference. Rationale: language switch and clipboard history are the hot paths, so they sit on `Meta` + thumb/index (`Space`, `V`) — one hand, no chord of four modifiers. Window management keeps the standard `Alt`/KWin keys, terminal keeps the Linux-standard `Ctrl+Alt+T`. Hyper-only bindings that never got used (KRunner on `Caps+R`, screenshots on `Caps+P`/`Meta+Shift+S`) were dropped: `Print` and the `Meta` launcher already cover them.

**Bootstrap a fresh machine:** install the OS with the login user `boss` (sudo/wheel) → `sudo systemctl enable --now sshd` → `sudo pacman -S openssh python tailscale` → `tailscale up` (disable key expiry; delete the machine's stale tailnet node first, or MagicDNS registers the new install as `<name>-1`) → generate the machine keypair `ssh-keygen -t ed25519 -C boss@<name> -f ~/.ssh/id_ed25519 -N ''`, register its public half on GitHub (the `dotfiles` role clones over `git@github.com:`) and replace `files/ssh/<name>.pub` → authorize the controller's key in `~/.ssh/authorized_keys` (`ssh-copy-id` while the fresh sshd still allows passwords) → add to `[workstations]` + optional `inventory/host_vars/<name>.yml` → `ansible-playbook playbooks/workstation.yml --limit <name> --ask-become-pass` (from an already-managed controller the MagicDNS name resolves immediately; the fresh host resolves tailnet names itself only after `arch_common` rewires NetworkManager to systemd-resolved, so a run started ON that host — a `-c local` day-0 — needs `-e ansible_host=<tailscale-ip>`). Day-0 on the machine hosting this repo (little-raven): `ansible-playbook playbooks/workstation.yml -c local --limit little-raven --ask-become-pass`. Partial runs: `--tags packages|docker|dotfiles|tailscale|layout|lockscreen|power`.

**SSH key access:** `arch_common` adds the public keys listed in `workstation_ssh_keys` (`inventory/group_vars/workstations/common.yml`, filenames under `files/ssh/`) to `workstation_user` (`boss`). The shared list includes `starling.pub` and `little-raven.pub`; existing authorized keys are retained, and no root access is granted. To apply only these keys, run `ansible-playbook playbooks/workstation.yml --tags ssh_keys --ask-become-pass` (optionally `--limit <name>`). This does not run the other common tasks or change SSH daemon or sudo policy. Rotating a workstation key is a file replacement plus a manual purge: these loops are additive, so the previous blob stays authorized on `mon-1`, Unraid (both SSH paths) and the workstations until it is removed by hand.

**fprintd gotcha (little-raven; laptop-only, provisioned by no role):** `/etc/pam.d/sudo` puts `pam_fprintd.so` first, so a non-interactive `sudo` (Ansible become) waits for a FINGER before it ever prints the password prompt — the run appears stuck at Gathering Facts and dies with "Timed out waiting for become success". When that happens, just touch the fingerprint reader; the become password typed at the start is then not even used.

## Synchronize tooling and dotfiles

Ansible installs tooling; the [dotfiles repository](https://github.com/nikhcevov/dotfiles-chezmoi)
owns portable preferences. Keep package declarations in the
[enabled package groups](../inventory/group_vars/workstations/packages.yml), not in
chezmoi install scripts. The full playbook already installs packages before applying
dotfiles. For a focused sync, run both tags together:

```bash
ansible-playbook playbooks/workstation.yml --tags packages,dotfiles --ask-become-pass
```

Use `--limit starling` or `--limit little-raven` to target one machine. A
`--tags dotfiles` run assumes its configured tools, including fish, are already installed.
The role sets fish as the account's login shell with root privileges and supplies
`SHELL=/usr/bin/fish` to chezmoi, so its standalone `chsh` hook does not ask for a
second password during noninteractive apply.

System Node/npm cover Mason's npm-backed tools even when Neovim is launched outside
an interactive fish session. Fisher still owns `nvm.fish`; the tracked `v24` default
selects a locally installed version, not an automatic download. Run `nvm install v24`
in fish if that interactive default is wanted. Existing nvm installations stay local.
The AUR oh-my-pi package is a standalone binary, so it does not require a separate
Bun installation.

### Capture before applying

The dotfiles role uses `--force`: pushed dotfiles overwrite local managed-file
changes. It also runs chezmoi with `--no-tty`, because Ansible can allocate a
pty for the become session — that makes chezmoi's `stdinIsATTY` true and leaves
its interactive prompt (git email) blocked on a terminal nobody is typing into,
with the prompt text hidden inside the task's captured stdout. `--no-tty` takes
the non-interactive branch instead, which uses the personal default email.

Before deployment, run these commands as the workstation user:

```bash
chezmoi source-path
chezmoi diff
```

Review and capture wanted changes with `chezmoi re-add`, then commit and push the
configured source repository. If editing a separate checkout, pass
`chezmoi --source "$PWD"` from its root; Ansible otherwise updates the source directory
in that machine's chezmoi config. No fixed source directory is imposed by the role. After applying KDE settings, log out first, apply while no
Plasma session is running (SSH or a console), then log in: applying with the
session running only survives until that session writes its stale values on
exit, which silently reverts entries (layout list, layout-switch and
window-walk shortcuts).

Handy is managed as a whole settings file, including empty API-key fields; applying it
replaces any local values in those fields. Do not capture provider credentials into
Git. Model downloads remain local: confirm the selected model is available in Handy
on each machine. oh-my-pi credentials, sessions, and caches are not tracked; authenticate
separately on each machine.

### Verify and recover

```bash
chezmoi verify
node --version
npm --version
omp --version
bat --list-themes
getent passwd "$USER"
```

Expected: chezmoi verification succeeds; the tooling is available; bat lists
`tokyonight_moon`; the account's login shell is `/usr/bin/fish`. Chezmoi builds bat's
machine-local cache on first apply and when its tracked config/theme changes.
After a bat upgrade or cache deletion, rebuild it with `bat cache --build`.

To roll back synced preferences or package declarations, revert the relevant Git
commit, push, and rerun the focused sync. Package installation is additive: removing
a package from the declaration does not uninstall it. To undo the fish login shell,
restore the previous shell with `chsh -s /path/to/previous-shell`; later dotfiles-role
runs set fish again unless the role is changed. Git cannot restore local settings or
credentials that were overwritten without a separate backup.
