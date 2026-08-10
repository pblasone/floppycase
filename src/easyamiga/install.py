"""Installation routine: fetch everything needed to play.

This installs the Amiberry emulator (via its official apt repository), the
small system tools easyamiga needs, the WHDLoad distribution, and the easyamiga
application icon. Network steps are best-effort and idempotent so re-running
``easyamiga install`` is always safe.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib import resources
from pathlib import Path

import requests

from . import amiberry, desktop
from .paths import Paths

WHDLOAD_URL = "https://whdload.de/whdload/WHDLoad_usr.lha"

APT_REPO_INSTALLER = "https://packages.amiberry.com/install.sh"


class InstallError(RuntimeError):
    pass


def _is_root() -> bool:
    return os.geteuid() == 0


def _sudo(cmd: list[str]) -> list[str]:
    if _is_root():
        return cmd
    if shutil.which("sudo"):
        return ["sudo", *cmd]
    return cmd


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, text=True, **kwargs)


# --- Amiberry ------------------------------------------------------------------
def install_amiberry(log=print) -> bool:
    """Install Amiberry from its official apt repository. Idempotent."""
    if amiberry.is_installed():
        log(f"Amiberry already installed at {amiberry.find_amiberry()}")
        return True

    if not shutil.which("apt-get"):
        raise InstallError(
            "Automatic Amiberry install currently supports Debian/Ubuntu (apt) only. "
            "Install Amiberry manually: https://github.com/BlitterStudio/amiberry"
        )

    log("Adding the official Amiberry apt repository...")
    # The installer script configures packages.amiberry.com as an apt source.
    installer = _run(
        _sudo(["sh", "-c", f"curl -fsSL {APT_REPO_INSTALLER} | sh"]),
    )
    if installer.returncode != 0:
        raise InstallError(
            "Failed to configure the Amiberry apt repository. Check network access."
        )

    log("Updating package lists...")
    _run(_sudo(["apt-get", "update"]))
    log("Installing Amiberry...")
    result = _run(_sudo(["apt-get", "install", "-y", "amiberry"]))
    if result.returncode != 0 or not amiberry.is_installed():
        raise InstallError("apt failed to install the 'amiberry' package.")
    log(f"Amiberry installed at {amiberry.find_amiberry()}")
    return True


def _has_tkinter() -> bool:
    try:
        import tkinter  # noqa: F401

        return True
    except Exception:
        return False


def install_system_deps(log=print) -> None:
    """Install small helper tools: lhasa (WHDLoad .lha) and python3-tk (GUI)."""
    if not shutil.which("apt-get"):
        return
    packages = []
    if not (shutil.which("lha") or shutil.which("lhasa")):
        packages.append("lhasa")
    if not _has_tkinter():
        packages.append("python3-tk")
    if not packages:
        return
    log(f"Installing helper packages: {', '.join(packages)}...")
    _run(_sudo(["apt-get", "install", "-y", *packages]))


# --- Downloads -----------------------------------------------------------------
def download_file(url: str, dest: Path, log=print, timeout: int = 60) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"Downloading {url}")
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 16):
                if chunk:
                    handle.write(chunk)
        tmp.replace(dest)
    return dest


def install_whdload(paths: Paths, log=print) -> bool:
    """Download and unpack WHDLoad into the whdload directory. Best-effort."""
    # The archive extracts into whdload/WHDLoad/... with the loader in C/.
    marker = paths.whdload / "WHDLoad" / "C" / "WHDLoad"
    if marker.exists():
        log("WHDLoad already installed.")
        return True

    archive = paths.downloads / "WHDLoad_usr.lha"
    try:
        if not archive.exists():
            download_file(WHDLOAD_URL, archive, log=log)
    except Exception as exc:  # network / URL issues are non-fatal
        log(f"Could not download WHDLoad ({exc}). Skipping - you can add it later.")
        return False

    paths.whdload.mkdir(parents=True, exist_ok=True)
    lha = shutil.which("lha")
    lhasa = shutil.which("lhasa")
    result = None
    if lha:
        # `xfw=DIR` extracts (x) with force overwrite (f) into DIR (w) - non-interactive.
        result = _run([lha, f"xfw={paths.whdload}", str(archive)],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if (result is None or result.returncode != 0) and lhasa:
        result = _run([lhasa, "-f", "e", str(archive)], cwd=str(paths.whdload))
    if result is None:
        log("No lha/lhasa extractor found; leaving WHDLoad archive in downloads/.")
        return False
    if result.returncode == 0 and marker.exists():
        log(f"WHDLoad unpacked into {paths.whdload}")
        return True
    log("WHDLoad extraction failed; archive kept in downloads/.")
    return False


# --- Icon ----------------------------------------------------------------------
def install_icon(log=print) -> Path:
    """Install the easyamiga icon into the user icon theme and return its path."""
    target_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "easyamiga.svg"
    source = resources.files("easyamiga.assets").joinpath("easyamiga.svg")
    target.write_bytes(source.read_bytes())
    log(f"Icon installed at {target}")
    return target


def install_app_launcher(log=print) -> Path:
    """Install a desktop-menu launcher for the easyamiga GUI."""
    target = desktop.write_app_launcher()
    log(f"App launcher installed at {target}")
    return target


# --- Kickstart / WHDLoad booter wiring -----------------------------------------
def _looks_like_rom(path: Path) -> bool:
    if not path.is_file():
        return False
    size = path.stat().st_size
    return 128 * 1024 <= size <= 4 * 1024 * 1024


def sync_kickstarts(paths: Paths, log=print) -> int:
    """Make the user's Kickstart ROMs visible to Amiberry's WHDLoad Booter.

    Amiberry scans its own ROM path (e.g. ``~/Amiberry/ROMs``) and symlinks
    recognised Kickstarts into the WHDLoad Booter's ``Kickstarts`` folder. Our
    ROMs live under ``~/EasyAmiga/roms``, so we symlink them across. Returns the
    number of ROMs made available.
    """
    if not amiberry.is_installed() or not paths.roms.exists():
        return 0
    target_dir = amiberry.rom_path()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log(f"Could not prepare Amiberry ROM path {target_dir}: {exc}")
        return 0

    count = 0
    for rom in sorted(paths.roms.rglob("*")):
        if not _looks_like_rom(rom):
            continue
        link = target_dir / rom.name
        try:
            if link.is_symlink() or link.exists():
                if link.resolve() == rom.resolve():
                    count += 1
                    continue
                link.unlink()
            link.symlink_to(rom)
            count += 1
        except OSError:
            # Fall back to copying if symlinks aren't permitted.
            try:
                shutil.copy2(rom, link)
                count += 1
            except OSError as exc:
                log(f"Could not link ROM {rom.name}: {exc}")
    if count:
        log(f"Made {count} Kickstart ROM(s) available to Amiberry at {target_dir}")
    return count


def ensure_whdboot(log=print) -> bool:
    """Ensure Amiberry's WHDLoad Booter assets exist (download if missing)."""
    if not amiberry.is_installed():
        return False
    booter = amiberry.whdboot_path() / "WHDLoad"
    if booter.exists():
        return True
    exe = amiberry.find_amiberry()
    log("Fetching Amiberry WHDLoad Booter assets...")
    result = _run([exe, "--download-whdboot"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


# --- Orchestration -------------------------------------------------------------
def install_all(paths: Paths, log=print, with_whdload: bool = True) -> dict[str, bool]:
    """Run the full install routine. Returns a summary of what succeeded."""
    paths.ensure()
    summary: dict[str, bool] = {}

    install_system_deps(log=log)
    try:
        summary["amiberry"] = install_amiberry(log=log)
    except InstallError as exc:
        log(f"Amiberry install failed: {exc}")
        summary["amiberry"] = False

    try:
        summary["icon"] = bool(install_icon(log=log))
    except Exception as exc:  # icon is cosmetic
        log(f"Icon install skipped: {exc}")
        summary["icon"] = False

    try:
        summary["app_launcher"] = bool(install_app_launcher(log=log))
    except Exception as exc:  # launcher is cosmetic
        log(f"App launcher skipped: {exc}")
        summary["app_launcher"] = False

    if with_whdload:
        summary["whdload"] = install_whdload(paths, log=log)

    if summary.get("amiberry"):
        try:
            summary["whdboot"] = ensure_whdboot(log=log)
        except Exception as exc:
            log(f"WHDLoad Booter setup skipped: {exc}")
            summary["whdboot"] = False
        try:
            sync_kickstarts(paths, log=log)
            summary["kickstarts_linked"] = True
        except Exception as exc:
            log(f"Kickstart sync skipped: {exc}")
            summary["kickstarts_linked"] = False

    return summary
