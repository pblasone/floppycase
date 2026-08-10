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


def _encode(plaintext: bytes, key: bytes) -> bytes:
    from easyamiga.roms import AMIROMTYPE1

    body = bytes(b ^ key[i % len(key)] for i, b in enumerate(plaintext))
    return AMIROMTYPE1 + body


def test_encoded_rom_without_key_is_flagged(tmp_path):
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    plaintext = (b"KICK" * (512 * 1024 // 4))
    (roms_dir / "amiga-os-310-a1200.rom").write_bytes(_encode(plaintext, b"secret"))

    detected = detect_roms(roms_dir)
    assert len(detected) == 1
    rom = detected[0]
    assert rom.encoded and not rom.has_key
    assert not rom.usable
    assert "ENCRYPTED" in rom.description.upper()


def test_encoded_rom_is_decoded_with_key(tmp_path):
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    key = b"\x11\x22\x33\x44\x55"
    plaintext = bytes((i * 7) & 0xFF for i in range(512 * 1024))
    (roms_dir / "amiga-os-310-a1200.rom").write_bytes(_encode(plaintext, key))
    (roms_dir / "rom.key").write_bytes(key)

    detected = detect_roms(roms_dir)
    assert len(detected) == 1
    rom = detected[0]
    assert rom.encoded and rom.has_key and rom.usable
    # Decoded content identity must match the original plaintext's CRC.
    assert rom.crc32 == crc32_bytes_of(plaintext)
    # The usable path points at the decoded copy, whose bytes equal the plaintext.
    assert rom.path.read_bytes() == plaintext


def crc32_bytes_of(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"
