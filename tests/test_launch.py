import pytest

from easyamiga import amiberry
from easyamiga.config_gen import ConfigOptions, read_meta, render_config, write_config
from easyamiga.models import get_model
from easyamiga.paths import Paths
from easyamiga.roms import DetectedRom, KNOWN_ROMS, default_model_key

FAKE_EXE = "/usr/bin/amiberry"


def test_default_model_from_rom():
    a1200_rom = DetectedRom(path=None, crc32="1483a091", known=KNOWN_ROMS["1483a091"])
    a500_rom = DetectedRom(path=None, crc32="c4f0f55f", known=KNOWN_ROMS["c4f0f55f"])
    assert default_model_key([a1200_rom]) == "a1200"
    assert default_model_key([a500_rom]) == "a500"
    # No known ROM -> fallback.
    assert default_model_key([]) == "a500"
    assert default_model_key([], fallback="a1200") == "a1200"


def test_config_records_launch_metadata(tmp_path):
    paths = Paths.resolve(tmp_path)
    paths.ensure()
    game = paths.games / "Turrican.lha"
    game.write_bytes(b"x")
    opts = ConfigOptions(
        model=get_model("a1200"), paths=paths, rom=None,
        source=game, kind="whdload", mount_games=True,
    )
    cfg = write_config(opts, "Turrican")
    meta = read_meta(cfg)
    assert meta["source"] == str(game)
    assert meta["kind"] == "whdload"
    assert meta["model"] == "a1200"


def test_adf_config_has_no_hd_mount(tmp_path):
    paths = Paths.resolve(tmp_path)
    opts = ConfigOptions(
        model=get_model("a500"), paths=paths, rom=None,
        floppy=paths.games / "Game.adf", kind="adf", mount_games=False,
    )
    text = render_config(opts)
    assert "uaehf0" not in text
    assert "floppy0=" in text


def test_build_game_command_whdload_uses_autoload(tmp_path):
    lha = tmp_path / "SuperFrog.lha"
    lha.write_bytes(b"x")
    cmd = amiberry.build_game_command(lha, kind="whdload", amiberry=FAKE_EXE)
    assert cmd[0] == FAKE_EXE
    assert "--autoload" in cmd
    assert str(lha) in cmd


def test_build_game_command_adf_boots_directly(tmp_path):
    adf = tmp_path / "Lemmings.adf"
    adf.write_bytes(b"x")
    cmd = amiberry.build_game_command(adf, kind="adf", amiberry=FAKE_EXE, rescan=False)
    assert "--autoload" not in cmd
    assert cmd[-1] == str(adf)


def test_build_game_command_folder_without_lha_raises(tmp_path):
    folder = tmp_path / "SomeGame"
    folder.mkdir()
    (folder / "readme.txt").write_text("no game here")
    with pytest.raises(FileNotFoundError):
        amiberry.build_game_command(folder, kind="whdload", amiberry=FAKE_EXE)


def test_build_game_command_folder_with_lha_autoloads(tmp_path):
    folder = tmp_path / "SomeGame"
    (folder / "inner").mkdir(parents=True)
    inner_lha = folder / "inner" / "Game.lha"
    inner_lha.write_bytes(b"x")
    cmd = amiberry.build_game_command(folder, kind="whdload", amiberry=FAKE_EXE)
    assert "--autoload" in cmd
    assert str(inner_lha) in cmd
