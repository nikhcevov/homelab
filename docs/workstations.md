# Workstations (Arch/CachyOS)

[Repository overview](../README.md) · [Getting started](getting-started.md) · [Laptop power](laptop-power.md)

Sources: [playbooks/workstation.yml](../playbooks/workstation.yml), [workstation variables](../inventory/group_vars/workstations/), [host overrides](../inventory/host_vars/), and [inventory](../inventory/hosts.ini).

Run commands from the repository root.

Desktops (`workstations` group) managed by `playbooks/workstation.yml` — same model: declarative lists in `inventory/group_vars/workstations/`, deltas in `inventory/host_vars/`, management over the tailnet. Goal: **identical dev environment**, not identical systems. GUI/desktop/hardware packages are deliberately NOT managed.

Active managed workstations: `starling` and `little-raven` (main operator PC).

| Layer                              | Tool                                        |
| ---------------------------------- | ------------------------------------------- |
| Dev packages                       | Ansible (`arch_packages`, base + dev lists) |
| User config (fish, nvim, git, ...) | chezmoi + git (`dotfiles` role)             |
| Source code (`~/Projects`)         | git + GitHub                                |
| `~/Documents`                      | Syncthing (user service, only this folder)  |
| Large/shared files                 | Unraid directly                             |

Roles: `arch_common` (optional `-Syu` via `-e arch_system_upgrade=true`, timezone/locale, NetworkManager → systemd-resolved fix for MagicDNS), `ssh`, `tailscale` (day-0 `tailscale up` is manual), `keyd` (Caps Lock = Left Ctrl, Left Ctrl = Hyper; device exclusions in [keyd variables](../inventory/group_vars/workstations/keyd.yml), currently empty), `arch_packages` (official packages and AUR via yay; [package lists](../inventory/group_vars/workstations/packages.yml)), `docker` (re-login once for the group), `dotfiles` (sets the fish login shell, then chezmoi init or update; set `dotfiles_chezmoi_repo`), `kde_lock_layout` (US layout on screen lock), `kde_lock_immediate` (password prompt after resume), `laptop_power` (per-host gated battery tuning — [power guide](laptop-power.md)), and `syncthing` (Documents only).

**Hyper (LCtrl) shortcuts.** keyd turns held Left Ctrl into C-M-A-S (Caps Lock in turn acts as plain Left Ctrl), so every `LCtrl+<key>` is a conflict-free combo. The bindings themselves live in KDE (`~/.config/kglobalshortcutsrc`, chezmoi-managed) and in Handy's own settings — this table is the reference, not the source of truth:

| Shortcut       | Action                               | Where bound          |
| -------------- | ------------------------------------ | -------------------- |
| `LCtrl+Space`  | Switch to next keyboard layout       | KDE Layout Switcher  |
| `LCtrl+F`      | Walk through windows (Alt+Tab-style) | KWin                 |
| `LCtrl+G`      | Walk through windows of current app  | KWin                 |
| `LCtrl+Q`      | Close window                         | KWin                 |
| `LCtrl+M`      | Maximize window                      | KWin                 |
| `LCtrl+R`      | KRunner / system search              | KRunner              |
| `LCtrl+V`      | Clipboard history at cursor          | Klipper              |
| `LCtrl+Return` | Terminal (Ghostty)                   | KDE service shortcut |
| `LCtrl+P`      | Screenshot (Spectacle)               | KDE service shortcut |
| `LCtrl+D`      | Dictation (transcribe)               | Handy settings       |

Logic: left-hand home row (`F/G/Q/M`) = window management, `R/V/D` = system tools, `Space/Return` = most frequent actions. KDE defaults (Alt+Tab, Alt+F4, Print, Alt+F2) are kept alongside. Plain Ctrl lives on Caps Lock — nothing is lost, the two keys just swap roles.

**Bootstrap a fresh machine:** install OS + user → `sudo pacman -S git ansible openssh tailscale` → `tailscale up` (disable key expiry) → add to `[workstations]` + optional `inventory/host_vars/<name>.yml` → `ansible-playbook playbooks/workstation.yml --limit <name> --ask-become-pass`. Day-0 on the machine hosting this repo: `ansible-playbook playbooks/workstation.yml -c local --limit starling --ask-become-pass`. Partial runs: `--tags packages|docker|dotfiles|syncthing|tailscale|keyd|layout|lockscreen|power`.

**SSH key access:** `arch_common` adds the public keys listed in `workstation_ssh_keys` (`inventory/group_vars/workstations/common.yml`, filenames under `files/ssh/`) to `workstation_user` (`boss`). The shared list includes `starling.pub` and `little-raven.pub`; existing authorized keys are retained, and no root access is granted. To apply only these keys, run `ansible-playbook playbooks/workstation.yml --tags ssh_keys --ask-become-pass` (optionally `--limit <name>`). This does not run the other common tasks or change SSH daemon or sudo policy.

**fprintd gotcha (little-raven):** `/etc/pam.d/sudo` puts `pam_fprintd.so` first, so a non-interactive `sudo` (Ansible become) waits for a FINGER before it ever prints the password prompt — the run appears stuck at Gathering Facts and dies with "Timed out waiting for become success". When that happens, just touch the fingerprint reader; the become password typed at the start is then not even used.

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
changes. Before deployment, run these commands as the workstation user:

```bash
chezmoi source-path
chezmoi diff
```

Review and capture wanted changes with `chezmoi re-add`, then commit and push the
configured source repository. If editing a separate checkout, pass
`chezmoi --source "$PWD"` from its root; Ansible otherwise updates the source directory
in that machine's chezmoi config. No fixed source directory is imposed by the role.
After applying KDE settings, log out/in so the running session does not overwrite them.

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
