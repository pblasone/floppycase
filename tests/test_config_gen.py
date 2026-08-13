from floppycase.config_gen import ConfigOptions, render_config, write_config
from floppycase.models import get_model
from floppycase.paths import Paths
from floppycase.roms import DetectedRom, KNOWN_ROMS


def test_a500_aros_config(tmp_path):
    paths = Paths.resolve(tmp_path)
    paths.ensure()
    opts = ConfigOptions(model=get_model("a500"), paths=paths, rom=None)
    text = render_config(opts)

    assert "chipset=ocs" in text
    assert "cpu_model=68000" in text
    assert "fastmem_size=8" in text
    assert "chipmem_size=1" in text
    # No ROM -> built-in AROS
    assert "kickstart_rom_file=:AROS" in text
    # Games directory mounted read/write (never auto-boots)
    assert f"uaehf0=dir,rw,DH0:Games:{paths.games},-128" in text
    # Boots straight into emulation by default
    assert "use_gui=no" in text
    # Keep running when the window loses focus (better for click-to-play)
    assert "inactive_pause=false" in text


def test_a1200_config_uses_aga_and_020(tmp_path):
    paths = Paths.resolve(tmp_path)
    opts = ConfigOptions(model=get_model("a1200"), paths=paths, rom=None)
    text = render_config(opts)
    assert "chipset=aga" in text
    assert "cpu_model=68020" in text
    assert "chipmem_size=4" in text
    assert "fastmem_size=8" in text


def test_config_with_known_rom(tmp_path):
    paths = Paths.resolve(tmp_path)
    rom = DetectedRom(path=tmp_path / "kick.rom", crc32="1483a091", known=KNOWN_ROMS["1483a091"])
    opts = ConfigOptions(model=get_model("a1200"), paths=paths, rom=rom)
    text = render_config(opts)
    assert "kickstart_rom_file=" in text
    assert "1483A091" in text
    assert ":AROS" not in text


def test_write_config_creates_file(tmp_path):
    paths = Paths.resolve(tmp_path)
    opts = ConfigOptions(model=get_model("a500"), paths=paths, rom=None)
    written = write_config(opts, "test")
    assert written.exists()
    assert written.name == "test.uae"
