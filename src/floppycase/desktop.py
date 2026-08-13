"""Create freedesktop ``.desktop`` launchers so games are one click away.

Each launcher runs ``floppycase run <name>`` which boots Amiberry with the
game's generated config. Launchers are written to the per-user applications
directory so they show up in the desktop's application menu.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_ID_PREFIX = "floppycase-game-"
APP_DESKTOP_ID = "floppycase"
ICON_NAME = "floppycase"


def floppycase_exe() -> str:
    """Best-effort absolute path to the ``floppycase`` executable.

    Prefers the copy on ``PATH``, then the currently running script, so
    generated launchers work regardless of the desktop session's ``PATH``.
    """
    exe = shutil.which("floppycase")
    if exe:
        return exe
    argv0 = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if argv0 and argv0.name == "floppycase" and argv0.exists():
        return str(argv0.resolve())
    return "floppycase"


def applications_dir() -> Path:
    """Per-user XDG applications directory (respects ``XDG_DATA_HOME``)."""
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "applications"


def icons_home() -> Path:
    """Per-user hicolor icon theme root."""
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return base / "icons" / "hicolor"


def installed_icon_path() -> Path | None:
    """Absolute path to the best installed FloppyCase app icon, if present."""
    base = icons_home()
    candidates = [
        base / "128x128" / "apps" / f"{ICON_NAME}.png",
        base / "64x64" / "apps" / f"{ICON_NAME}.png",
        base / "48x48" / "apps" / f"{ICON_NAME}.png",
        base / "scalable" / "apps" / f"{ICON_NAME}.svg",
        base / "256x256" / "apps" / f"{ICON_NAME}.png",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def icon_for_desktop() -> str:
    """Icon value for ``.desktop`` files.

    Prefer an absolute path (reliable on Cinnamon/Mint). Fall back to the
    theme icon name when icons have not been installed yet.
    """
    path = installed_icon_path()
    return str(path) if path else ICON_NAME


def desktop_file_path(slug: str) -> Path:
    """Path to a game's ``.desktop`` file (``slug`` is the config stem)."""
    return applications_dir() / f"{APP_ID_PREFIX}{_slug(slug)}.desktop"


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
    comment: str = "Play an Amiga game with FloppyCase",
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
    display_name: str,
    exec_command: str,
    icon: str | None = None,
    *,
    slug: str | None = None,
) -> Path:
    """Write a per-game launcher. ``slug`` is the config stem (defaults to ``display_name``)."""
    directory = applications_dir()
    directory.mkdir(parents=True, exist_ok=True)
    file_slug = slug or display_name
    target = desktop_file_path(file_slug)
    target.write_text(
        render_desktop_entry(display_name, exec_command, icon or icon_for_desktop()),
        encoding="utf-8",
    )
    target.chmod(0o755)
    return target


def remove_launcher(slug: str) -> bool:
    target = desktop_file_path(slug)
    if target.exists():
        target.unlink()
        return True
    return False


def app_desktop_file_path() -> Path:
    return applications_dir() / f"{APP_DESKTOP_ID}.desktop"


def write_app_launcher(icon: str | None = None) -> Path:
    """Install a launcher for the FloppyCase GUI itself into the app menu."""
    directory = applications_dir()
    directory.mkdir(parents=True, exist_ok=True)
    entry = "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Name=FloppyCase",
            "Comment=Play Amiga games the easy way",
            f"Exec={floppycase_exe()} gui",
            f"Icon={icon or icon_for_desktop()}",
            "Terminal=false",
            "Categories=Game;Emulator;Utility;",
            "Keywords=amiga;amiberry;emulator;games;floppycase;",
            "",
        ]
    )
    target = app_desktop_file_path()
    target.write_text(entry, encoding="utf-8")
    target.chmod(0o755)
    return target
