# Workstations (Arch/CachyOS)

[Repository overview](../README.md) · [Getting started](getting-started.md) · [Laptop power](laptop-power.md)

Sources: [playbooks/workstation.yml](../playbooks/workstation.yml), [workstation variables](../inventory/group_vars/workstations/), [host overrides](../inventory/host_vars/), and [inventory](../inventory/hosts.ini).

Run commands from the repository root.

Desktops (`workstations` group) managed by `playbooks/workstation.yml` — same model: declarative lists in `inventory/group_vars/workstations/`, deltas in `inventory/host_vars/`, management over the tailnet. Goal: **identical dev environment**, not identical systems. GUI/desktop/hardware packages are deliberately NOT managed.

| Layer                              | Tool                                        |
| ---------------------------------- | ------------------------------------------- |
| Dev packages                       | Ansible (`arch_packages`, base + dev lists) |
| User config (fish, nvim, git, ...) | chezmoi + git (`dotfiles` role)             |
| Source code (`~/Projects`)         | git + GitHub                                |
| `~/Documents`                      | Syncthing (user service, only this folder)  |
| Large/shared files                 | Unraid directly                             |

Roles: `arch_common` (optional `-Syu` via `-e arch_system_upgrade=true`, timezone/locale, NetworkManager → systemd-resolved fix for MagicDNS), `ssh`, `tailscale` (day-0 `tailscale up` is manual), `keyd` (Caps Lock = Left Ctrl, Left Ctrl = Hyper — every `LCtrl+<key>` emits `C-M-A-S+<key>` for KDE global shortcuts; device exclusion list in `inventory/group_vars/workstations/keyd.yml` — the external keyboard is passed through on any machine), `arch_packages` (AUR via yay: handy-bin + kwtype-git), `docker` (re-login once for the group), `dotfiles` (chezmoi init + update every run; set `dotfiles_chezmoi_repo`), `kde_lock_layout` (US layout on screen lock), `kde_lock_immediate` (password prompt after resume), `laptop_power` (per-host gated battery tuning — [power guide](lap…

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

**fprintd gotcha (little-raven):** `/etc/pam.d/sudo` puts `pam_fprintd.so` first, so a non-interactive `sudo` (Ansible become) waits for a FINGER before it ever prints the password prompt — the run appears stuck at Gathering Facts and dies with "Timed out waiting for become success". When that happens, just touch the fingerprint reader; the become password typed at the start is then not even used.
