"""Filesystem layout for an easyamiga installation.

Everything easyamiga manages lives under a single *base* directory so the whole
setup is self-contained and easy to back up or move. The default base is
``~/EasyAmiga`` but it can be overridden (e.g. for tests or multiple setups).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE = Path.home() / "EasyAmiga"

ENV_BASE = "EASYAMIGA_HOME"


def default_base() -> Path:
    """Return the configured base directory.

    Honours the ``EASYAMIGA_HOME`` environment variable so a user (or the test
    suite) can point easyamiga at a different location without extra flags.
    """

    env = os.environ.get(ENV_BASE)
    if env:
        return Path(env).expanduser()
    return DEFAULT_BASE


@dataclass(frozen=True)
class Paths:
    """Resolved directory layout for one easyamiga base."""

    base: Path

    @classmethod
    def resolve(cls, base: Path | str | None = None) -> "Paths":
        if base is None:
            base = default_base()
        return cls(Path(base).expanduser())

    # --- managed sub-directories -------------------------------------------------
    @property
    def roms(self) -> Path:
        """Kickstart ROMs live here; Amiberry scans it recursively."""
        return self.base / "roms"

    @property
    def games(self) -> Path:
        """Drop WHDLoad games / ADFs here. Mounted read/write inside the Amiga."""
        return self.base / "games"

    @property
    def workbench(self) -> Path:
        """Workbench / boot hard-drive content."""
        return self.base / "workbench"

    @property
    def configs(self) -> Path:
        """Generated Amiberry ``.uae`` configuration files."""
        return self.base / "configs"

    @property
    def whdload(self) -> Path:
        """Extracted WHDLoad distribution."""
        return self.base / "whdload"

    @property
    def downloads(self) -> Path:
        """Cache for downloaded archives (WHDLoad, AROS, ...)."""
        return self.base / "downloads"

    def all_dirs(self) -> list[Path]:
        return [
            self.base,
            self.roms,
            self.games,
            self.workbench,
            self.configs,
            self.whdload,
            self.downloads,
        ]

    def ensure(self) -> None:
        """Create every managed directory (idempotent)."""
        for directory in self.all_dirs():
            directory.mkdir(parents=True, exist_ok=True)

    def config_file(self, name: str) -> Path:
        """Path to a named ``.uae`` config in the configs directory."""
        safe = name if name.endswith(".uae") else f"{name}.uae"
        return self.configs / safe
