import pytest

from floppycase import amiberry
from floppycase.config_gen import ConfigOptions, read_meta, render_config, write_config
from floppycase.models import get_model
from floppycase.paths import Paths
from floppycase.roms import DetectedRom, KNOWN_ROMS, default_model_key

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
    assert "; floppycase_source=" in cfg.read_text()


def test_read_meta_accepts_legacy_easyamiga_prefix(tmp_path):
    cfg = tmp_path / "legacy.uae"
    cfg.write_text(
        "; easyamiga_source=/games/Old.lha\n"
        "; easyamiga_kind=whdload\n"
        "; easyamiga_model=a500\n",
        encoding="utf-8",
    )
    meta = read_meta(cfg)
    assert meta == {
        "source": "/games/Old.lha",
        "kind": "whdload",
        "model": "a500",
    }


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


def test_default_joyports_keyboard(monkeypatch):
    monkeypatch.delenv("FLOPPYCASE_JOYPORTS", raising=False)
    assert amiberry.default_joyports() == "Md"
    monkeypatch.setenv("FLOPPYCASE_JOYPORTS", "off")
    assert amiberry.default_joyports() is None
    monkeypatch.setenv("FLOPPYCASE_JOYPORTS", "01")
    assert amiberry.default_joyports() == "01"


def test_build_game_command_adds_joyports(tmp_path):
    lha = tmp_path / "Game.lha"
    lha.write_bytes(b"x")
    cmd = amiberry.build_game_command(lha, kind="whdload", amiberry=FAKE_EXE, joyports="Md")
    assert cmd[-2:] == ["-J", "Md"]


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


def test_clear_game_config_removes_cached_configs(tmp_path, monkeypatch):
    cfgdir = tmp_path / "Configurations"
    abdir = tmp_path / "Autoboots"
    cfgdir.mkdir()
    abdir.mkdir()
    monkeypatch.setattr(amiberry, "config_path", lambda: cfgdir)
    monkeypatch.setattr(amiberry, "autoboots_path", lambda: abdir)

    (cfgdir / "WormsDC_AGA.uae").write_text("stale")
    (abdir / "WormsDC_AGA.uae").write_text("stale")
    (cfgdir / "Other.uae").write_text("keep")

    removed = amiberry.clear_game_config(tmp_path / "WormsDC_AGA.lha")
    assert len(removed) == 2
    assert not (cfgdir / "WormsDC_AGA.uae").exists()
    assert not (abdir / "WormsDC_AGA.uae").exists()
    assert (cfgdir / "Other.uae").exists()


def test_effective_roms_dir_prefers_amiberry(tmp_path, monkeypatch):
    from floppycase import install
    from floppycase.paths import Paths

    paths = Paths.resolve(tmp_path / "FloppyCase")
    amiga_dir = tmp_path / "Amiberry" / "ROMs"

    monkeypatch.setattr(install.amiberry, "is_installed", lambda: False)
    assert install.effective_roms_dir(paths) == paths.roms

    monkeypatch.setattr(install.amiberry, "is_installed", lambda: True)
    monkeypatch.setattr(install.amiberry, "rom_path", lambda: amiga_dir)
    assert install.effective_roms_dir(paths) == amiga_dir


def test_sha1_of_matches_hashlib(tmp_path):
    import hashlib

    from floppycase.roms import sha1_of

    p = tmp_path / "x.lha"
    data = b"hello whdload" * 1000
    p.write_bytes(data)
    assert sha1_of(p) == hashlib.sha1(data).hexdigest()


def test_load_whdload_db_indexes(tmp_path, monkeypatch):
    import json

    from floppycase import install

    gd = tmp_path / "WHDBoot" / "game-data"
    gd.mkdir(parents=True)
    (gd / "whdload_db.json").write_text(
        json.dumps(
            {
                "games": [
                    {"filename": "Firepower_v1.0_0061", "sha1": "aa11", "name": "Firepower"},
                    {"filename": "DuckTales_v1.1_0299", "sha1": "bb22", "name": "DuckTales"},
                ]
            }
        )
    )
    monkeypatch.setattr(install.amiberry, "whdboot_path", lambda: tmp_path / "WHDBoot")
    by_sha1, by_name = install.load_whdload_db()
    assert by_sha1["aa11"]["name"] == "Firepower"
    assert by_name["ducktales_v1.1_0299"]["name"] == "DuckTales"


def test_migrate_legacy_roms_copies_once(tmp_path):
    from floppycase import install
    from floppycase.paths import Paths

    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()
    paths.roms.mkdir(parents=True, exist_ok=True)
    (paths.roms / "kick.rom").write_bytes(b"\x00" * (512 * 1024))
    (paths.roms / "rom.key").write_bytes(b"key")
    dest = tmp_path / "Amiberry" / "ROMs"

    moved = install.migrate_legacy_roms(paths, dest)
    assert moved == 2
    assert (dest / "kick.rom").exists()
    assert (dest / "rom.key").exists()
    # Idempotent: nothing new copied on a second run.
    assert install.migrate_legacy_roms(paths, dest) == 0
