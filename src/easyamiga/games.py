"""Register games and wire them up to configs + desktop launchers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from . import desktop
from .config_gen import ConfigOptions, write_config
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
    # Prefer an absolute path so the launcher works regardless of the desktop
    # session's PATH: the easyamiga on PATH, else the running script, else bare.
    import sys

    exe = shutil.which("easyamiga")
    if not exe:
        argv0 = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
        if argv0 and argv0.name == "easyamiga" and argv0.exists():
            exe = str(argv0.resolve())
    exe = exe or "easyamiga"
    return f'{exe} run "{config_name}"'


def add_game(
    paths: Paths,
    source: Path,
    model: AmigaModel,
    name: str | None = None,
    rom: DetectedRom | None = None,
    create_launcher: bool = True,
    icon: str = "easyamiga",
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
