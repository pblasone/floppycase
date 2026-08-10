import struct
import zlib

from easyamiga.roms import crc32_of, detect_roms, pick_rom_for_model, KNOWN_ROMS


def _write_rom_with_crc(path, target_crc_hex, size=512 * 1024):
    """Write a file whose CRC32 equals target_crc_hex.

    We can't easily force an arbitrary CRC, so instead we verify crc32_of by
    computing the expected value directly.
    """
    data = b"\x00" * size
    path.write_bytes(data)
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"


def test_crc32_matches_zlib(tmp_path):
    p = tmp_path / "rom.bin"
    data = b"AMIGA" * 100000
    p.write_bytes(data)
    assert crc32_of(p) == f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"


def test_detect_and_identify_known_rom(tmp_path, monkeypatch):
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    rom = roms_dir / "kick.rom"
    expected = _write_rom_with_crc(rom, None)

    # Register a fake known ROM matching our generated file's CRC.
    from easyamiga.roms import KnownRom

    monkeypatch.setitem(KNOWN_ROMS, expected, KnownRom(expected, "Test KS (A1200)", "a1200", f"{expected.upper()},Test"))

    detected = detect_roms(roms_dir)
    assert len(detected) == 1
    assert detected[0].is_known
    assert detected[0].known.model == "a1200"


def test_pick_prefers_model_specific(tmp_path):
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    from easyamiga.roms import DetectedRom, KnownRom

    a500 = DetectedRom(roms_dir / "a.rom", "aaaa1111", KnownRom("aaaa1111", "A500", "a500", "x"))
    a1200 = DetectedRom(roms_dir / "b.rom", "bbbb2222", KnownRom("bbbb2222", "A1200", "a1200", "y"))
    assert pick_rom_for_model([a500, a1200], "a1200") is a1200
    assert pick_rom_for_model([a500, a1200], "a500") is a500


def test_detect_ignores_tiny_files(tmp_path):
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    (roms_dir / "note.txt").write_text("not a rom")
    assert detect_roms(roms_dir) == []
