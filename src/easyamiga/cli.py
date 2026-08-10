"""easyamiga command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__, amiberry, install as install_mod
from .config_gen import ConfigOptions, write_config
from .games import add_game as add_game_impl, list_configs
from .models import DEFAULT_MODEL, MODELS, get_model
from .paths import Paths
from .roms import AROS, DetectedRom, crc32_of, detect_roms, pick_rom_for_model, KNOWN_ROMS

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


def _resolve_rom(paths: Paths, rom_path: Optional[str], model_key: str) -> Optional[DetectedRom]:
    """Return the DetectedRom to use, or None to fall back to built-in AROS."""
    if rom_path:
        p = Path(rom_path).expanduser()
        if not p.exists():
            raise typer.BadParameter(f"ROM file not found: {p}")
        crc = crc32_of(p)
        return DetectedRom(path=p, crc32=crc, known=KNOWN_ROMS.get(crc))
    detected = detect_roms(paths.roms)
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
    try:
        install_mod.install_icon(log=lambda *_: None)
    except Exception:
        pass

    table = Table(title=f"easyamiga initialised at {paths.base}", show_header=True)
    table.add_column("Directory")
    table.add_column("Purpose")
    table.add_row(str(paths.roms), "Kickstart ROMs (drop them here)")
    table.add_row(str(paths.games), "Games: WHDLoad folders / ADFs")
    table.add_row(str(paths.workbench), "Workbench / boot content")
    table.add_row(str(paths.configs), "Generated Amiberry configs")
    table.add_row(str(paths.whdload), "WHDLoad distribution")
    table.add_row(str(paths.downloads), "Download cache")
    console.print(table)
    console.print(
        "\nNext: [bold]easyamiga install[/bold] to install Amiberry, then "
        "[bold]easyamiga config[/bold] to create your first machine."
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

    detected = detect_roms(paths.roms)
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
    chosen_rom = _resolve_rom(paths, rom, amiga.key)
    config_name = name or amiga.key

    options = ConfigOptions(model=amiga, paths=paths, rom=chosen_rom, show_gui=gui)
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
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help=f"Amiga model ({', '.join(MODELS)})."),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Display name for the game."),
    rom: Optional[str] = typer.Option(None, "--rom", help="Kickstart ROM path (else auto-detect / AROS)."),
    launcher: bool = typer.Option(True, help="Create a desktop launcher icon."),
) -> None:
    """Add a game: store it, build a config, and create a clickable desktop icon."""
    paths = _paths(base)
    paths.ensure()
    amiga = get_model(model)
    chosen_rom = _resolve_rom(paths, rom, amiga.key)

    result = add_game_impl(
        paths=paths,
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
    console.print(f"Launching Amiberry: {config_path}")
    amiberry.launch(config_path, wait=True)


@app.command("list")
def list_cmd(base: Optional[str] = BaseOption) -> None:
    """List detected ROMs, generated configs, and stored games."""
    paths = _paths(base)

    roms = detect_roms(paths.roms)
    rom_table = Table(title="Kickstart ROMs")
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
def doctor(base: Optional[str] = BaseOption) -> None:
    """Diagnose the setup and report what is ready or missing."""
    paths = _paths(base)
    table = Table(title="easyamiga doctor")
    table.add_column("Check")
    table.add_column("Result")

    exe = amiberry.find_amiberry()
    table.add_row("Amiberry", f"[green]{exe}[/green]" if exe else "[red]not installed[/red]")
    table.add_row("Base directory", f"{paths.base} {'[green](exists)[/green]' if paths.base.exists() else '[yellow](missing - run init)[/yellow]'}")
    roms = detect_roms(paths.roms) if paths.roms.exists() else []
    known = [r for r in roms if r.known]
    table.add_row("ROMs", f"{len(roms)} found, {len(known)} identified" if roms else "none (AROS fallback)")
    table.add_row("Configs", str(len(list_configs(paths))))
    console.print(table)


def main() -> None:  # console-script entry point
    app()


if __name__ == "__main__":
    main()
