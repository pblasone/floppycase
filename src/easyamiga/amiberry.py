"""Locate and launch the Amiberry emulator."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

#: Places Amiberry may be installed outside of ``$PATH``.
_CANDIDATE_PATHS = [
    "/usr/bin/amiberry",
    "/usr/local/bin/amiberry",
    "/opt/amiberry/amiberry",
    str(Path.home() / "Amiberry" / "amiberry"),
]


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


def build_command(config_path: Path, amiberry: str | None = None) -> list[str]:
    exe = amiberry or find_amiberry()
    if exe is None:
        raise FileNotFoundError(
            "Amiberry is not installed. Run 'easyamiga install' first."
        )
    return [exe, "--config", str(config_path)]


def launch(
    config_path: Path,
    amiberry: str | None = None,
    wait: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen | subprocess.CompletedProcess:
    """Launch Amiberry with the given config.

    ``wait=True`` blocks until the emulator exits (used by the ``run`` command);
    ``wait=False`` returns the ``Popen`` handle immediately.
    """
    import os

    cmd = build_command(config_path, amiberry)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    if wait:
        return subprocess.run(cmd, env=env, check=False)
    return subprocess.Popen(cmd, env=env)
