# Changelog

All notable changes to FloppyCase are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Document a `pipx` git install form that includes the package name
  (`floppycase @ git+…`), which avoids “cannot determine package name” on
  some machines; require `git` in the install prerequisites.

## [0.2.3] - 2026-08-13

### Fixed

- Host hotkeys (**F10** quit, **F11** fullscreen, **Ctrl+Alt** mouse release) were
  ignored because Amiberry only accepts those options with an `amiberry.` prefix
  on the command line.
- `whdload_quit_on_exit` is now applied *before* `--autoload` so WHDLoad's
  startup-sequence actually includes AmiQuit.
- GUI header logo sits on a brand row beside the FloppyCase title again (the
  hotkey tip had pulled it out of alignment).

## [0.2.2] - 2026-08-13

### Added

- Host hotkeys while playing: **F10** quits, **F11** toggles fullscreen, and
  **Ctrl+Alt** releases the mouse (shown in the GUI and window title).
- `whdload_quit_on_exit` so leaving a WHDLoad game closes Amiberry instead of
  dropping you at Workbench/Shell.

## [0.2.1] - 2026-08-13

### Fixed

- Start-menu icon on Linux Mint/Cinnamon: install PNG sizes, refresh the icon
  cache, and write an absolute `Icon=` path into the `.desktop` launcher.
- Fullscreen launch option now sets Amiberry's `gfx_fullscreen_amiga` /
  `gfx_fullscreen_picasso` to `fullwindow` (the previous key was ignored).

### Changed

- Kickstart ROMs are documented/managed as a single folder (Amiberry's ROM
  directory). `~/FloppyCase/roms` is no longer created for new installs; leftover
  files there are still migrated once.

## [0.2.0] - 2026-08-13

### Changed

- Renamed the project from **EasyAmiga** to **FloppyCase** (package, CLI,
  desktop id, default data directory, and docs).
- Default data directory is now `~/FloppyCase` (env: `FLOPPYCASE_HOME`).
- Console scripts are now `floppycase` and `floppycase-gui`.
- Config metadata is written as `; floppycase_*`.
- GUI start-menu opt-in label is now **Add to start menu**; unchecked by
  default (explicit library flag only — leftover `.desktop` files do not count).
- Application icon replaced with the FloppyCase monochrome glyph; added
  `floppycase-tray.svg` for Linux Mint/Ubuntu panels.

### Added

- Public-beta README sections: status banner, requirements, disclaimer, known
  limitations, troubleshooting, and support.
- User-oriented install flow: `pipx install` from GitHub, then a single
  `floppycase install` (creates `~/FloppyCase` — no separate `init` required).
- Full GPL-3.0 license text plus third-party / trademark notes.
- `SECURITY.md` (GitHub private vulnerability reporting), `CONTRIBUTING.md`,
  and this changelog.

### Compatibility

- Still accepts legacy `EASYAMIGA_HOME` and an existing `~/EasyAmiga` directory.
- Still reads legacy `; easyamiga_*` metadata in older `.uae` configs.
- Still ignores legacy `easyamiga-decoded/` ROM folders when scanning.

## [0.1.2] - 2026-08-13

### Added

- Per-game Menu toggle for optional app-menu launchers.

## [0.1.1] - 2026-08-13

### Fixed

- Header logo loading from pipx installs.

## [0.1.0] - 2026-08-13

### Added

- Initial EasyAmiga PoC: install, init, config, scan, add-game, run, GUI,
  ROM detection (including Amiga Forever decode), WHDLoad booter integration.
