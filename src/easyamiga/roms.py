"""Kickstart ROM detection.

Amiberry identifies Kickstart ROMs by their CRC32 checksum regardless of
filename, so easyamiga does the same: hash every file in the ROM directory and
match it against a small database of well-known Kickstart images. This lets us
auto-select the best Amiga model for a given ROM, or fall back to the built-in
AROS replacement ROM when no real Kickstart is present.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from pathlib import Path

#: Sentinel understood by Amiberry: use the built-in AROS Kickstart replacement.
AROS = ":AROS"


@dataclass(frozen=True)
class KnownRom:
    crc32: str  # lowercase hex, no prefix
    description: str
    model: str  # easyamiga model key this ROM suits best
    rom_id: str  # value for kickstart_rom_file_id


#: A small, well-known subset. CRC32 values are the canonical ones published in
#: the Amiberry / WinUAE ROM database.
KNOWN_ROMS: dict[str, KnownRom] = {
    "c4f0f55f": KnownRom("c4f0f55f", "Kickstart v1.3 r34.5 (A500)", "a500", "C4F0F55F,KS ROM v1.3 (A500)"),
    "a6ce1636": KnownRom("a6ce1636", "Kickstart v1.2 r33.180 (A500)", "a500", "A6CE1636,KS ROM v1.2 (A500)"),
    "c3bdb240": KnownRom("c3bdb240", "Kickstart v2.04 r37.175 (A500+)", "a500", "C3BDB240,KS ROM v2.04 (A500+)"),
    "43b0df7b": KnownRom("43b0df7b", "Kickstart v2.05 r37.350 (A600)", "a500", "43B0DF7B,KS ROM v2.05 (A600)"),
    "1483a091": KnownRom("1483a091", "Kickstart v3.1 r40.68 (A1200)", "a1200", "1483A091,KS ROM v3.1 (A1200)"),
    "6c9b07d2": KnownRom("6c9b07d2", "Kickstart v3.0 r39.106 (A1200)", "a1200", "6C9B07D2,KS ROM v3.0 (A1200)"),
}


@dataclass(frozen=True)
class DetectedRom:
    path: Path
    crc32: str
    known: KnownRom | None

    @property
    def description(self) -> str:
        return self.known.description if self.known else "Unknown ROM"

    @property
    def is_known(self) -> bool:
        return self.known is not None


def crc32_of(path: Path) -> str:
    """Return the lowercase hex CRC32 of a file, streamed in chunks."""
    checksum = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            checksum = zlib.crc32(chunk, checksum)
    return f"{checksum & 0xFFFFFFFF:08x}"


def _looks_like_rom(path: Path) -> bool:
    if not path.is_file():
        return False
    # Kickstart images are 256 KB / 512 KB / 1 MB. Filter out obvious noise.
    size = path.stat().st_size
    return 128 * 1024 <= size <= 4 * 1024 * 1024


def detect_roms(roms_dir: Path) -> list[DetectedRom]:
    """Scan ``roms_dir`` recursively and return every candidate ROM found."""
    if not roms_dir.exists():
        return []
    detected: list[DetectedRom] = []
    for path in sorted(roms_dir.rglob("*")):
        if not _looks_like_rom(path):
            continue
        crc = crc32_of(path)
        detected.append(DetectedRom(path=path, crc32=crc, known=KNOWN_ROMS.get(crc)))
    return detected


def pick_rom_for_model(detected: list[DetectedRom], model_key: str) -> DetectedRom | None:
    """Choose the best ROM for a model: prefer a known ROM for that exact model,
    then any known ROM, then any ROM at all."""
    known_for_model = [d for d in detected if d.known and d.known.model == model_key]
    if known_for_model:
        return known_for_model[0]
    known_any = [d for d in detected if d.known]
    if known_any:
        return known_any[0]
    return detected[0] if detected else None
