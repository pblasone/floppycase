# easyamiga

**Plug-and-play Amiga gaming on Linux.**

Getting classic Amiga games running on Linux normally means a "desert walk" of
emulators, Kickstart ROMs, WHDLoad, hard-drive images and cryptic `.uae`
configuration. `easyamiga` collapses that into a few commands: it installs the
[Amiberry](https://github.com/BlitterStudio/amiberry) emulator, sets up a clean
directory structure, auto-configures the right Amiga model for your ROM, and lets
you add favorite games to your desktop app menu when you want them there.

> Goal: go from *nothing* to *playing an Amiga game* with as little friction as
> possible.

## What it does

- **One-command install** – installs Amiberry (via its official apt repo),
  WHDLoad, and the easyamiga desktop icon.
- **Tidy directory layout** – a single `~/EasyAmiga` folder with `roms/`,
  `games/`, `workbench/`, `configs/`, `whdload/` and `downloads/`.
- **Automatic configuration** – detects your Kickstart ROM by CRC32 and writes
  an Amiberry config for the matching model (**A500** or **A1200**) with the
  correct chipset/CPU and the **maximum recommended Fast RAM** (8 MB). If no ROM
  is present it falls back to the built-in **AROS** Kickstart replacement, so you
  can boot an Amiga with zero copyrighted files.
- **Real click-to-play** – WHDLoad games (`.lha`) boot straight into the game
  via Amiberry's WHDLoad Booter (no manual Workbench setup); ADF disk images
  boot the floppy directly. easyamiga makes your Kickstart ROMs visible to the
  booter automatically.
- **Optional app-menu launchers** – tick **Menu** on a game in the GUI (or pass
  `--launcher` on `add-game` / `scan`) to add a freedesktop `.desktop` entry so
  you can launch favorites from your Linux application menu without opening the
  easyamiga window.
- **Friendly desktop app** – `easyamiga gui` opens a scrollable alphabetical list
  of your games; click the play icon (or double-click a row) to launch.
- **Per-game settings & notes** – a cog on each row opens a dialog to set
  controls, window scale, fullscreen and a display filter, plus a free-text
  **notes** field to remember what you worked out for a game. A global
  **Settings** dialog sets the defaults for everything.
- **Playable on a keyboard** – games launch with keyboard-as-joystick by
  default (cursor keys + Space to fire); switch to numpad or a gamepad per game
  or globally.

## Quick start

On Ubuntu/Debian (Python 3.12+), **do not** use system `pip install` — the OS
blocks it (`externally-managed-environment`). Use **pipx** (recommended) or a
**venv** instead.

### Install easyamiga

```bash
# One-time: pipx + Tkinter for the GUI
sudo apt install pipx python3-tk python3-venv
pipx ensurepath
# reopen the terminal if pipx ensurepath tells you to

cd ~/Devel/easyamiga   # your checkout

# Recommended: isolated app install (upgrades with pipx reinstall .)
pipx install .

# Alternative: development venv in the repo
python3 -m venv .venv
source .venv/bin/activate
pip install -U -e ".[dev]"
```

After `pipx install .`, the commands `easyamiga` and `easyamiga-gui` are on your
PATH. To pick up changes after `git pull`:

```bash
cd ~/Devel/easyamiga
pipx reinstall .
```

### Set up Amiberry and play

```bash
# Install Amiberry + WHDLoad and create the folder structure
easyamiga install
easyamiga init

# Drop games into ~/EasyAmiga/games, then open the app
easyamiga gui
```

The GUI scans your `games/` folder on open and lists every game alphabetically.

### Prefer the terminal?

```bash
# Boot an Amiga right now with the free AROS ROM (no Kickstart needed)
easyamiga config --model a500
easyamiga run a500

# Or drop a Kickstart ROM into ~/EasyAmiga/roms first, then:
easyamiga config          # auto-detects the ROM and picks the model

# Scan the games folder and register everything found
easyamiga scan

# Add a single game (use --launcher to add it to your app menu)
easyamiga add-game ~/Downloads/TurricanII --model a500 --name "Turrican II" --launcher
```

## Commands

| Command | What it does |
| --- | --- |
| `easyamiga gui` | Open the desktop app: scan the games folder and click to play. |
| `easyamiga init` | Create the `~/EasyAmiga` directory structure. |
| `easyamiga install` | Install Amiberry, WHDLoad and the app icon. |
| `easyamiga config` | Generate an Amiberry config (auto-detects ROM/model). |
| `easyamiga scan` | Scan the games folder and register every game found. |
| `easyamiga add-game <path>` | Store a game and build its config (`--launcher` adds an app-menu entry). |
| `easyamiga run <name>` | Boot the game (WHDLoad auto-boot for `.lha`, floppy for ADF). |
| `easyamiga sync-roms` | Decode (if needed) and refresh your Kickstarts in Amiberry's ROM folder. |
| `easyamiga clean-configs [name]` | Reset the WHDLoad booter's cached game config(s). |
| `easyamiga list` | List detected ROMs and generated configs. |
| `easyamiga doctor` | Report what is installed / configured / missing. |

The model for new games is auto-detected from your ROM (a KS 3.1 A1200 ROM →
A1200); pass `--model` to override.

Use `--base <dir>` (or the `EASYAMIGA_HOME` env var) to manage a setup somewhere
other than `~/EasyAmiga`.

## Tuning games (controls, display, notes)

Click the cog on a game row (or set global defaults from the toolbar
**Settings** button) to adjust:

- **Controls** – keyboard layouts matching Amiberry (arrows + Space, arrows +
  Left Ctrl, WASD, numpad, or gamepad). CD32 pad mode can be forced on/off when
  auto-detection is wrong.
- **Display** – fullscreen, window scale, CRT filter, horizontal/vertical
  centering (`none` / `simple` / `smart`), and pixel offsets when the picture
  looks misaligned in the viewport.
- **Input** – block duplicate keypresses (Amiberry's keyboard-as-joystick option).
- **Notes** – free text saved per game.

WHDLoad games pick CPU, chipset and RAM from the WHDLoad database at boot; you do
not need to choose A500 vs A1200 manually. Scan/add still writes a local config
for metadata, using the best Kickstart ROM you have installed.

These are stored in `~/EasyAmiga/library.json` and applied at launch as Amiberry
``-s key=value`` options. A game's settings override the global defaults; leave
a field on `default` to inherit or let the WHDLoad booter decide.

## How model auto-configuration works

`easyamiga` mirrors Amiberry's own behaviour: it hashes every file in `roms/`
with CRC32 and matches it against a database of well-known Kickstart images to
pick the best model.

| Model | Chipset | CPU | Chip RAM | Fast RAM |
| --- | --- | --- | --- | --- |
| Amiga 500 | OCS | 68000 | 512 KB | 8 MB |
| Amiga 1200 | AGA | 68020 | 2 MB | 8 MB |

If no ROM is found, the built-in **AROS** ROM is used automatically.

## ROMs, WHDLoad and the law

Original **Kickstart ROMs and Workbench are copyrighted** and are *not*
distributed with easyamiga. The legal way to obtain them is
[Amiga Forever](https://www.amigaforever.com/).

Once Amiberry is installed, easyamiga uses **Amiberry's own ROM folder**
(`~/Amiberry/ROMs/`) as the single source of truth — drop your ROMs there (any
ROMs found in the legacy `~/EasyAmiga/roms/` are migrated across automatically).
`easyamiga doctor` prints the exact folder it's using.

For a fully free setup, easyamiga uses the open-source
[AROS](https://aros.org/) Kickstart replacement that ships with Amiberry.

### Amiga Forever (encrypted) ROMs

Amiga Forever often ships ROMs in Cloanto's *encoded* form (an `AMIROMTYPE1`
header, scrambled with `rom.key`). Emulators can't boot these directly — they
show up as an unknown ROM and the CPU crashes on start. If you have the
`rom.key` file, **copy it into the ROM folder alongside the ROMs** and easyamiga
decodes them automatically into an `easyamiga-decoded/` subfolder that Amiberry
also scans. If you don't have a `rom.key`, run Amiga Forever once (its newer
versions decrypt the ROMs on first launch) and copy the resulting `.rom` files
instead. `easyamiga doctor` flags encrypted ROMs and tells you exactly what to do.

If a game got a bad auto-config before your ROMs were set up (e.g. stuck at
68000), reset it with `easyamiga clean-configs <name>` — or launch it again,
since easyamiga clears the WHDLoad booter's cached config on each launch so it
regenerates against your current ROMs.

### How games are launched

- **WHDLoad `.lha` games** boot via Amiberry's WHDLoad Booter (`amiberry
  --autoload game.lha`). Amiberry builds a temporary hard drive, installs the
  game and starts it — no Workbench setup needed. This needs a **Kickstart 3.1
  (A1200)** ROM (and ideally 1.3) available to Amiberry; easyamiga symlinks the
  ROMs from `~/EasyAmiga/roms/` into Amiberry's ROM path for you. Use RetroPlay
  `.lha` packs (one top-level folder containing the `.slave`) for best results.
- **ADF disk images** boot the floppy directly using a generated config with
  the auto-detected model and your Kickstart.

Run `easyamiga doctor` to confirm the WHDLoad Booter is ready and that a
suitable Kickstart is visible to Amiberry.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

## License

GPL-3.0-or-later. Amiberry and WHDLoad are the property of their respective
authors and are installed from their official distributions.
