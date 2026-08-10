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


def build_command(config_path: Path, amiberry: str | None = None) -> list[str]:
    exe = amiberry or find_amiberry()
    if exe is None:
        raise FileNotFoundError(
            "Amiberry is not installed. Run 'easyamiga install' first."
        )
    return [exe, "--config", str(config_path)]


def _exe_or_raise(amiberry: str | None) -> str:
    exe = amiberry or find_amiberry()
    if exe is None:
        raise FileNotFoundError(
            "Amiberry is not installed. Run 'easyamiga install' first."
        )
    return exe


def build_game_command(
    source: Path, kind: str | None = None, amiberry: str | None = None, rescan: bool = True
) -> list[str]:
    """Build the Amiberry command to actually boot a game.

    * WHDLoad archives (``.lha`` etc.) use the WHDLoad Booter (``--autoload``).
    * Disk/CD images are passed directly so Amiberry auto-detects and boots them.
    * A WHDLoad *folder* is resolved to a single ``.lha`` inside it if present.
    """
    exe = _exe_or_raise(amiberry)
    source = Path(source)
    suffix = source.suffix.lower()

    if source.is_dir():
        archives = sorted(source.rglob("*.lha")) or sorted(source.rglob("*.lzx"))
        if len(archives) >= 1:
            source, suffix = archives[0], archives[0].suffix.lower()
        else:
            raise FileNotFoundError(
                f"'{source.name}' is a folder with no .lha inside. For click-to-play, "
                "use a WHDLoad .lha pack (e.g. a RetroPlay archive) or an .adf disk image."
            )

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
    return cmd


def _spawn(cmd: list[str], wait: bool, extra_env: dict[str, str] | None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    if wait:
        return subprocess.run(cmd, env=env, check=False)
    return subprocess.Popen(cmd, env=env)


def launch(
    config_path: Path,
    amiberry: str | None = None,
    wait: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen | subprocess.CompletedProcess:
    """Launch Amiberry with a generated ``.uae`` config (bare machine / ADF)."""
    return _spawn(build_command(config_path, amiberry), wait, extra_env)


def launch_game(
    source: Path,
    kind: str | None = None,
    amiberry: str | None = None,
    wait: bool = True,
    rescan: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen | subprocess.CompletedProcess:
    """Boot an actual game (WHDLoad archive or disk image) via Amiberry."""
    return _spawn(build_game_command(source, kind, amiberry, rescan), wait, extra_env)
