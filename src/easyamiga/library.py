"""Per-game library: display names, user notes, and launch settings.

easyamiga keeps a small JSON "library" (``~/EasyAmiga/library.json``) with global
default settings plus per-game overrides and free-text notes. Settings are turned
into Amiberry command-line options (``-s key=value`` and ``-J``) at launch time,
so a game can be tuned without hand-editing `.uae` files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .paths import Paths

LIBRARY_FILE = "library.json"

#: Global default launch settings (also the shape of a per-game override).
DEFAULT_SETTINGS: dict = {
    "controls": "keyboard-arrows",  # keyboard-arrows | keyboard-numpad | gamepad
    "fullscreen": False,
    "scale": "2x",                  # 1x | 2x | 3x
    "filter": "none",               # none | crt
}

#: PAL-ish base resolution used to compute integer window scales.
_BASE_W, _BASE_H = 720, 568


def _path(paths: Paths) -> Path:
    return paths.base / LIBRARY_FILE


def load(paths: Paths) -> dict:
    path = _path(paths)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data.setdefault("defaults", {})
            data.setdefault("games", {})
            return data
        except (OSError, ValueError):
            pass
    return {"defaults": {}, "games": {}}


def save(paths: Paths, data: dict) -> None:
    paths.base.mkdir(parents=True, exist_ok=True)
    _path(paths).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def get_defaults(paths: Paths) -> dict:
    return {**DEFAULT_SETTINGS, **load(paths).get("defaults", {})}


def set_defaults(paths: Paths, values: dict) -> None:
    data = load(paths)
    data["defaults"] = {**data.get("defaults", {}), **values}
    save(paths, data)


def get_game(paths: Paths, key: str) -> dict:
    return dict(load(paths).get("games", {}).get(key, {}))


def set_game(paths: Paths, key: str, values: dict) -> None:
    data = load(paths)
    games = data.setdefault("games", {})
    games[key] = {**games.get(key, {}), **values}
    save(paths, data)


def effective(paths: Paths, key: str) -> dict:
    """Global defaults merged with a game's overrides (only for setting keys)."""
    eff = get_defaults(paths)
    game = get_game(paths, key)
    for field in DEFAULT_SETTINGS:
        value = game.get(field)
        if value not in (None, "", "default"):
            eff[field] = value
    return eff


# --- display names -------------------------------------------------------------
def prettify(stem: str) -> str:
    """Turn a RetroPlay-style filename stem into a friendlier title.

    ``DuckTales_v1.1_0299`` -> ``DuckTales``; underscores become spaces.
    """
    s = re.sub(r"_v[0-9].*$", "", stem)  # drop version/hash suffix
    s = s.replace("_", " ").strip()
    return s or stem


def title_for(stem: str, override_name: str | None, db_by_name: dict | None) -> str:
    """Best display title: explicit override, then DB name, then prettified stem."""
    if override_name:
        return override_name
    if db_by_name:
        entry = db_by_name.get(stem.lower())
        if entry and entry.get("name"):
            return entry["name"]
    return prettify(stem)


# --- settings -> Amiberry launch options --------------------------------------
def launch_args(eff: dict) -> tuple[str | None, dict[str, str]]:
    """Return (joyports for ``-J``, {config option: value} for ``-s``)."""
    joy = {
        "keyboard-arrows": "Md",  # port0=mouse, port1=keyboard layout D (cursor+LCtrl)
        "keyboard-numpad": "Ma",  # port1=keyboard layout A (numpad)
        "gamepad": None,          # leave Amiberry's own port setup (use detected pad)
    }.get(eff.get("controls", "keyboard-arrows"), "Md")

    opts: dict[str, str] = {}
    if eff.get("fullscreen"):
        opts["gfx_fullscreen"] = "fullwindow"
    else:
        scale = str(eff.get("scale", "2x"))
        if scale in ("1x", "2x", "3x"):
            factor = int(scale[0])
            opts["gfx_width"] = str(_BASE_W * factor)
            opts["gfx_height"] = str(_BASE_H * factor)
            opts["gfx_correct_aspect"] = "true"
    if eff.get("filter") == "crt":
        opts["shader"] = "crt"
    return joy, opts
