# easyamiga

**Plug-and-play Amiga gaming on Linux.**

Getting classic Amiga games running on Linux normally means a "desert walk" of
emulators, Kickstart ROMs, WHDLoad, hard-drive images and cryptic `.uae`
configuration. `easyamiga` collapses that into a few commands: it installs the
[Amiberry](https://github.com/BlitterStudio/amiberry) emulator, sets up a clean
directory structure, auto-configures the right Amiga model for your ROM, and
gives every game a clickable desktop icon.

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
- **WHDLoad-ready games folder** – your host `games/` directory is mounted
  read/write inside the Amiga as `DH0:` / `Games:`, so WHDLoad games dropped
  there appear on the Amiga desktop.
- **Clickable game icons** – `easyamiga add-game` creates a freedesktop
  `.desktop` launcher so a game is one click away from your Linux application
  menu.

## Quick start

```bash
# 1. Install easyamiga (from a checkout)
pipx install .            # or: pip install .

# 2. Install Amiberry + WHDLoad and create the folder structure
easyamiga install
easyamiga init

# 3a. Boot an Amiga right now with the free AROS ROM (no Kickstart needed)
easyamiga config --model a500
easyamiga run a500

# 3b. …or drop a Kickstart ROM into ~/EasyAmiga/roms first, then:
easyamiga config          # auto-detects the ROM and picks the model
easyamiga list            # see detected ROMs, configs

# 4. Add a game and get a desktop icon for it
easyamiga add-game ~/Downloads/TurricanII --model a500 --name "Turrican II"
```

## Commands

| Command | What it does |
| --- | --- |
| `easyamiga init` | Create the `~/EasyAmiga` directory structure. |
| `easyamiga install` | Install Amiberry, WHDLoad and the app icon. |
| `easyamiga config` | Generate an Amiberry config (auto-detects ROM/model). |
| `easyamiga add-game <path>` | Store a game, build its config, add a desktop icon. |
| `easyamiga run <name>` | Launch Amiberry with a generated config. |
| `easyamiga list` | List detected ROMs and generated configs. |
| `easyamiga doctor` | Report what is installed / configured / missing. |

Use `--base <dir>` (or the `EASYAMIGA_HOME` env var) to manage a setup somewhere
other than `~/EasyAmiga`.

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
[Amiga Forever](https://www.amigaforever.com/). Drop your ROM files into
`~/EasyAmiga/roms/` and easyamiga will detect them automatically.

For a fully free setup, easyamiga uses the open-source
[AROS](https://aros.org/) Kickstart replacement that ships with Amiberry.

Fully-automatic WHDLoad *auto-booting* (Amiberry's WHDLoad booter) additionally
requires the specific Kickstart 1.3 and 3.1 ROMs; without them you can still
mount `games/` inside a booted Workbench/AROS and launch WHDLoad manually.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

## License

GPL-3.0-or-later. Amiberry and WHDLoad are the property of their respective
authors and are installed from their official distributions.
