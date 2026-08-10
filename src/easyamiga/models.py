"""Amiga hardware model definitions.

Each model captures the settings easyamiga needs to render an Amiberry ``.uae``
configuration: chipset, CPU, and memory. Fast RAM defaults to the maximum amount
commonly recommended for that machine (8 MB of Zorro-II autoconfig Fast RAM),
which is what most WHDLoad games expect.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AmigaModel:
    key: str
    name: str
    chipset: str  # ocs / ecs / aga
    chipset_compatible: str  # A500 / A1200 (Amiberry preset name)
    cpu_model: int  # 68000 / 68020 / ...
    cpu_speed: str  # "real" (accurate) or "max" (fastest)
    cpu_24bit: bool  # 24-bit address bus (68000 / 68EC020)
    chipmem_size: int  # in 512 KB units (1 = 512 KB, 2 = 1 MB, 4 = 2 MB)
    bogomem_size: int  # "slow" RAM, in 256 KB units (2 = 512 KB)
    fastmem_mb: int  # Zorro-II Fast RAM in MB (max recommended for the model)

    @property
    def chipmem_kb(self) -> int:
        return self.chipmem_size * 512

    @property
    def bogomem_kb(self) -> int:
        return self.bogomem_size * 256


#: Supported models. Kept intentionally small (A500 + A1200) for the first pass.
MODELS: dict[str, AmigaModel] = {
    "a500": AmigaModel(
        key="a500",
        name="Amiga 500",
        chipset="ocs",
        chipset_compatible="A500",
        cpu_model=68000,
        cpu_speed="real",
        cpu_24bit=True,
        chipmem_size=1,  # 512 KB chip
        bogomem_size=2,  # 512 KB slow
        fastmem_mb=8,  # max recommended Fast RAM
    ),
    "a1200": AmigaModel(
        key="a1200",
        name="Amiga 1200",
        chipset="aga",
        chipset_compatible="A1200",
        cpu_model=68020,
        cpu_speed="max",
        cpu_24bit=True,  # A1200 ships a 68EC020 (24-bit)
        chipmem_size=4,  # 2 MB chip
        bogomem_size=0,
        fastmem_mb=8,  # max recommended Fast RAM
    ),
}

DEFAULT_MODEL = "a500"


def get_model(key: str) -> AmigaModel:
    normalized = key.strip().lower()
    if normalized not in MODELS:
        valid = ", ".join(sorted(MODELS))
        raise KeyError(f"Unknown Amiga model {key!r}. Choose one of: {valid}")
    return MODELS[normalized]
