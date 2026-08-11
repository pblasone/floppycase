"""Per-game library: display names, user notes, and launch settings.

easyamiga keeps a small JSON "library" (``~/EasyAmiga/library.json``) with global
default settings plus per-game overrides and free-text notes. Settings are turned
into Amiberry command-line options (``-s key=value``) at launch time,
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
#: Amiberry ``joyportN=kbd*`` assignments (see Amiberry Input panel / cfgfile).
_KEYBOARD_JOYPORT = {
    # Keyrah layout: cursor keys + Space/Right Alt fire (matches many WHDLoad packs).
    "keyboard-arrows": "kbd4",
    # Layout A: numpad directions + 0/5 fire.
    "keyboard-numpad": "kbd1",
}

#: Applied for keyboard play so focus changes and key-as-joystick do not block input.
_KEYBOARD_HOST_OPTS = {
    "inactive_pause": "false",
    "active_not_captured_pause": "false",
    "input_keyboard_as_joystick_stop_keypresses": "no",
}


def hardware_from_db(stem: str, db_by_name: dict | None) -> dict | None:
    """Return WHDLoad ``hardware`` metadata for a game archive stem, if known."""
    if not db_by_name:
        return None
    entry = db_by_name.get(stem.lower())
    if not entry:
        return None
    hardware = entry.get("hardware")
    return hardware if isinstance(hardware, dict) else None


def needs_cd32_joystick_mode(hardware: dict | None) -> bool:
    """True when the WHDLoad database says the game expects a CD32 pad."""
    if not hardware:
        return False
    return hardware.get("port0") == "cd32" or hardware.get("port1") == "cd32"


def launch_args(
    eff: dict,
    hardware: dict | None = None,
) -> tuple[None, dict[str, str]]:
    """Return launch options for ``-s key=value`` (joyports tuple is always ``None``).

  Keyboard controls are applied via ``joyport0`` / ``joyport1`` *after* WHDLoad
  auto-boot so they override the booter's default ``joy1`` assignment. CD32
  titles also get ``joyport1mode=cd32joy`` so Amiberry maps keys to CD32
  buttons (red/green/…) instead of a plain joystick fire bit.
    """
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

    controls = eff.get("controls", "keyboard-arrows")
    if controls == "gamepad":
        return None, opts

    kbd = _KEYBOARD_JOYPORT.get(controls, _KEYBOARD_JOYPORT["keyboard-arrows"])
    opts.update(_KEYBOARD_HOST_OPTS)
    # Joyport overrides last so they win over any WHDLoad cached ``.uae`` config.
    opts["joyport0"] = "mouse"
    opts["joyport1"] = kbd
    opts["joyport1keyboardoverride"] = "yes"
    if needs_cd32_joystick_mode(hardware):
        opts["joyport1mode"] = "cd32joy"
    return None, opts
