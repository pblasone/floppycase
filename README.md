# FloppyCase

> **Public beta.** FloppyCase works for day-to-day play, but APIs, paths, and
> UX may still change. Please file issues when something breaks.

**Plug-and-play Amiga gaming on Linux.**

Getting classic Amiga games running on Linux normally means a "desert walk" of
emulators, Kickstart ROMs, WHDLoad, hard-drive images and cryptic `.uae`
configuration. `floppycase` collapses that into a few commands: it installs the
[Amiberry](https://github.com/BlitterStudio/amiberry) emulator, sets up a clean
directory structure, auto-configures the right Amiga model for your ROM, and lets
you add favorite games to your desktop app menu when you want them there.

> Goal: go from *nothing* to *playing an Amiga game* with as little friction as
> possible.

## Requirements

- Linux desktop (developed and tested on **Ubuntu/Debian**)
- **Python 3.10+**
- `pipx` (recommended) or a virtualenv — system `pip install` is blocked on
  modern Debian/Ubuntu (`externally-managed-environment`)
- `python3-tk` for the GUI
- Network access on first `floppycase install` (Amiberry apt repo + WHDLoad)

## What it does

- **One-command install** – installs Amiberry (via its official apt repo),
  WHDLoad, and the FloppyCase desktop icon.
- **Tidy directory layout** – a single `~/FloppyCase` folder with `roms/`,
  `games/`, `workbench/`, `configs/`, `whdload/` and `downloads/`.
- **Automatic configuration** – detects your Kickstart ROM by CRC32 and writes
  an Amiberry config for the matching model (**A500** or **A1200**) with the
  correct chipset/CPU and the **maximum recommended Fast RAM** (8 MB). If no ROM
  is present it falls back to the built-in **AROS** Kickstart replacement, so you
  can boot an Amiga with zero copyrighted files.
- **Real click-to-play** – WHDLoad games (`.lha`) boot straight into the game
  via Amiberry's WHDLoad Booter (no manual Workbench setup); ADF disk images
  boot the floppy directly. FloppyCase makes your Kickstart ROMs visible to the
  booter automatically.
- **Optional app-menu launchers** – tick **Menu** on a game in the GUI (or pass
  `--launcher` on `add-game` / `scan`) to add a freedesktop `.desktop` entry so
  you can launch favorites from your Linux application menu without opening the
  FloppyCase window.
- **Friendly desktop app** – `floppycase gui` opens a scrollable alphabetical list
  of your games; click the play icon (or double-click a row) to launch.
- **Per-game settings & notes** – a cog on each row opens a dialog to set
  controls, window scale, fullscreen and a display filter, plus a free-text
  **notes** field to remember what you worked out for a game. A global
  **Settings** dialog sets the defaults for everything.
- **Playable on a keyboard** – games launch with keyboard-as-joystick by
  default (cursor keys + Space to fire); switch to numpad or a gamepad per game
  or globally.

## Quick start

### Install FloppyCase

```bash
# One-time: pipx + Tkinter for the GUI
sudo apt install pipx python3-tk python3-venv
pipx ensurepath
# reopen the terminal if pipx ensurepath tells you to

cd ~/Devel/floppycase   # your checkout

# Recommended: isolated app install (upgrades with pipx reinstall .)
pipx install .

# Alternative: development venv in the repo
python3 -m venv .venv
source .venv/bin/activate
pip install -U -e ".[dev]"
```

After `pipx install .`, the commands `floppycase` and `floppycase-gui` are on your
PATH. To pick up changes after `git pull`:

```bash
cd ~/Devel/floppycase
pipx reinstall .
```

### Set up Amiberry and play

```bash
# Install Amiberry + WHDLoad and create the folder structure
floppycase install
floppycase init

# Drop games into ~/FloppyCase/games, then open the app
floppycase gui
```

The GUI scans your `games/` folder on open and lists every game alphabetically.

### Prefer the terminal?

```bash
# Boot an Amiga right now with the free AROS ROM (no Kickstart needed)
floppycase config --model a500
floppycase run a500

# Or drop a Kickstart ROM into ~/FloppyCase/roms first, then:
floppycase config          # auto-detects the ROM and picks the model

# Scan the games folder and register everything found
floppycase scan

# Add a single game (use --launcher to add it to your app menu)
floppycase add-game ~/Downloads/TurricanII --model a500 --name "Turrican II" --launcher
```

## Commands

| Command | What it does |
| --- | --- |
| `floppycase gui` | Open the desktop app: scan the games folder and click to play. |
| `floppycase init` | Create the `~/FloppyCase` directory structure. |
| `floppycase install` | Install Amiberry, WHDLoad and the app icon. |
| `floppycase config` | Generate an Amiberry config (auto-detects ROM/model). |
| `floppycase scan` | Scan the games folder and register every game found. |
| `floppycase add-game <path>` | Store a game and build its config (`--launcher` adds an app-menu entry). |
| `floppycase run <name>` | Boot the game (WHDLoad auto-boot for `.lha`, floppy for ADF). |
| `floppycase sync-roms` | Decode (if needed) and refresh your Kickstarts in Amiberry's ROM folder. |
| `floppycase clean-configs [name]` | Reset the WHDLoad booter's cached game config(s). |
| `floppycase list` | List detected ROMs and generated configs. |
| `floppycase doctor` | Report what is installed / configured / missing. |

The model for new games is auto-detected from your ROM (a KS 3.1 A1200 ROM →
A1200); pass `--model` to override.

Use `--base <dir>` (or the `FLOPPYCASE_HOME` env var) to manage a setup somewhere
other than `~/FloppyCase`.

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

These are stored in `~/FloppyCase/library.json` and applied at launch as Amiberry
``-s key=value`` options. A game's settings override the global defaults; leave
a field on `default` to inherit or let the WHDLoad booter decide.

## How model auto-configuration works

`floppycase` mirrors Amiberry's own behaviour: it hashes every file in `roms/`
with CRC32 and matches it against a database of well-known Kickstart images to
pick the best model.

| Model | Chipset | CPU | Chip RAM | Fast RAM |
| --- | --- | --- | --- | --- |
| Amiga 500 | OCS | 68000 | 512 KB | 8 MB |
| Amiga 1200 | AGA | 68020 | 2 MB | 8 MB |

If no ROM is found, the built-in **AROS** ROM is used automatically.

## ROMs, WHDLoad and the law

Original **Kickstart ROMs and Workbench are copyrighted** and are *not*
distributed with FloppyCase. The legal way to obtain them is
[Amiga Forever](https://www.amigaforever.com/).

Once Amiberry is installed, FloppyCase uses **Amiberry's own ROM folder**
(`~/Amiberry/ROMs/`) as the single source of truth — drop your ROMs there (any
ROMs found in the local `~/FloppyCase/roms/` are migrated across automatically).
`floppycase doctor` prints the exact folder it's using.

For a fully free setup, FloppyCase uses the open-source
[AROS](https://aros.org/) Kickstart replacement that ships with Amiberry.

### Amiga Forever (encrypted) ROMs

Amiga Forever often ships ROMs in Cloanto's *encoded* form (an `AMIROMTYPE1`
header, scrambled with `rom.key`). Emulators can't boot these directly — they
show up as an unknown ROM and the CPU crashes on start. If you have the
`rom.key` file, **copy it into the ROM folder alongside the ROMs** and FloppyCase
decodes them automatically into a `floppycase-decoded/` subfolder that Amiberry
also scans. If you don't have a `rom.key`, run Amiga Forever once (its newer
versions decrypt the ROMs on first launch) and copy the resulting `.rom` files
instead. `floppycase doctor` flags encrypted ROMs and tells you exactly what to do.

If a game got a bad auto-config before your ROMs were set up (e.g. stuck at
68000), reset it with `floppycase clean-configs <name>` — or launch it again,
since FloppyCase clears the WHDLoad booter's cached config on each launch so it
regenerates against your current ROMs.

### How games are launched

- **WHDLoad `.lha` games** boot via Amiberry's WHDLoad Booter (`amiberry
  --autoload game.lha`). Amiberry builds a temporary hard drive, installs the
  game and starts it — no Workbench setup needed. This needs a **Kickstart 3.1
  (A1200)** ROM (and ideally 1.3) available to Amiberry; FloppyCase makes your
  ROMs visible to Amiberry's ROM path for you. Use RetroPlay `.lha` packs (one
  top-level folder containing the `.slave`) for best results.
- **ADF disk images** boot the floppy directly using a generated config with
  the auto-detected model and your Kickstart.

Run `floppycase doctor` to confirm the WHDLoad Booter is ready and that a
suitable Kickstart is visible to Amiberry.

## Known limitations

- **Linux only** for now (desktop integration targets freedesktop / apt).
- WHDLoad auto-boot works best with a **Kickstart 3.1 (A1200)** ROM available
  to Amiberry; without it, many `.lha` packs will not start cleanly.
- Game compatibility ultimately depends on Amiberry / WHDLoad, not FloppyCase.
- This is a **beta**: expect rough edges, and please report them.

## Troubleshooting

Start with:

```bash
floppycase doctor
```

It reports whether Amiberry, WHDLoad, Kickstart ROMs, and the directory layout
look healthy, and prints the ROM folder FloppyCase is using.

Common fixes:

- GUI missing / Tk errors → `sudo apt install python3-tk`, then `pipx reinstall .`
- Encrypted Amiga Forever ROMs → copy `rom.key` next to the ROMs, then
  `floppycase sync-roms`
- Stale WHDLoad boot settings → `floppycase clean-configs <game>`
- Wrong data directory → set `FLOPPYCASE_HOME` or pass `--base`

## Disclaimer

FloppyCase is provided **as is**, without warranty of any kind. You are
responsible for ensuring you have the legal right to use any Kickstart ROMs,
Workbench files, and game images you add. FloppyCase does **not** distribute
copyrighted Amiga system software or commercial games.

Amiberry and WHDLoad are third-party projects with their own licenses and
terms. "Amiga" is a trademark of its respective owner; FloppyCase is an
independent project and is not affiliated with or endorsed by the trademark
holder.

## Support

- File bugs and feature requests in
  [GitHub Issues](https://github.com/pblasone/easyamiga/issues).
- Include `floppycase doctor` output (and your distro / Python version) when
  reporting install or launch problems.
- Security reports: see [SECURITY.md](SECURITY.md).
- Contributions: see [CONTRIBUTING.md](CONTRIBUTING.md).

## Migrating from EasyAmiga

This project was previously called **EasyAmiga**. FloppyCase still works with
an existing `~/EasyAmiga` tree and the old `EASYAMIGA_HOME` environment
variable. New installs default to `~/FloppyCase` / `FLOPPYCASE_HOME`. After
reinstalling (`pipx reinstall .`), update any personal scripts that called
`easyamiga`.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

## License

[GPL-3.0-or-later](LICENSE). Amiberry and WHDLoad are the property of their
respective authors and are installed from their official distributions.
