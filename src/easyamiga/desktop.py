"""Create freedesktop ``.desktop`` launchers so games are one click away.

Each launcher runs ``easyamiga run <name>`` which boots Amiberry with the
game's generated config. Launchers are written to the per-user applications
directory so they show up in the desktop's application menu.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_ID_PREFIX = "easyamiga-game-"
APP_DESKTOP_ID = "easyamiga"


def easyamiga_exe() -> str:
    """Best-effort absolute path to the ``easyamiga`` executable.

    Prefers the copy on ``PATH``, then the currently running script, so
    generated launchers work regardless of the desktop session's ``PATH``.
    """
    exe = shutil.which("easyamiga")
    if exe:
        return exe
    argv0 = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if argv0 and argv0.name == "easyamiga" and argv0.exists():
        return str(argv0.resolve())
    return "easyamiga"


def applications_dir() -> Path:
    """Per-user XDG applications directory (respects ``XDG_DATA_HOME``)."""
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "applications"


def desktop_file_path(game_name: str) -> Path:
    slug = _slug(game_name)
    return applications_dir() / f"{APP_ID_PREFIX}{slug}.desktop"


def _slug(name: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in name]
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "game"


def render_desktop_entry(
    game_name: str,
    exec_command: str,
    icon: str,
    comment: str = "Play an Amiga game with easyamiga",
) -> str:
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            f"Name={game_name}",
            f"Comment={comment}",
            f"Exec={exec_command}",
            f"Icon={icon}",
            "Terminal=false",
            "Categories=Game;Emulator;",
            f"Keywords=amiga;amiberry;{_slug(game_name)};",
            "",
        ]
    )


def write_launcher(
    game_name: str,
    exec_command: str,
    icon: str,
) -> Path:
    directory = applications_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = desktop_file_path(game_name)
    target.write_text(
        render_desktop_entry(game_name, exec_command, icon), encoding="utf-8"
    )
    target.chmod(0o755)
    return target


def remove_launcher(game_name: str) -> bool:
    target = desktop_file_path(game_name)
    if target.exists():
        target.unlink()
        return True
    return False


def app_desktop_file_path() -> Path:
    return applications_dir() / f"{APP_DESKTOP_ID}.desktop"


def write_app_launcher(icon: str = "easyamiga") -> Path:
    """Install a launcher for the easyamiga GUI itself into the app menu."""
    directory = applications_dir()
    directory.mkdir(parents=True, exist_ok=True)
    entry = "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Name=easyamiga",
            "Comment=Play Amiga games the easy way",
            f"Exec={easyamiga_exe()} gui",
            f"Icon={icon}",
            "Terminal=false",
            "Categories=Game;Emulator;Utility;",
            "Keywords=amiga;amiberry;emulator;games;",
            "",
        ]
    )
    target = app_desktop_file_path()
    target.write_text(entry, encoding="utf-8")
    target.chmod(0o755)
    return target
