"""easyamiga command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__, amiberry, install as install_mod, library
from .config_gen import ConfigOptions, read_meta, write_config
from .games import (
    add_game as add_game_impl,
    discover_game_sources,
    list_configs,
    prune_orphans,
    resolve_launch,
    scan_games,
)
from .models import DEFAULT_MODEL, MODELS, get_model
from .paths import Paths
from .roms import (
    AROS,
    DetectedRom,
    KNOWN_ROMS,
    crc32_of,
    default_model_key,
    detect_roms,
    pick_rom_for_model,
    sha1_of,
)

WHDLOAD_ARCHIVE_SUFFIXES = {".lha", ".lzh", ".lzx", ".zip"}

app = typer.Typer(
    add_completion=False,
    help="Plug-and-play Amiga gaming on Linux with Amiberry.",
    no_args_is_help=True,
)
console = Console()

BaseOption = typer.Option(
    None,
    "--base",
    help="easyamiga base directory (default: ~/EasyAmiga or $EASYAMIGA_HOME).",
)


def _paths(base: Optional[str]) -> Paths:
    return Paths.resolve(base)


def _roms_dir(paths: Paths) -> Path:
    """Effective ROM directory (Amiberry's own folder when it is installed)."""
    return install_mod.effective_roms_dir(paths)


def _resolve_model(paths: Paths, explicit: Optional[str]) -> str:
    """Explicit model wins; otherwise pick the model that matches a detected ROM."""
    if explicit:
        return explicit
    return default_model_key(detect_roms(_roms_dir(paths)), DEFAULT_MODEL)


def _usable_or_warn(rom: Optional[DetectedRom]) -> Optional[DetectedRom]:
    """Drop an unusable (encrypted, keyless) ROM to AROS with a clear warning."""
    if rom is not None and not rom.usable:
        console.print(
            f"[yellow]ROM '{rom.path.name}' is an encrypted Amiga Forever ROM and no "
            "rom.key was found, so it can't be used. Falling back to the free AROS ROM.\n"
            "Fix: copy 'rom.key' from Amiga Forever into ~/EasyAmiga/roms (easyamiga will "
            "decode it), or run Amiga Forever once to get decrypted .rom files.[/yellow]"
        )
        return None
    return rom


def _resolve_rom(paths: Paths, rom_path: Optional[str], model_key: str) -> Optional[DetectedRom]:
    """Return the DetectedRom to use, or None to fall back to built-in AROS."""
    if rom_path:
        p = Path(rom_path).expanduser()
        if not p.exists():
            raise typer.BadParameter(f"ROM file not found: {p}")
        crc = crc32_of(p)
        return DetectedRom(path=p, crc32=crc, known=KNOWN_ROMS.get(crc))
    detected = detect_roms(_roms_dir(paths))
    return pick_rom_for_model(detected, model_key)


# --- commands ------------------------------------------------------------------
@app.command()
def version() -> None:
    """Show the easyamiga version."""
    console.print(f"easyamiga {__version__}")


@app.command()
def init(base: Optional[str] = BaseOption) -> None:
    """Create the easyamiga directory structure."""
    paths = _paths(base)
    paths.ensure()
    for step in (install_mod.install_icon, install_mod.install_app_launcher):
        try:
            step(log=lambda *_: None)
        except Exception:
            pass

    rdir = _roms_dir(paths)
    table = Table(title=f"easyamiga initialised at {paths.base}", show_header=True)
    table.add_column("Directory")
    table.add_column("Purpose")
    table.add_row(str(rdir), "Kickstart ROMs (drop them here, with rom.key if any)")
    table.add_row(str(paths.games), "Games: WHDLoad folders / ADFs")
    table.add_row(str(paths.workbench), "Workbench / boot content")
    table.add_row(str(paths.configs), "Generated Amiberry configs")
    table.add_row(str(paths.whdload), "WHDLoad distribution")
    table.add_row(str(paths.downloads), "Download cache")
    console.print(table)
    if not amiberry.is_installed():
        console.print(
            "\nNext: [bold]easyamiga install[/bold] to install Amiberry, then "
            "[bold]easyamiga config[/bold] to create your first machine."
        )
    else:
        console.print(
            f"\nDrop Kickstart ROMs into [bold]{rdir}[/bold] (Amiberry's own ROM folder), "
            "then [bold]easyamiga gui[/bold] to play."
        )


@app.command()
def install(
    base: Optional[str] = BaseOption,
    whdload: bool = typer.Option(True, help="Also download and unpack WHDLoad."),
) -> None:
    """Install Amiberry and supporting packages."""
    paths = _paths(base)
    console.print(Panel.fit("Installing easyamiga prerequisites", style="cyan"))
    summary = install_mod.install_all(paths, log=console.print, with_whdload=whdload)

    table = Table(title="Install summary")
    table.add_column("Component")
    table.add_column("Status")
    for name, ok in summary.items():
        table.add_row(name, "[green]ok[/green]" if ok else "[yellow]skipped/failed[/yellow]")
    console.print(table)

    if not summary.get("amiberry"):
        console.print(
            "[yellow]Amiberry was not installed. See "
            "https://github.com/BlitterStudio/amiberry for manual instructions.[/yellow]"
        )


@app.command()
def config(
    base: Optional[str] = BaseOption,
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help=f"Amiga model ({', '.join(MODELS)}). Auto-detected from ROM if omitted."
    ),
    rom: Optional[str] = typer.Option(None, "--rom", help="Path to a Kickstart ROM (else auto-detect / AROS)."),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Config name."),
    gui: bool = typer.Option(False, "--gui", help="Show the Amiberry GUI instead of booting straight in."),
) -> None:
    """Generate an Amiberry config for a machine (auto-configured from the ROM)."""
    paths = _paths(base)
    paths.ensure()

    detected = detect_roms(_roms_dir(paths))
    model_key = model
    if model_key is None:
        # Auto-select model from a known ROM if possible.
        known = next((d for d in detected if d.known), None)
        model_key = known.known.model if known else DEFAULT_MODEL
        if rom:
            rp = Path(rom).expanduser()
            if rp.exists():
                kr = KNOWN_ROMS.get(crc32_of(rp))
                if kr:
                    model_key = kr.model

    amiga = get_model(model_key)
    chosen_rom = _usable_or_warn(_resolve_rom(paths, rom, amiga.key))
    config_name = name or amiga.key

    options = ConfigOptions(model=amiga, paths=paths, rom=chosen_rom, show_gui=gui, roms_dir=_roms_dir(paths))
    path = write_config(options, config_name)

    rom_desc = chosen_rom.description if chosen_rom else "AROS (built-in, no ROM needed)"
    console.print(
        Panel.fit(
            f"[bold]{amiga.name}[/bold]\n"
            f"Kickstart: {rom_desc}\n"
            f"Chip: {amiga.chipmem_kb} KB | Fast: {amiga.fastmem_mb} MB | CPU: {amiga.cpu_model}\n"
            f"Config: {path}",
            title="Config created",
            style="green",
        )
    )
    console.print(f"Run it with: [bold]easyamiga run {config_name}[/bold]")


@app.command("add-game")
def add_game(
    game: str = typer.Argument(..., help="Path to an ADF, WHDLoad folder, or archive."),
    base: Optional[str] = BaseOption,
    model: Optional[str] = typer.Option(None, "--model", "-m", help=f"Amiga model ({', '.join(MODELS)}). Auto-detected from ROM if omitted."),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Display name for the game."),
    rom: Optional[str] = typer.Option(None, "--rom", help="Kickstart ROM path (else auto-detect / AROS)."),
    launcher: bool = typer.Option(True, help="Create a desktop launcher icon."),
) -> None:
    """Add a game: store it, build a config, and create a clickable desktop icon."""
    paths = _paths(base)
    paths.ensure()
    amiga = get_model(_resolve_model(paths, model))
    chosen_rom = _usable_or_warn(_resolve_rom(paths, rom, amiga.key))

    result = add_game_impl(
        paths=paths,
        roms_dir=_roms_dir(paths),
        source=Path(game),
        model=amiga,
        name=name,
        rom=chosen_rom,
        create_launcher=launcher,
    )
    console.print(
        Panel.fit(
            f"[bold]{result.name}[/bold] ({result.kind})\n"
            f"Stored: {result.stored}\n"
            f"Config: {result.config_path}\n"
            + (f"Launcher: {result.desktop_path}" if result.desktop_path else "No launcher created"),
            title="Game added",
            style="green",
        )
    )
    if result.desktop_path:
        console.print("You can now launch it from your desktop's application menu.")


@app.command()
def run(
    name: str = typer.Argument(..., help="Config name (or path to a .uae file)."),
    base: Optional[str] = BaseOption,
) -> None:
    """Launch Amiberry with a generated config."""
    paths = _paths(base)
    candidate = Path(name).expanduser()
    if candidate.suffix == ".uae" and candidate.exists():
        config_path = candidate
    else:
        config_path = paths.config_file(name)
    if not config_path.exists():
        available = ", ".join(p.stem for p in list_configs(paths)) or "(none)"
        raise typer.BadParameter(f"No config named {name!r}. Available: {available}")
    if not amiberry.is_installed():
        console.print("[red]Amiberry is not installed. Run 'easyamiga install' first.[/red]")
        raise typer.Exit(1)

    eff = library.effective(paths, config_path.stem)
    joyports, options = library.launch_args(eff)
    source, kind = resolve_launch(paths, config_path)
    if kind == "whdload" and source is not None:
        # WHDLoad game: boot it via Amiberry's WHDLoad Booter (--autoload),
        # regardless of what a stale config said.
        install_mod.sync_kickstarts(paths, log=lambda *_: None)
        console.print(f"Launching game (WHDLoad auto-boot): {source.name}")
        try:
            amiberry.launch_game(source, kind, wait=True, joyports=joyports, options=options)
        except FileNotFoundError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1)
    else:
        # ADF game (boots the floppy) or a bare machine: use the generated config.
        console.print(f"Launching Amiberry: {config_path}")
        amiberry.launch(config_path, wait=True, joyports=joyports, options=options)


@app.command("list")
def list_cmd(base: Optional[str] = BaseOption) -> None:
    """List detected ROMs, generated configs, and stored games."""
    paths = _paths(base)

    roms = detect_roms(_roms_dir(paths))
    rom_table = Table(title=f"Kickstart ROMs in {_roms_dir(paths)}")
    rom_table.add_column("File")
    rom_table.add_column("CRC32")
    rom_table.add_column("Identified as")
    if roms:
        for r in roms:
            rom_table.add_row(r.path.name, r.crc32, r.description)
    else:
        rom_table.add_row("(none)", "-", "Will fall back to built-in AROS")
    console.print(rom_table)

    cfg_table = Table(title="Configs")
    cfg_table.add_column("Name")
    cfg_table.add_column("Path")
    for c in list_configs(paths):
        cfg_table.add_row(c.stem, str(c))
    if not list_configs(paths):
        cfg_table.add_row("(none)", "-")
    console.print(cfg_table)


@app.command()
def scan(
    base: Optional[str] = BaseOption,
    model: Optional[str] = typer.Option(None, "--model", "-m", help=f"Model for newly found games ({', '.join(MODELS)}). Auto-detected from ROM if omitted."),
    launcher: bool = typer.Option(True, help="Create desktop launchers for new games."),
    force: bool = typer.Option(False, "--force", help="Regenerate configs even if they already exist."),
) -> None:
    """Scan the games folder and register every game found."""
    paths = _paths(base)
    amiga = get_model(_resolve_model(paths, model))
    rom = _usable_or_warn(_resolve_rom(paths, None, amiga.key))
    pruned = prune_orphans(paths)  # drop games whose files were deleted
    games = scan_games(paths, amiga, rom=rom, create_launchers=launcher, overwrite=force, roms_dir=_roms_dir(paths), prune=False)
    added = sum(1 for g in games if g.newly_created)

    table = Table(title=f"Scanned {paths.games}")
    table.add_column("Game")
    table.add_column("Type")
    table.add_column("Status")
    for g in games:
        table.add_row(g.name, g.kind, "[green]new[/green]" if g.newly_created else "already registered")
    for name in pruned:
        table.add_row(name, "-", "[red]removed (file deleted)[/red]")
    if not games and not pruned:
        table.add_row("(none)", "-", "drop games into the folder first")
    console.print(table)
    summary = f"Found {len(games)} game(s); [bold]{added}[/bold] newly added"
    if pruned:
        summary += f"; [bold]{len(pruned)}[/bold] removed"
    console.print(summary + ".")


@app.command("sync-roms")
def sync_roms(base: Optional[str] = BaseOption) -> None:
    """Decode (if needed) and copy your Kickstart ROMs into Amiberry's ROM folder.

    Run this after adding ROMs or a rom.key. Games launched via easyamiga do this
    automatically, but this is handy after changing ROMs while Amiberry is set up.
    """
    paths = _paths(base)
    if not amiberry.is_installed():
        console.print("[red]Amiberry is not installed. Run 'easyamiga install' first.[/red]")
        raise typer.Exit(1)
    n = install_mod.sync_kickstarts(paths, log=console.print)
    roms = detect_roms(_roms_dir(paths))
    usable_a1200 = any(r.usable and r.known and r.known.model == "a1200" for r in roms)
    console.print(f"[bold]{n}[/bold] usable ROM(s) in {_roms_dir(paths)}.")
    if usable_a1200:
        console.print("[green]A1200 Kickstart 3.1 is available - WHDLoad auto-boot should work.[/green]")
    console.print(
        "Launch a game with [bold]easyamiga run <name>[/bold] or the GUI "
        "(they rescan Amiberry's ROMs automatically)."
    )


@app.command("clean-configs")
def clean_configs(
    name: Optional[str] = typer.Argument(None, help="Game name to reset (default: all WHDLoad auto-boot caches)."),
    base: Optional[str] = BaseOption,
) -> None:
    """Remove Amiberry's cached auto-generated game configs so they regenerate fresh.

    Useful if a game got a bad auto-config (e.g. stuck at 68000, or a wrong
    DATA path) before your ROMs/database were set up correctly.
    """
    paths = _paths(base)
    if not amiberry.is_installed():
        console.print("[red]Amiberry is not installed. Run 'easyamiga install' first.[/red]")
        raise typer.Exit(1)

    removed: list[Path] = []
    if name:
        cfg = paths.config_file(name)
        src = read_meta(cfg).get("source") if cfg.exists() else None
        target = Path(src) if src else Path(name)
        removed = amiberry.clear_game_config(target)
    else:
        autoboots = amiberry.autoboots_path()
        if autoboots.exists():
            for pattern in ("*.uae", "*.auto-startup"):
                for f in sorted(autoboots.glob(pattern)):
                    try:
                        f.unlink()
                        removed.append(f)
                    except OSError:
                        pass

    if removed:
        console.print(f"Removed {len(removed)} cached file(s):")
        for r in removed:
            console.print(f"  {r}")
    else:
        console.print("No cached game configs to remove.")


@app.command()
def verify(base: Optional[str] = BaseOption) -> None:
    """Check which games are recognised RetroPlay packs (and which may need work).

    Matches each game against Amiberry's WHDLoad database by SHA-1 (exact pack)
    or filename, so you can tell plug-and-play packs from ones that likely need
    manual setup or a different download.
    """
    paths = _paths(base)
    by_sha1, by_name = install_mod.load_whdload_db()
    if not by_sha1 and not by_name:
        console.print(
            "[yellow]WHDLoad database unavailable - run 'easyamiga install' or "
            "'easyamiga repair-whdboot' first.[/yellow]"
        )

    table = Table(title=f"Game check ({paths.games})")
    table.add_column("Game")
    table.add_column("Status")
    recognised = 0
    total = 0
    for source in discover_game_sources(paths):
        total += 1
        if source.is_dir():
            table.add_row(source.name, "[yellow]folder - a .lha RetroPlay pack is recommended[/yellow]")
            continue
        if source.suffix.lower() not in WHDLOAD_ARCHIVE_SUFFIXES:
            table.add_row(source.name, "disk image (ADF/CD) - boots directly")
            continue
        entry = by_sha1.get(sha1_of(source))
        how = "exact pack"
        if entry is None:
            entry = by_name.get(source.stem.lower())
            how = "name match (different build)"
        if entry:
            recognised += 1
            table.add_row(source.name, f"[green]recognised[/green] ({how}): {entry.get('name', '?')}")
        else:
            table.add_row(source.name, "[yellow]not in database - may need manual setup or a RetroPlay pack[/yellow]")
    if total == 0:
        table.add_row("(none)", "drop game .lha files into the games folder first")
    console.print(table)
    if total:
        console.print(
            f"{recognised}/{total} recognised as WHDLoad packs. Recognised packs should "
            "auto-boot once the game's Kickstart is present (see 'easyamiga doctor')."
        )


@app.command("repair-whdboot")
def repair_whdboot(base: Optional[str] = BaseOption) -> None:
    """Restore Amiberry's full WHDLoad game database if it was replaced by a stub.

    A near-empty database causes almost every WHDLoad game to fail with
    DOS-Error #205 (the booter can't find each game's data drawer).
    """
    paths = _paths(base)
    if not amiberry.is_installed():
        console.print("[red]Amiberry is not installed. Run 'easyamiga install' first.[/red]")
        raise typer.Exit(1)
    active, backup = install_mod.whdload_db_counts()
    console.print(f"WHDLoad database: active={active} games, backup={backup} games.")
    if install_mod.repair_whdload_db(log=console.print):
        console.print("[green]Database restored.[/green] Re-launch your game (it will regenerate the boot config).")
    else:
        console.print("Database looks healthy; no repair needed.")


@app.command()
def gui(base: Optional[str] = BaseOption) -> None:
    """Launch the easyamiga desktop app (scan and click to play)."""
    try:
        from .gui import run_gui
    except Exception as exc:  # tkinter missing, etc.
        console.print(
            f"[red]Could not start the GUI ({exc}).[/red]\n"
            "Make sure Tk is installed (e.g. 'sudo apt install python3-tk'), "
            "or run 'easyamiga install'."
        )
        raise typer.Exit(1)
    run_gui(base)


@app.command()
def doctor(base: Optional[str] = BaseOption) -> None:
    """Diagnose the setup and report what is ready or missing."""
    paths = _paths(base)
    table = Table(title="easyamiga doctor")
    table.add_column("Check")
    table.add_column("Result")

    exe = amiberry.find_amiberry()
    rdir = _roms_dir(paths)
    table.add_row("Amiberry", f"[green]{exe}[/green]" if exe else "[red]not installed[/red]")
    table.add_row("Base directory", f"{paths.base} {'[green](exists)[/green]' if paths.base.exists() else '[yellow](missing - run init)[/yellow]'}")
    roms = detect_roms(rdir) if rdir.exists() else []
    known = [r for r in roms if r.known]
    encrypted = [r for r in roms if r.encoded and not r.has_key]
    table.add_row("ROM folder", str(rdir))
    table.add_row("ROMs", f"{len(roms)} found, {len(known)} identified" if roms else "none (AROS fallback)")
    if encrypted:
        table.add_row(
            "Encrypted ROMs",
            f"[yellow]{len(encrypted)} need rom.key (copy it into {rdir})[/yellow]",
        )

    if exe:
        present = {r.crc32 for r in roms if r.usable}
        wanted = [
            ("1.3 (A500)", "c4f0f55f"),
            ("2.05 (A600)", "43b0df7b"),
            ("3.1 (A1200)", "1483a091"),
        ]
        cover = ", ".join(
            f"[green]{label} \u2713[/green]" if crc in present else f"[yellow]{label} \u2717[/yellow]"
            for label, crc in wanted
        )
        table.add_row("Kickstarts (WHDLoad)", cover)
        if not all(crc in present for _, crc in wanted):
            table.add_row(
                "",
                "[yellow]Add the full Amiga Forever ROM set - different games need "
                "different Kickstarts.[/yellow]",
            )
        booter = amiberry.whdboot_path() / "WHDLoad"
        table.add_row("WHDLoad Booter", "[green]ready[/green]" if booter.exists() else "[yellow]missing (run install)[/yellow]")
        active, backup = install_mod.whdload_db_counts()
        if active < 100 and backup > active:
            table.add_row("WHDLoad game DB", f"[yellow]{active} games (stub!) - run 'easyamiga repair-whdboot'[/yellow]")
        else:
            table.add_row("WHDLoad game DB", f"{active} games")
    table.add_row("Configs", str(len(list_configs(paths))))
    console.print(table)


def main() -> None:  # console-script entry point
    app()


if __name__ == "__main__":
    main()
