from pathlib import Path

from easyamiga import desktop
from easyamiga.games import add_game, classify, list_configs
from easyamiga.models import get_model
from easyamiga.paths import Paths


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
    paths = Paths.resolve(tmp_path / "EasyAmiga")
    paths.ensure()

    adf = tmp_path / "Lemmings.adf"
    adf.write_bytes(b"\x00" * (880 * 1024))

    game = add_game(paths, adf, get_model("a500"), name="Lemmings")

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
    paths = Paths.resolve(tmp_path / "EasyAmiga")
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
    entry = desktop.render_desktop_entry("Turrican II!", "easyamiga run turrican", "easyamiga")
    assert "Name=Turrican II!" in entry
    assert desktop.desktop_file_path("Turrican II!").name == "easyamiga-game-turrican-ii.desktop"
