# Changelog

All notable changes to FloppyCase are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-08-13

### Changed

- Renamed the project from **EasyAmiga** to **FloppyCase** (package, CLI,
  desktop id, default data directory, and docs).
- Default data directory is now `~/FloppyCase` (env: `FLOPPYCASE_HOME`).
- Console scripts are now `floppycase` and `floppycase-gui`.
- Config metadata is written as `; floppycase_*`.

### Added

- Public-beta README sections: status banner, requirements, disclaimer, known
  limitations, troubleshooting, and support.
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
