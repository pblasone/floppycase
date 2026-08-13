"""Installation routine: fetch everything needed to play.

This installs the Amiberry emulator (via its official apt repository), the
small system tools floppycase needs, the WHDLoad distribution, and the floppycase
application icon. Network steps are best-effort and idempotent so re-running
``floppycase install`` is always safe.
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
from .roms import decode_in_place, detect_roms

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
_APP_ICON_SIZES = (16, 22, 24, 32, 48, 64, 128, 256)
_TRAY_ICON_SIZES = (16, 22, 24, 32)


def _refresh_desktop_caches(icon_theme_root: Path, log=print) -> None:
    """Ask GTK / xdg to notice newly installed icons and .desktop files."""
    # Ensure a minimal index.theme so hicolor lookups work for this user tree.
    index = icon_theme_root / "index.theme"
    directories = ["scalable/apps", "scalable/status"]
    sections = [
        "[Icon Theme]",
        "Name=Hicolor",
        "Comment=Fallback icon theme",
        "",
        "[scalable/apps]",
        "Size=128",
        "Type=Scalable",
        "MinSize=1",
        "MaxSize=512",
        "Context=Applications",
        "",
        "[scalable/status]",
        "Size=22",
        "Type=Scalable",
        "MinSize=1",
        "MaxSize=512",
        "Context=Status",
        "",
    ]
    for size in _APP_ICON_SIZES:
        directories.append(f"{size}x{size}/apps")
        sections += [
            f"[{size}x{size}/apps]",
            f"Size={size}",
            "Type=Fixed",
            "Context=Applications",
            "",
        ]
        directories.append(f"{size}x{size}/status")
        sections += [
            f"[{size}x{size}/status]",
            f"Size={size}",
            "Type=Fixed",
            "Context=Status",
            "",
        ]
    sections.insert(3, "Directories=" + ",".join(directories))
    index.write_text("\n".join(sections), encoding="utf-8")

    cache_cmd = shutil.which("gtk-update-icon-cache")
    if cache_cmd:
        result = _run(
            [cache_cmd, "-f", "-t", str(icon_theme_root)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            log("Icon cache refreshed")
        else:
            log("Icon cache refresh skipped (gtk-update-icon-cache reported an error)")

    desk_cmd = shutil.which("update-desktop-database")
    if desk_cmd:
        apps = desktop.applications_dir()
        apps.mkdir(parents=True, exist_ok=True)
        _run(
            [desk_cmd, str(apps)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def install_icon(log=print) -> Path:
    """Install FloppyCase icons into the user icon theme and return the app icon path.

    Installs SVG + PNG sizes (Mint/Cinnamon often ignores scalable-only icons)
    and refreshes the icon / desktop-file caches.
    """
    base = desktop.icons_home()
    assets = resources.files("floppycase.assets")
    icon_assets = assets.joinpath("icons")

    apps_scalable = base / "scalable" / "apps"
    status_scalable = base / "scalable" / "status"
    apps_scalable.mkdir(parents=True, exist_ok=True)
    status_scalable.mkdir(parents=True, exist_ok=True)

    app_svg = apps_scalable / "floppycase.svg"
    tray_svg = status_scalable / "floppycase-tray.svg"
    app_svg.write_bytes(assets.joinpath("floppycase.svg").read_bytes())
    tray_bytes = assets.joinpath("floppycase-tray.svg").read_bytes()
    tray_svg.write_bytes(tray_bytes)
    (apps_scalable / "floppycase-tray.svg").write_bytes(tray_bytes)

    for size in _APP_ICON_SIZES:
        target_dir = base / f"{size}x{size}" / "apps"
        target_dir.mkdir(parents=True, exist_ok=True)
        src = icon_assets.joinpath(f"floppycase-{size}.png")
        (target_dir / "floppycase.png").write_bytes(src.read_bytes())

    for size in _TRAY_ICON_SIZES:
        target_dir = base / f"{size}x{size}" / "status"
        target_dir.mkdir(parents=True, exist_ok=True)
        src = icon_assets.joinpath(f"floppycase-tray-{size}.png")
        (target_dir / "floppycase-tray.png").write_bytes(src.read_bytes())

    _refresh_desktop_caches(base, log=log)

    preferred = desktop.installed_icon_path() or app_svg
    log(f"Icon installed at {preferred}")
    log(f"Tray icon installed at {tray_svg}")
    return preferred


def install_app_launcher(log=print) -> Path:
    """Install a desktop-menu launcher for the FloppyCase GUI."""
    # Caller should run install_icon() first so Icon= can be an absolute PNG path.
    target = desktop.write_app_launcher()
    _refresh_desktop_caches(desktop.icons_home(), log=lambda *_: None)
    log(f"App launcher installed at {target}")
    log(f"Launcher Icon= {desktop.icon_for_desktop()}")
    return target

# --- Kickstart / WHDLoad booter wiring -----------------------------------------
def _looks_like_rom(path: Path) -> bool:
    if not path.is_file():
        return False
    size = path.stat().st_size
    return 128 * 1024 <= size <= 4 * 1024 * 1024


def effective_roms_dir(paths: Paths) -> Path:
    """The directory FloppyCase uses for Kickstart ROMs.

    Single source of truth: Amiberry's own ROM folder when the emulator is
    installed. Falls back to ``~/FloppyCase/roms`` only before Amiberry exists.
    """
    if amiberry.is_installed():
        return amiberry.rom_path()
    return paths.roms


def migrate_legacy_roms(paths: Paths, dest: Path, log=print) -> int:
    """Copy ROMs/rom.key from a leftover ``~/FloppyCase/roms`` into ``dest``.

    Older builds asked users to drop ROMs under the FloppyCase tree; we still
    migrate those once into Amiberry's folder. Never deletes the originals.
    """
    legacy = paths.roms
    if not legacy.exists() or legacy.resolve() == dest.resolve():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    for src in sorted(legacy.iterdir()):
        if src.name in {
            ".floppycase-decoded",
            "floppycase-decoded",
            ".easyamiga-decoded",
            "easyamiga-decoded",
        }:
            continue
        if not (src.is_file() and (_looks_like_rom(src) or src.name.lower() == "rom.key")):
            continue
        target = dest / src.name
        if target.exists():
            continue
        try:
            shutil.copy2(src, target)
            moved += 1
        except OSError as exc:
            log(f"Could not copy {src.name} into {dest}: {exc}")
    if moved:
        log(f"Migrated {moved} ROM file(s) from {legacy} into {dest}")
    return moved


def sync_kickstarts(paths: Paths, log=print) -> int:
    """Ensure Kickstart ROMs are present and usable in Amiberry's ROM folder.

    Migrates any leftover ``~/FloppyCase/roms`` files into Amiberry's folder,
    then decodes encoded Amiga Forever ROMs in place. Returns usable ROM count.
    """
    if not amiberry.is_installed():
        return 0
    dest = effective_roms_dir(paths)
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log(f"Could not prepare ROM folder {dest}: {exc}")
        return 0

    migrate_legacy_roms(paths, dest, log=log)

    decoded = decode_in_place(dest)
    if decoded:
        log(f"Decoded {decoded} Amiga Forever ROM(s) in place (originals kept as *.encoded)")

    usable = 0
    encrypted_unusable = 0
    for rom in detect_roms(dest):  # decodes encoded ROMs in place as a side effect
        if rom.usable:
            usable += 1
        elif rom.encoded:
            encrypted_unusable += 1

    if usable:
        log(f"{usable} usable Kickstart ROM(s) in {dest}")
    if encrypted_unusable:
        log(
            f"{encrypted_unusable} ROM(s) are encrypted (Amiga Forever) with no rom.key - "
            f"add rom.key next to them in {dest}, or run Amiga Forever once to decrypt."
        )
    return usable


def _db_game_count(path: Path) -> int:
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ValueError):
        return 0
    games = data.get("games")
    if isinstance(games, list):
        return len(games)
    try:
        return int(data.get("game_count", 0) or 0)
    except (TypeError, ValueError):
        return 0


def whdload_db_counts() -> tuple[int, int]:
    """(active game count, backup game count) for Amiberry's WHDLoad database."""
    gd = amiberry.whdboot_path() / "game-data"
    return _db_game_count(gd / "whdload_db.json"), _db_game_count(gd / "whdload_db.bak")


def load_whdload_db() -> tuple[dict, dict]:
    """Load Amiberry's WHDLoad game database, indexed by sha1 and by filename.

    Prefers the full backup if the active database looks like a stub.
    """
    import json

    gd = amiberry.whdboot_path() / "game-data"
    active = gd / "whdload_db.json"
    backup = gd / "whdload_db.bak"
    path = active
    if _db_game_count(backup) > _db_game_count(active):
        path = backup
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ValueError):
        return {}, {}
    by_sha1: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for game in data.get("games", []):
        sha = (game.get("sha1") or "").lower()
        name = (game.get("filename") or "")
        if sha:
            by_sha1[sha] = game
        if name:
            by_name[name.lower()] = game
    return by_sha1, by_name


def repair_whdload_db(log=print) -> bool:
    """Restore the full WHDLoad game database if the active one is a stub.

    Amiberry's ``--download-whdboot`` can replace the full ``whdload_db.json``
    with a near-empty stub (backing the real one up to ``whdload_db.bak``). An
    empty database makes the booter mis-configure almost every game
    (DOS-Error #205). If the backup has many more games, restore it.
    """
    if not amiberry.is_installed():
        return False
    gd = amiberry.whdboot_path() / "game-data"
    db = gd / "whdload_db.json"
    bak = gd / "whdload_db.bak"
    if not bak.exists():
        return False
    active = _db_game_count(db) if db.exists() else 0
    full = _db_game_count(bak)
    if full > 100 and full > active:
        try:
            shutil.copy2(bak, db)
        except OSError as exc:
            log(f"Could not restore WHDLoad database: {exc}")
            return False
        log(f"Restored WHDLoad game database ({full} games; was {active}).")
        return True
    return False


def ensure_whdboot(log=print) -> bool:
    """Ensure Amiberry's WHDLoad Booter assets exist and the DB isn't a stub.

    Note: we deliberately avoid ``--download-whdboot`` unless the booter is
    entirely missing, because in some Amiberry builds it overwrites the full
    game database with a tiny stub.
    """
    if not amiberry.is_installed():
        return False
    booter = amiberry.whdboot_path() / "WHDLoad"
    ok = True
    if not booter.exists():
        exe = amiberry.find_amiberry()
        log("Fetching Amiberry WHDLoad Booter assets...")
        result = _run([exe, "--download-whdboot"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok = result.returncode == 0
    repair_whdload_db(log=log)
    return ok


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
