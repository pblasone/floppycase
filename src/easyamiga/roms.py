"""Kickstart ROM detection (including Amiga Forever encoded ROMs).

Amiberry identifies Kickstart ROMs by their CRC32 checksum regardless of
filename, so easyamiga does the same: hash every file in the ROM directory and
match it against a small database of well-known Kickstart images.

Amiga Forever distributes ROMs in Cloanto's *encoded* form (an ``AMIROMTYPE1``
header followed by the ROM XOR-scrambled with ``rom.key``). Amiberry cannot use
these directly, so easyamiga decodes them with ``rom.key`` (a simple, well-known
XOR transform) into plain ROM files that emulators recognise. When no key is
present the ROM is flagged as encrypted so the user gets a clear message instead
of a cryptic emulator crash.
"""

from __future__ import annotations

import hashlib
import zlib
from dataclasses import dataclass
from pathlib import Path

#: Sentinel understood by Amiberry: use the built-in AROS Kickstart replacement.
AROS = ":AROS"

#: Header on Cloanto/Amiga Forever encoded ROMs.
AMIROMTYPE1 = b"AMIROMTYPE1"
#: Legacy subfolder some older versions wrote decoded copies to (still ignored).
DECODED_DIRNAME = "easyamiga-decoded"
#: Suffix for the backup easyamiga keeps of an original encoded ROM before it
#: decodes it in place.
DECODED_BACKUP_SUFFIX = ".encoded"
#: Common names for the Amiga Forever decode key.
ROM_KEY_NAMES = {"rom.key"}
#: Files/dirs to ignore when scanning (Amiberry's own AROS + MT32 assets).
IGNORED_ROM_NAMES = {"aros-rom.bin", "aros-ext.bin"}
IGNORED_DIRNAMES = {DECODED_DIRNAME, "mt32-roms"}


def _skip(path: Path) -> bool:
    if any(part in IGNORED_DIRNAMES for part in path.parts):
        return True
    if path.name in IGNORED_ROM_NAMES:
        return True
    return path.name.endswith(DECODED_BACKUP_SUFFIX)


@dataclass(frozen=True)
class KnownRom:
    crc32: str  # lowercase hex, no prefix
    description: str
    model: str  # easyamiga model key this ROM suits best
    rom_id: str  # value for kickstart_rom_file_id


#: Well-known *decoded* Kickstart CRC32s (canonical WinUAE/Amiberry values).
KNOWN_ROMS: dict[str, KnownRom] = {
    "c4f0f55f": KnownRom("c4f0f55f", "Kickstart v1.3 r34.5 (A500)", "a500", "C4F0F55F,KS ROM v1.3 (A500)"),
    "a6ce1636": KnownRom("a6ce1636", "Kickstart v1.2 r33.180 (A500)", "a500", "A6CE1636,KS ROM v1.2 (A500)"),
    "c3bdb240": KnownRom("c3bdb240", "Kickstart v2.04 r37.175 (A500+)", "a500", "C3BDB240,KS ROM v2.04 (A500+)"),
    "43b0df7b": KnownRom("43b0df7b", "Kickstart v2.05 r37.350 (A600)", "a500", "43B0DF7B,KS ROM v2.05 (A600)"),
    "1483a091": KnownRom("1483a091", "Kickstart v3.1 r40.68 (A1200)", "a1200", "1483A091,KS ROM v3.1 (A1200)"),
    "6c9b07d2": KnownRom("6c9b07d2", "Kickstart v3.0 r39.106 (A1200)", "a1200", "6C9B07D2,KS ROM v3.0 (A1200)"),
    "a0d4f286": KnownRom("a0d4f286", "Kickstart v3.x r45.66 (A1200)", "a1200", "A0D4F286,KS ROM v3.x (A1200)"),
    "d6bae334": KnownRom("d6bae334", "Kickstart v3.1 r40.68 (A4000)", "a1200", "D6BAE334,KS ROM v3.1 (A4000)"),
}

#: CRC32s of the *encoded* Amiga Forever ROMs, so we can name them and pick a
#: model even before we have a key to decode them.
ENCODED_ROMS: dict[str, tuple[str, str]] = {
    "99d0d60f": ("a1200", "Kickstart 3.1 (A1200, Amiga Forever - encrypted)"),
    "2d878418": ("a1200", "Kickstart 3.X (A1200, Amiga Forever - encrypted)"),
}


@dataclass(frozen=True)
class DetectedRom:
    path: Path
    crc32: str
    known: KnownRom | None
    encoded: bool = False  # was an AMIROMTYPE1 (Amiga Forever) file
    has_key: bool = False  # a rom.key was available to decode it

    @property
    def is_known(self) -> bool:
        return self.known is not None

    @property
    def usable(self) -> bool:
        """True if an emulator can actually boot this ROM."""
        return (not self.encoded) or self.has_key

    @property
    def description(self) -> str:
        if self.encoded and not self.has_key:
            base = self.known.description if self.known else "Kickstart"
            return f"{base} - ENCRYPTED, needs rom.key"
        if self.known:
            return self.known.description
        return "Unknown ROM"


def crc32_of(path: Path) -> str:
    """Return the lowercase hex CRC32 of a file, streamed in chunks."""
    checksum = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            checksum = zlib.crc32(chunk, checksum)
    return f"{checksum & 0xFFFFFFFF:08x}"


def crc32_bytes(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"


def sha1_of(path: Path) -> str:
    """Return the lowercase hex SHA-1 of a file (used to match the WHDLoad DB)."""
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_like_rom(path: Path) -> bool:
    if not path.is_file():
        return False
    # Kickstart images are 256 KB / 512 KB / 1 MB. Filter out obvious noise.
    size = path.stat().st_size
    return 128 * 1024 <= size <= 4 * 1024 * 1024


def is_encoded(path: Path) -> bool:
    """True if the file is a Cloanto/Amiga Forever encoded ROM (AMIROMTYPE1)."""
    try:
        with path.open("rb") as handle:
            return handle.read(len(AMIROMTYPE1)) == AMIROMTYPE1
    except OSError:
        return False


def find_rom_key(roms_dir: Path) -> Path | None:
    if not roms_dir.exists():
        return None
    for path in roms_dir.rglob("*"):
        if DECODED_DIRNAME in path.parts:
            continue
        if path.is_file() and path.name.lower() in ROM_KEY_NAMES:
            return path
    return None


# (helpers _skip / ignore sets defined above are used by the scanners below)


def decode_encoded_bytes(encoded: bytes, key: bytes) -> bytes:
    """Decode Cloanto AMIROMTYPE1 payload (header already stripped) with a key.

    The transform is a simple repeating XOR of the payload against rom.key.
    """
    if not key:
        raise ValueError("empty rom.key")
    keylen = len(key)
    return bytes(b ^ key[i % keylen] for i, b in enumerate(encoded))


def decode_encoded_file(rom_path: Path, key_path: Path) -> bytes:
    data = rom_path.read_bytes()
    if data[: len(AMIROMTYPE1)] == AMIROMTYPE1:
        data = data[len(AMIROMTYPE1):]
    return decode_encoded_bytes(data, key_path.read_bytes())


def decode_in_place(roms_dir: Path) -> int:
    """Decode encoded Amiga Forever ROMs *in place* using ``rom.key``.

    The original encoded file is backed up alongside it as ``<name>.encoded``
    and the ROM at its original path is overwritten with the decoded bytes, so
    every emulator config that references the ROM by path gets a working ROM.
    Idempotent: an already-decoded (plain) ROM is left alone. Returns the number
    of ROMs decoded on this call.
    """
    if not roms_dir.exists():
        return 0
    key = find_rom_key(roms_dir)
    if key is None:
        return 0
    decoded_count = 0
    for rom in sorted(roms_dir.rglob("*")):
        if _skip(rom) or not _looks_like_rom(rom) or not is_encoded(rom):
            continue
        try:
            decoded = decode_encoded_file(rom, key)
        except (OSError, ValueError):
            continue
        backup = rom.with_name(rom.name + DECODED_BACKUP_SUFFIX)
        try:
            if not backup.exists():
                backup.write_bytes(rom.read_bytes())
            rom.write_bytes(decoded)
            decoded_count += 1
        except OSError:
            continue
    return decoded_count


def detect_roms(roms_dir: Path) -> list[DetectedRom]:
    """Scan ``roms_dir`` and return every candidate ROM, decoding encoded ones."""
    if not roms_dir.exists():
        return []
    decode_in_place(roms_dir)  # decode Amiga Forever ROMs in place (needs rom.key)
    detected: list[DetectedRom] = []
    for path in sorted(roms_dir.rglob("*")):
        if _skip(path) or not _looks_like_rom(path):
            continue
        crc = crc32_of(path)
        if is_encoded(path):
            # Still encoded => no key available to decode it.
            enc = ENCODED_ROMS.get(crc)
            known = KnownRom(crc, enc[1], enc[0], "") if enc else None
            detected.append(DetectedRom(path=path, crc32=crc, known=known, encoded=True, has_key=False))
        else:
            detected.append(DetectedRom(path=path, crc32=crc, known=KNOWN_ROMS.get(crc)))
    return detected


def default_model_key(detected: list[DetectedRom], fallback: str = "a500") -> str:
    """Best model to default to given the detected ROMs.

    If a known Kickstart is present, use the model it suits (e.g. a KS 3.1 A1200
    ROM -> ``a1200``) so the generated config matches the ROM's CPU requirement.
    """
    known = next((d for d in detected if d.known), None)
    return known.known.model if known else fallback


def pick_rom_for_model(detected: list[DetectedRom], model_key: str) -> DetectedRom | None:
    """Choose the best ROM for a model: prefer a usable known ROM for that exact
    model, then any usable known ROM, then any usable ROM, then anything."""
    usable = [d for d in detected if d.usable]
    pools = [
        [d for d in usable if d.known and d.known.model == model_key],
        [d for d in usable if d.known],
        usable,
        detected,
    ]
    for pool in pools:
        if pool:
            return pool[0]
    return None
