"""Locate and launch the Amiberry emulator."""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

#: Places Amiberry may be installed outside of ``$PATH``.
_CANDIDATE_PATHS = [
    "/usr/bin/amiberry",
    "/usr/local/bin/amiberry",
    "/opt/amiberry/amiberry",
    str(Path.home() / "Amiberry" / "amiberry"),
]

#: Game containers that Amiberry's WHDLoad Booter can auto-boot.
WHDLOAD_ARCHIVES = {".lha", ".lzh", ".lzx", ".zip"}
#: Disk/CD images Amiberry can auto-detect and boot directly.
DISK_IMAGES = {".adf", ".adz", ".dms", ".ipf", ".zip", ".cue", ".iso", ".chd"}


def find_amiberry() -> str | None:
    """Return the path to the amiberry executable, or ``None`` if not found."""
    found = shutil.which("amiberry")
    if found:
        return found
    for candidate in _CANDIDATE_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


def is_installed() -> bool:
    return find_amiberry() is not None


@lru_cache(maxsize=1)
def dump_paths() -> dict[str, str]:
    """Return Amiberry's resolved startup paths (from ``amiberry --dump-paths``)."""
    exe = find_amiberry()
    if exe is None:
        return {}
    try:
        proc = subprocess.run(
            [exe, "--dump-paths"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    paths: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            paths[key.strip()] = value.strip()
    return paths


def rom_path() -> Path:
    """Directory Amiberry scans for Kickstart ROMs (its BIOS path)."""
    resolved = dump_paths().get("rom_path")
    if resolved:
        return Path(resolved)
    return Path.home() / "Amiberry" / "ROMs"


def whdboot_path() -> Path:
    resolved = dump_paths().get("whdboot_path")
    if resolved:
        return Path(resolved)
    return Path.home() / ".local" / "share" / "amiberry" / "WHDBoot"


def config_path() -> Path:
    resolved = dump_paths().get("config_path")
    if resolved:
        return Path(resolved)
    return Path.home() / "Amiberry" / "Configurations"


def autoboots_path() -> Path:
    """Where the WHDLoad Booter caches per-game auto-generated configs."""
    return whdboot_path() / "save-data" / "Autoboots"


def game_config_names(source: Path) -> list[str]:
    """Config file names the WHDLoad Booter would derive from a game archive.

    RetroPlay ``.lha`` names map 1:1 to the booter's ``<stem>.uae`` config.
    """
    stem = Path(source).stem
    return [f"{stem}.uae"]


def clear_game_config(source: Path) -> list[Path]:
    """Delete the booter's cached config(s) for a game so it regenerates fresh.

    Prevents a stale (e.g. 68000) auto-config from being reused after the ROM or
    settings change. Returns the paths that were removed.
    """
    removed: list[Path] = []
    dirs = [config_path(), autoboots_path()]
    for name in game_config_names(source):
        for directory in dirs:
            target = directory / name
            try:
                if target.exists():
                    target.unlink()
                    removed.append(target)
            except OSError:
                pass
    return removed


def default_joyports() -> str | None:
    """Default ``-J`` value: port0=mouse, port1=keyboard 'layout D' (cursor keys
    + Left Ctrl/Alt fire), so games are playable on a keyboard out of the box.

    Override with ``EASYAMIGA_JOYPORTS`` (e.g. ``01`` for two real joysticks,
    or ``none``/``off``/empty to leave Amiberry's own port setup untouched).
    """
    value = os.environ.get("EASYAMIGA_JOYPORTS")
    if value is None:
        return "Md"
    value = value.strip()
    if value.lower() in {"", "none", "off"}:
        return None
    return value


def _joyport_args(joyports: str | None) -> list[str]:
    return ["-J", joyports] if joyports else []


def _set_args(options: dict[str, str] | None) -> list[str]:
    args: list[str] = []
    for key, value in (options or {}).items():
        args += ["-s", f"{key}={value}"]
    return args


def build_command(
    config_path: Path,
    amiberry: str | None = None,
    joyports: str | None = None,
    options: dict[str, str] | None = None,
) -> list[str]:
    exe = amiberry or find_amiberry()
    if exe is None:
        raise FileNotFoundError(
            "Amiberry is not installed. Run 'easyamiga install' first."
        )
    return [exe, "--config", str(config_path), *_joyport_args(joyports), *_set_args(options)]


def _exe_or_raise(amiberry: str | None) -> str:
    exe = amiberry or find_amiberry()
    if exe is None:
        raise FileNotFoundError(
            "Amiberry is not installed. Run 'easyamiga install' first."
        )
    return exe


def resolve_game_source(source: Path) -> Path:
    """Resolve the actual file Amiberry should open for a game.

    A WHDLoad *folder* is resolved to a single ``.lha``/``.lzx`` inside it.
    """
    source = Path(source)
    if source.is_dir():
        archives = sorted(source.rglob("*.lha")) or sorted(source.rglob("*.lzx"))
        if archives:
            return archives[0]
        raise FileNotFoundError(
            f"'{source.name}' is a folder with no .lha inside. For click-to-play, "
            "use a WHDLoad .lha pack (e.g. a RetroPlay archive) or an .adf disk image."
        )
    return source


def build_game_command(
    source: Path,
    kind: str | None = None,
    amiberry: str | None = None,
    rescan: bool = True,
    joyports: str | None = None,
    options: dict[str, str] | None = None,
) -> list[str]:
    """Build the Amiberry command to actually boot a game.

    * WHDLoad archives (``.lha`` etc.) use the WHDLoad Booter (``--autoload``).
    * Disk/CD images are passed directly so Amiberry auto-detects and boots them.
    """
    exe = _exe_or_raise(amiberry)
    source = resolve_game_source(source)
    suffix = source.suffix.lower()

    cmd = [exe]
    if rescan:
        cmd.append("--rescan-roms")

    if suffix in WHDLOAD_ARCHIVES and kind != "adf":
        cmd += ["--autoload", str(source)]
    elif suffix in DISK_IMAGES:
        cmd.append(str(source))
    else:
        # Unknown container: let the WHDLoad Booter try it.
        cmd += ["--autoload", str(source)]
    cmd += _joyport_args(joyports)
    cmd += _set_args(options)
    return cmd


def _spawn(cmd: list[str], wait: bool, extra_env: dict[str, str] | None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    if wait:
        return subprocess.run(cmd, env=env, check=False)
    return subprocess.Popen(cmd, env=env)


_JOYPORTS_DEFAULT = object()  # sentinel: use default_joyports()


def _resolve_joyports(joyports):
    return default_joyports() if joyports is _JOYPORTS_DEFAULT else joyports


def launch(
    config_path: Path,
    amiberry: str | None = None,
    wait: bool = True,
    joyports=_JOYPORTS_DEFAULT,
    options: dict[str, str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen | subprocess.CompletedProcess:
    """Launch Amiberry with a generated ``.uae`` config (bare machine / ADF)."""
    cmd = build_command(config_path, amiberry, _resolve_joyports(joyports), options)
    return _spawn(cmd, wait, extra_env)


def launch_game(
    source: Path,
    kind: str | None = None,
    amiberry: str | None = None,
    wait: bool = True,
    rescan: bool = True,
    fresh: bool = True,
    joyports=_JOYPORTS_DEFAULT,
    options: dict[str, str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen | subprocess.CompletedProcess:
    """Boot an actual game (WHDLoad archive or disk image) via Amiberry.

    ``fresh=True`` first removes the WHDLoad Booter's cached config for the game
    so it regenerates against the current ROMs/settings (avoids stale 68000
    configs being reused). ``joyports`` defaults to keyboard-as-joystick so games
    are playable without a controller. ``options`` are passed as ``-s key=value``.
    """
    resolved = resolve_game_source(source)
    if fresh and resolved.suffix.lower() in WHDLOAD_ARCHIVES:
        clear_game_config(resolved)
    cmd = build_game_command(resolved, kind, amiberry, rescan, _resolve_joyports(joyports), options)
    return _spawn(cmd, wait, extra_env)
