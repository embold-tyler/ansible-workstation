# ansible-workstation

Provisions this workstation (Gigabyte AERO 17 KC, Fedora Workstation 44, GNOME,
dual-booting Windows). Fedora is the tested path; Ubuntu branches are kept from
the original playbook but are **untested** — package names there have not been
verified against live repos the way the Fedora ones have.

## Run

```bash
ansible-galaxy install -r requirements.yml
ansible-playbook playbook.yml --ask-become-pass
```

Useful tags: `repos`, `base`, `hardware`, `apps`, `dev`, `dotfiles`, `upgrade`.

```bash
# skip the full system upgrade on a re-run
ansible-playbook playbook.yml --ask-become-pass --skip-tags upgrade
```

## Why the previous run died

The first run aborted in the `common` role and never reached the later roles.
Causes, all now fixed:

| Old value                                            | Problem                                  | Now                                                               |
| ---------------------------------------------------- | ---------------------------------------- | ----------------------------------------------------------------- |
| `neofetch`                                           | retired upstream, absent from F44        | `fastfetch`                                                       |
| `pandoc`                                             | renamed                                  | `pandoc-cli`                                                      |
| `p7zip`, `p7zip-plugins`                             | renamed                                  | `7zip`                                                            |
| `util-linux-user`                                    | merged upstream                          | `util-linux` (provides `chsh`)                                    |
| `vim`                                                | metapackage does not exist               | `vim-enhanced`                                                    |
| `wget`                                               | replaced by wget2                        | `wget2-wget`                                                      |
| `nodejs`                                             | F44 ships only `nodejs22`/`nodejs24`     | managed by `fnm`                                                  |
| copr `atim/vicinae`                                  | HTTP 404                                 | dropped                                                           |
| copr `espanso/espanso`                               | HTTP 404                                 | dropped (upstream copr is `eclipseo/espanso`, not currently used) |
| copr `elxreno/coolercontrol`                         | HTTP 404                                 | `codifryed/CoolerControl`                                         |
| `stdout_callback = yaml`                             | removed in community.general 12          | `result_format = yaml`                                            |
| PWA template ran `flatpak run com.google.Chrome`     | Chrome is an RPM at `/opt/google/chrome` | `google-chrome-stable --app=`                                     |
| `dotfiles` role wrote a stub `~/.zshrc`              | shadows the real chezmoi dotfiles        | `chezmoi init` from the dotfiles repo                             |
| flatpak `io.balena.etcher`                           | ID does not exist on Flathub             | vendor RPM from the balena GitHub release                         |
| flatpak `uk.co.screamingfrog.ScreamingFrogSEOSpider` | ID does not exist on Flathub             | vendor RPM, version pinned in `group_vars`                        |

Every Fedora package name in `group_vars/all.yml` was checked against the live
F44 repos, and every COPR against the Copr API, before being committed here.

## Fingerprint reader

`roles/hardware` installs a udev rule that keeps the ELAN `04f3:0c11` sensor out
of USB autosuspend. Without it, enrollment fails with _"Failed to enroll new
fingerprint"_ / `fprintd: transfer timed out`, because usbcore suspends the
sensor after 2s and the next libfprint transfer never completes.

After the run, enroll as your normal user (**not** with sudo):

```bash
fprintd-enroll
fprintd-list "$USER"
```

## Packaging policy

Prefer a vendor RPM over a flatpak wherever one exists to avoid permissions
issues from sandboxed flatpaks.

## Terminal

WezTerm is installed from the `wezfurlong/wezterm-nightly` COPR (the official
repo maintained by the WezTerm author, tracking `main` — see `roles/repos`),
and the desktop role:

- writes `~/.config/xdg-terminals.list` to resolve "Open in Terminal" / open-in-console
- sets the legacy `org.gnome.desktop.default-applications.terminal` key
- points nautilus-open-any-terminal at `wezterm start --cwd %s`
- registers a `wezterm-ssh.desktop` as the `x-scheme-handler/ssh` handler, so
  ssh:// links clicked in a browser open in WezTerm (`wezterm ssh` accepts
  `[user@]host[:port]` directly, so the handler script just strips the `ssh://`
  scheme and hands the rest over)

WezTerm's own `wezterm.lua` (Catppuccin Frappe, FiraCode Nerd Font Mono) is
chezmoi-managed in the dotfiles repo, not templated here.

### Stray characters when pasting, and dead Home/End

Both were the shell, not the terminal. In `dot_zshrc`:

- `unset zle_bracketed_paste` meant that when a TUI exited without clearing
  bracketed-paste mode, zle stopped stripping the `200~`/`201~` markers the
  terminal was still sending, so they landed in the buffer. Removed — zsh
  re-asserts the correct mode each prompt and always strips them.
- zsh binds neither Home nor End by default, and terminals disagree on CSI
  (`^[[H`) vs SS3 (`^[OH`). Both forms are now bound, plus Delete,
  Ctrl-Delete, Ctrl-Backspace and Ctrl-Left/Right.

## Keyboard shortcuts

| Shortcut                        | Action                             |
| ------------------------------- | ---------------------------------- |
| `Alt+Tab` / `Shift+Alt+Tab`     | switch **windows**                 |
| `Super+Tab` / `Shift+Super+Tab` | switch **applications**            |
| `Super+grave`                   | cycle windows of the current app   |
| `Super+Space`                   | Vicinae launcher                   |
| `Super+V`                       | Vicinae clipboard history          |
| `Super+.`                       | Emoji Copy, inserted at the cursor |
| `Super+Shift+D`                 | toggle light/dark                  |
| `Super+Shift+C`                 | colour picker (gcolor3)            |
| `Super+Shift+O`                 | screenshot-region OCR to clipboard |
| `Super+Shift+K`                 | Caffeine (inhibit sleep)           |
| `Shift+Alt+Space`               | espanso search bar                 |

Four bindings were already taken and are reassigned first, in
`gnome_keybinding_conflicts` — assigning over a live binding leaves neither
working:

- `Super+V` was `toggle-message-tray` → now `Super+M` only
- `Super+Tab` was `switch-group` → moved to `Super+grave`
- `Super+.` was ibus's emoji picker → cleared, handed to Emoji Copy
- `Super+Space` was `switch-input-source` → cleared (one `us` layout here)

## GNOME extensions

Installed from extensions.gnome.org into `~/.local/share/gnome-shell/extensions`
so there is a single location and update path. Fedora _does_ package Caffeine,
but the RPM installs system-wide and would duplicate a user copy.

Extension gsettings schemas are **not** on the default gsettings path, so every
`gsettings` call for one needs `--schemadir`. Without it the command exits 0 and
changes nothing.

`version_tag` values in `gnome_extensions_ego` pin the GNOME 50 build and must be
bumped by hand on a Shell upgrade.

EGO's `/download-extension` endpoint returns 500 from time to time while the
rest of the site stays up, so the role stats each extension first, only fetches
what is missing, retries, and fails only if something is _still_ absent
afterwards. A download failure for an already-installed extension is not an
error. Note the download uses `ignore_errors` rather than `failed_when: false`:
the latter rewrites `failed` to `false` on the result, so a failed download
would pass the filter and the install step would run against a zip that was
never written.

Extensions are enabled by writing `org.gnome.shell enabled-extensions` directly
rather than calling `gnome-extensions enable`, which fails with "does not exist"
for anything the running Shell has not rescanned — always the case for an
extension installed in the same run. Emoji Selector (1162) is not included — it
supports GNOME 43 at most.

## Launcher

**Clipboard history needs the `vicinae@dagimg-dot` Shell extension.** GNOME's
Mutter implements no clipboard-monitoring Wayland protocol — it has neither
`zwlr_data_control_manager_v1` nor `ext_data_control_manager_v1` — so Vicinae
cannot watch the clipboard on its own. Without the extension it silently falls
back to a dummy clipboard server and the UI reads "Clipboard monitoring
unavailable". The extension is in `gnome_extensions_ego`.

Vicinae ships a tarball and an AppImage. **The tarball cannot run on Fedora 44**:
it is linked against glibc 2.44 (Fedora 44 has 2.43) plus Qt private API, and
needs `libqalculate.so.23`, `libLayerShellQtInterface.so.6` and
`libKF6SyntaxHighlighting.so.6`. The AppImage bundles all of that and works, so
that is what the playbook installs.

### Extensions (manual — no CLI install exists yet)

Vicinae has no `vicinae extension install` command (open feature request:
[vicinaehq/vicinae#1884](https://github.com/vicinaehq/vicinae/issues/1884)), so
this can't be scripted here. Installing is still one click each from Vicinae's
built-in Raycast store — this is just the checklist, carried over from the
Windows Raycast setup, with Windows-only extensions dropped and duplicates
resolved:

- [ ] unicode-symbols · gmail · diff-checker · gif-search · random · docker ·
      tailwindcss · github · web-converter · visual-studio-code ·
      google-tasks · regex-tester · font-awesome · search-mdn ·
      unix-timestamp · tw-colorpicker · gitmoji · vim-bro · placeholder ·
      base64 · lorem-ipsum · slack · whois · media-converter · cheatsheets ·
      get-favicon · search-npm · ip-geolocation · cloudflare · 1password
- [ ] espanso — a Vicinae-store version exists and is installed; unverified
      whether it actually works yet.

Dropped as Windows-only (no Linux build, or Vicinae's built-in window switcher
already covers it): `wsl-manager`, `windows-terminal`,
`powertoys-tool-runner`, `ports` (admin-rights process killing, Windows
10+ only), `window-walker` (superseded by Vicinae's built-in window switcher).

`runcloud` and `wphaven` are our own extensions (source in the Windows box's
`Code/raycast`), not store installs — `runcloud` was already forked from
macOS to Windows and needs the same treatment for Linux; `wphaven` still
needs porting too.

## Face unlock

`roles/howdy` configures Howdy against the IR camera in a Windows Hello webcam
(Logitech Brio 4K — the original, not MX Brio or Brio 100/300/500, which have no
IR sensor). It probes for an IR camera first and skips everything if none is
attached, so it is safe to run before the hardware arrives.

It also installs `linux-enable-ir-emitter`, because many Hello cameras leave the
IR illuminator off by default — which makes face unlock work in daylight and fail
in the dark.

The SELinux module is not optional: GDM runs as `xdm_t` and cannot `map` a V4L2
device without it, so face unlock would work for `sudo` and fail silently at the
login screen.

## Disk encryption

See [docs/disk-encryption.md](docs/disk-encryption.md) for the in-place
LUKS2 conversion. `roles/luks_tpm` handles TPM2 enrolment afterwards and is a
no-op until the volume is actually encrypted.

## Secrets and SSH

Keys live in 1Password, not `~/.ssh`, so one vault serves Fedora, Windows and
Coder workspaces. The dotfiles role points `ssh` at `~/.1password/agent.sock`
and masks gnome-keyring's competing agent, which otherwise wins `$SSH_AUTH_SOCK`.

`gh` is wrapped by the 1Password shell plugin (`op plugin run -- gh`), so raw
`gh auth status` reports "not logged in" and any _non-interactive_ `gh` call
(scripts, CI, an agent's shell) has no credentials. That is expected, not a
broken setup.

## What is deliberately not automated

- **1Password sign-in** and `op plugin init gh` — interactive.
- **`coder login`** — interactive.
- **Chrome web apps.** Generating `--app=<url>` launchers here produced a
  second, icon-less copy of every app alongside the real Chrome-installed ones,
  and the generated copies could not be uninstalled from the app grid. Install
  them from inside Chrome instead; the playbook only prints a reminder.
- **Dotfiles** are skipped unless SSH auth to GitHub already works; the play
  prints how to re-run just that tag afterwards.
