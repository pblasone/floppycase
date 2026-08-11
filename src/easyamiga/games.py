"""Register games and wire them up to configs + desktop launchers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from . import desktop
from .config_gen import ConfigOptions, read_meta, write_config
from .models import AmigaModel
from .paths import Paths
from .roms import DetectedRom

ADF_SUFFIXES = {".adf", ".adz", ".ipf"}
WHDLOAD_SUFFIXES = {".lha", ".lzx", ".zip"}


@dataclass
class Game:
    name: str
    kind: str  # "adf" | "whdload"
    stored: Path
    config_path: Path
    desktop_path: Path | None = None
    newly_created: bool = True


def classify(source: Path) -> str:
    if source.is_dir():
        return "whdload"
    suffix = source.suffix.lower()
    if suffix in ADF_SUFFIXES:
        return "adf"
    if suffix in WHDLOAD_SUFFIXES:
        return "whdload"
    # Unknown files are treated as WHDLoad payloads dropped into the games dir.
    return "whdload"


def _store_game(paths: Paths, source: Path) -> Path:
    """Copy the game under the games directory (unless it already lives there)."""
    paths.games.mkdir(parents=True, exist_ok=True)
    try:
        source.relative_to(paths.games)
        return source  # already inside games/
    except ValueError:
        pass
    dest = paths.games / source.name
    if source.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
    else:
        shutil.copy2(source, dest)
    return dest


def _exec_command(config_name: str) -> str:
    return f'{desktop.easyamiga_exe()} run "{config_name}"'


def add_game(
    paths: Paths,
    source: Path,
    model: AmigaModel,
    name: str | None = None,
    rom: DetectedRom | None = None,
    create_launcher: bool = True,
    icon: str = "easyamiga",
    roms_dir: Path | None = None,
) -> Game:
    """Register a game: store it, generate a config, and add a desktop launcher."""
    source = source.expanduser()
    if not source.exists():
        raise FileNotFoundError(f"Game not found: {source}")

    kind = classify(source)
    stored = _store_game(paths, source)
    game_name = name or source.stem

    floppy = stored if kind == "adf" else None
    options = ConfigOptions(
        model=model,
        paths=paths,
        rom=rom,
        floppy=floppy,
        show_gui=False,
        description=f"easyamiga: {game_name} ({model.name})",
        source=stored,
        kind=kind,
        # ADF games boot the floppy directly; no games-HD mount needed.
        mount_games=(kind != "adf"),
        roms_dir=roms_dir,
    )
    config_path = write_config(options, game_name)

    desktop_path = None
    if create_launcher:
        desktop_path = desktop.write_launcher(
            game_name,
            _exec_command(config_path.stem),
            icon,
        )

    return Game(
        name=game_name,
        kind=kind,
        stored=stored,
        config_path=config_path,
        desktop_path=desktop_path,
    )


def list_configs(paths: Paths) -> list[Path]:
    if not paths.configs.exists():
        return []
    return sorted(paths.configs.glob("*.uae"))


def prune_orphans(paths: Paths) -> list[str]:
    """Remove configs + launchers for games whose source file no longer exists.

    Only touches easyamiga game configs (those with a recorded ``source``); bare
    machine configs and anything without game metadata are left alone. Returns
    the names of the games that were pruned.
    """
    removed: list[str] = []
    for cfg in list_configs(paths):
        source = read_meta(cfg).get("source")
        if source and not Path(source).exists():
            try:
                cfg.unlink()
            except OSError:
                continue
            desktop.remove_launcher(cfg.stem)
            removed.append(cfg.stem)
    return removed


def resolve_launch(paths: Paths, config_path: Path) -> tuple[Path | None, str | None]:
    """Work out the actual game file + kind for a config, authoritatively.

    Prefers the config's embedded ``source`` metadata, but falls back to matching
    the config name against files in the games folder (so old configs written
    before launch metadata existed still launch correctly). The kind is always
    re-derived from the real file, so a WHDLoad ``.lha`` always auto-boots even
    if a stale config said otherwise.
    """
    meta = read_meta(config_path)
    source: Path | None = None
    stored = meta.get("source")
    if stored:
        candidate = Path(stored)
        if candidate.exists():
            source = candidate
    if source is None:
        for entry in discover_game_sources(paths):
            if entry.stem == config_path.stem:
                source = entry
                break
    kind = classify(source) if (source and source.exists()) else None
    return source, kind


def discover_game_sources(paths: Paths) -> list[Path]:
    """Top-level entries in the games directory that look like games."""
    if not paths.games.exists():
        return []
    sources: list[Path] = []
    for entry in sorted(paths.games.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            sources.append(entry)
        elif entry.suffix.lower() in (ADF_SUFFIXES | WHDLOAD_SUFFIXES):
            sources.append(entry)
    return sources


def scan_games(
    paths: Paths,
    model: AmigaModel,
    rom: DetectedRom | None = None,
    create_launchers: bool = True,
    overwrite: bool = False,
    roms_dir: Path | None = None,
    prune: bool = True,
) -> list[Game]:
    """Register every game found in the games directory.

    Idempotent: games that already have a config are left as-is (unless
    ``overwrite`` is set) but still returned so callers get the full list.
    Newly registered games have ``newly_created=True``. When ``prune`` is set,
    configs/launchers for deleted games are removed first.
    """
    paths.ensure()
    if prune:
        prune_orphans(paths)
    results: list[Game] = []
    for source in discover_game_sources(paths):
        name = source.stem
        config_path = paths.config_file(name)
        # Regenerate stale configs (missing launch metadata from older versions)
        # so they get the right model and can be launched correctly.
        stale = config_path.exists() and not read_meta(config_path).get("source")
        if config_path.exists() and not overwrite and not stale:
            launcher = desktop.desktop_file_path(name)
            results.append(
                Game(
                    name=name,
                    kind=classify(source),
                    stored=source,
                    config_path=config_path,
                    desktop_path=launcher if launcher.exists() else None,
                    newly_created=False,
                )
            )
            continue
        results.append(
            add_game(
                paths=paths,
                source=source,
                model=model,
                name=name,
                rom=rom,
                create_launcher=create_launchers,
                roms_dir=roms_dir,
            )
        )
    return results
