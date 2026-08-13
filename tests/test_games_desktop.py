from pathlib import Path

from floppycase import desktop
from floppycase.games import (
    add_game,
    classify,
    discover_game_sources,
    list_configs,
    menu_launcher_enabled,
    resolve_launch,
    scan_games,
    set_menu_launcher,
)
from floppycase.models import get_model
from floppycase.paths import Paths


def test_classify(tmp_path):
    adf = tmp_path / "game.adf"
    adf.write_bytes(b"\x00" * 1024)
    assert classify(adf) == "adf"

    folder = tmp_path / "MyGame"
    folder.mkdir()
    assert classify(folder) == "whdload"

    lha = tmp_path / "game.lha"
    lha.write_bytes(b"\x00" * 10)
    assert classify(lha) == "whdload"


def test_add_adf_game_creates_config_and_launcher(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()

    adf = tmp_path / "Lemmings.adf"
    adf.write_bytes(b"\x00" * (880 * 1024))

    game = add_game(paths, adf, get_model("a500"), name="Lemmings", create_launcher=True)

    assert game.kind == "adf"
    assert game.config_path.exists()
    assert (paths.games / "Lemmings.adf").exists()
    # config references the stored ADF as floppy0
    text = game.config_path.read_text()
    assert "floppy0=" in text
    assert "Lemmings.adf" in text
    # launcher exists and is well-formed
    assert game.desktop_path is not None and game.desktop_path.exists()
    entry = game.desktop_path.read_text()
    assert "[Desktop Entry]" in entry
    assert "Name=Lemmings" in entry
    assert "run" in entry


def test_add_whdload_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()

    folder = tmp_path / "SomeWHD"
    folder.mkdir()
    (folder / "SomeWHD.slave").write_bytes(b"\x00" * 100)

    game = add_game(paths, folder, get_model("a1200"), create_launcher=False)
    assert game.kind == "whdload"
    assert (paths.games / "SomeWHD").is_dir()
    assert game.desktop_path is None
    assert game.config_path in list_configs(paths)


def test_desktop_slug_and_render():
    entry = desktop.render_desktop_entry("Turrican II!", "floppycase run turrican", "floppycase")
    assert "Name=Turrican II!" in entry
    assert desktop.desktop_file_path("Turrican II!").name == "floppycase-game-turrican-ii.desktop"


def test_scan_registers_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()

    # Drop two games directly into the games folder.
    (paths.games / "Chaos.adf").write_bytes(b"\x00" * (880 * 1024))
    whd = paths.games / "Turrican"
    whd.mkdir()
    (whd / "Turrican.slave").write_bytes(b"\x00" * 100)
    # A stray hidden/junk entry that must be ignored.
    (paths.games / ".DS_Store").write_bytes(b"junk")

    sources = discover_game_sources(paths)
    assert {s.name for s in sources} == {"Chaos.adf", "Turrican"}

    first = scan_games(paths, get_model("a500"))
    assert len(first) == 2
    assert all(g.newly_created for g in first)
    assert len(list_configs(paths)) == 2

    # Second scan finds the same games but registers nothing new.
    second = scan_games(paths, get_model("a500"))
    assert len(second) == 2
    assert not any(g.newly_created for g in second)


def test_resolve_launch_from_stale_config(tmp_path, monkeypatch):
    """A config without launch metadata still resolves to the .lha and WHDLoad."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()
    lha = paths.games / "WormsDC.lha"
    lha.write_bytes(b"x")
    # Simulate an old floppycase config: right name, no floppycase_* metadata, A500.
    stale = paths.configs / "WormsDC.uae"
    stale.write_text("config_description=floppycase: WormsDC (Amiga 500)\ncpu_model=68000\n")

    source, kind = resolve_launch(paths, stale)
    assert source == lha
    assert kind == "whdload"


def test_scan_heals_stale_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()
    lha = paths.games / "WormsDC.lha"
    lha.write_bytes(b"x")
    stale = paths.configs / "WormsDC.uae"
    stale.write_text("config_description=old\ncpu_model=68000\n")

    scan_games(paths, get_model("a1200"))
    healed = stale.read_text()
    # The stale config is regenerated with launch metadata and the new model.
    assert "floppycase_source=" in healed
    assert "floppycase_kind=whdload" in healed
    assert "floppycase_model=a1200" in healed


def test_scan_prunes_deleted_games(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()
    keep = paths.games / "Keeper.lha"
    keep.write_bytes(b"x")
    gone = paths.games / "Gone.lha"
    gone.write_bytes(b"x")

    scan_games(paths, get_model("a500"))
    assert {c.stem for c in list_configs(paths)} == {"Keeper", "Gone"}

    # User deletes one game file, then rescans.
    gone.unlink()
    scan_games(paths, get_model("a500"))
    assert {c.stem for c in list_configs(paths)} == {"Keeper"}


def test_prune_keeps_bare_machine_configs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    from floppycase.config_gen import ConfigOptions, write_config
    from floppycase.games import prune_orphans

    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()
    # A bare-machine config (no game source) must never be pruned.
    write_config(ConfigOptions(model=get_model("a500"), paths=paths), "a500")
    assert prune_orphans(paths) == []
    assert (paths.configs / "a500.uae").exists()


def test_scan_does_not_create_launchers_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()
    (paths.games / "Chaos.adf").write_bytes(b"\x00" * (880 * 1024))

    games = scan_games(paths, get_model("a500"))
    assert len(games) == 1
    assert games[0].desktop_path is None
    assert not menu_launcher_enabled(paths, "Chaos")


def test_menu_launcher_toggle(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()
    adf = tmp_path / "Lemmings.adf"
    adf.write_bytes(b"\x00" * (880 * 1024))
    add_game(paths, adf, get_model("a500"), name="Lemmings", create_launcher=False)

    assert not menu_launcher_enabled(paths, "Lemmings")
    launcher = set_menu_launcher(paths, "Lemmings", True, display_title="Lemmings!")
    assert launcher is not None and launcher.exists()
    assert menu_launcher_enabled(paths, "Lemmings")
    entry = launcher.read_text()
    assert "Name=Lemmings!" in entry

    set_menu_launcher(paths, "Lemmings", False)
    assert not menu_launcher_enabled(paths, "Lemmings")
    assert not launcher.exists()


def test_menu_launcher_ignores_orphan_desktop_file(tmp_path, monkeypatch):
    """A leftover .desktop file alone must not opt the game into the start menu."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()
    adf = tmp_path / "Chaos.adf"
    adf.write_bytes(b"\x00" * (880 * 1024))
    add_game(paths, adf, get_model("a500"), name="Chaos", create_launcher=False)

    orphan = desktop.desktop_file_path("Chaos")
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("[Desktop Entry]\nName=Chaos\n", encoding="utf-8")
    assert orphan.exists()
    assert not menu_launcher_enabled(paths, "Chaos")


def test_app_launcher_written(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    from floppycase import install

    install.install_icon(log=lambda *_: None)
    target = desktop.write_app_launcher()
    assert target.exists()
    text = target.read_text()
    assert "Name=FloppyCase" in text
    assert "gui" in text
    # Mint/Cinnamon resolve theme names unreliably; we embed an absolute icon path.
    assert "Icon=" in text
    icon_line = next(line for line in text.splitlines() if line.startswith("Icon="))
    icon_path = Path(icon_line.split("=", 1)[1])
    assert icon_path.is_file()
    assert icon_path.suffix in {".png", ".svg"}
