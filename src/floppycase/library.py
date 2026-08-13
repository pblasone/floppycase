"""Per-game library: display names, user notes, and launch settings.

FloppyCase keeps a small JSON "library" (``~/FloppyCase/library.json``) with global
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
  "controls": "keyboard-arrows",  # see CONTROL_LAYOUTS
  "fullscreen": False,
  "scale": "2x",                  # 1x | 2x | 3x
  "filter": "none",               # none | crt
  # Display alignment (``default`` = leave WHDLoad / Amiberry booter values)
  "screen_center_h": "default",   # default | none | simple | smart
  "screen_center_v": "default",
  "screen_offset_h": "default",   # default | pixel offset (integer string)
  "screen_offset_v": "default",
  # Video timing / viewport (fixes cropped tops on some titles)
  "video_standard": "default",    # default | pal | ntsc
  "line_mode": "default",         # default | single | double (scanline height)
  "vertical_offset": "default",   # default | pixels (amiberry.vertical_offset)
  # Input fine-tuning (mirrors Amiberry input / WHDLoad options)
  "cd32_pad": "default",          # default | on | off
  "stop_keypresses": "default",   # default | off | on
}

#: Amiberry keyboard-as-joystick layouts (``joyportN=kbd*``).
CONTROL_LAYOUTS: dict[str, str] = {
    "keyboard-arrows": "kbd4",         # Keyrah: cursor + Space / RAlt fire
    "keyboard-arrows-lctrl": "kbd9",   # Layout D: cursor + LCtrl/LAlt fire
    "keyboard-arrows-rctrl": "kbd2",   # Layout B: cursor + RCtrl/RAlt fire
    "keyboard-wasd": "kbd3",           # Layout C: WASAD + LAlt fire
    "keyboard-numpad": "kbd1",         # Layout A: numpad + 0/5 fire
}

SCREEN_CENTER_CHOICES = ("default", "none", "simple", "smart")
VIDEO_STANDARD_CHOICES = ("default", "pal", "ntsc")
LINE_MODE_CHOICES = ("default", "single", "double")
CD32_PAD_CHOICES = ("default", "on", "off")
STOP_KEYPRESS_CHOICES = ("default", "off", "on")

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


def field_inherited(game: dict, field: str) -> bool:
    """True when a per-game field defers to global defaults."""
    return game.get(field) in (None, "", "default")


def fullscreen_inherited(game: dict) -> bool:
    return game.get("fullscreen_choice", "default") in (None, "", "default")


def display_value(game: dict, defaults: dict, field: str) -> str:
    """UI value for a setting: global default when inherited, else the override."""
    if field == "fullscreen":
        if fullscreen_inherited(game):
            return "on" if defaults.get("fullscreen") else "off"
        return "on" if game.get("fullscreen") is True else "off"
    if field_inherited(game, field):
        val = defaults.get(field, DEFAULT_SETTINGS.get(field, ""))
        return str(val)
    return str(game.get(field, ""))


def store_if_matches_global(current: str, defaults: dict, field: str) -> str:
    """Store ``default`` when ``current`` matches the global default value."""
    stripped = str(current).strip()
    if not stripped:
        return "default"
    global_val = defaults.get(field, DEFAULT_SETTINGS.get(field, ""))
    if stripped == str(global_val).strip():
        return "default"
    return stripped


def display_entry_value(game: dict, defaults: dict, field: str) -> str:
    """Text for numeric offset fields: blank when unset or inheriting ``default``."""
    if field_inherited(game, field):
        global_val = defaults.get(field, DEFAULT_SETTINGS.get(field, ""))
        if str(global_val).strip() in ("", "default"):
            return ""
        return str(global_val).strip()
    raw = game.get(field, "")
    if str(raw).strip() in ("", "default"):
        return ""
    return str(raw).strip()


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


def _apply_display_opts(eff: dict, opts: dict[str, str]) -> None:
    h = eff.get("screen_center_h", "default")
    if h in ("none", "simple", "smart"):
        opts["gfx_center_horizontal"] = h
    v = eff.get("screen_center_v", "default")
    if v in ("none", "simple", "smart"):
        opts["gfx_center_vertical"] = v
    for field, key in (
        ("screen_offset_h", "gfx_center_horizontal_position"),
        ("screen_offset_v", "gfx_center_vertical_position"),
    ):
        raw = eff.get(field, "default")
        if raw not in (None, "", "default"):
            try:
                opts[key] = str(int(str(raw).strip()))
            except ValueError:
                pass

    vs = eff.get("video_standard", "default")
    if vs == "pal":
        opts["ntsc"] = "false"
    elif vs == "ntsc":
        opts["ntsc"] = "true"

    lm = eff.get("line_mode", "default")
    if lm == "single":
        opts["gfx_linemode"] = "none"
    elif lm == "double":
        opts["gfx_linemode"] = "double"

    raw_vo = eff.get("vertical_offset", "default")
    if raw_vo not in (None, "", "default"):
        try:
            opts["amiberry.vertical_offset"] = str(int(str(raw_vo).strip()))
        except ValueError:
            pass


def _want_cd32_pad(eff: dict, hardware: dict | None) -> bool:
    mode = eff.get("cd32_pad", "default")
    if mode == "on":
        return True
    if mode == "off":
        return False
    return needs_cd32_joystick_mode(hardware)


def _stop_keypresses_value(eff: dict) -> str:
    val = eff.get("stop_keypresses", "default")
    if val == "on":
        return "yes"
    return "no"  # default and off both allow keys through to the Amiga


def launch_args(
    eff: dict,
    hardware: dict | None = None,
) -> tuple[None, dict[str, str]]:
    """Return launch options for ``-s key=value`` (joyports tuple is always ``None``).

    Keyboard controls are applied via ``joyport0`` / ``joyport1`` *after* WHDLoad
    auto-boot so they override the booter's default ``joy1`` assignment. CD32
    titles also get ``joyport1mode=cd32joy`` unless overridden in library settings.
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
    _apply_display_opts(eff, opts)

    controls = eff.get("controls", "keyboard-arrows")
    if controls != "gamepad":
        kbd = CONTROL_LAYOUTS.get(controls, CONTROL_LAYOUTS["keyboard-arrows"])
        opts["inactive_pause"] = "false"
        opts["active_not_captured_pause"] = "false"
        opts["input_keyboard_as_joystick_stop_keypresses"] = _stop_keypresses_value(eff)
        # Joyport overrides last so they win over any WHDLoad cached ``.uae`` config.
        opts["joyport0"] = "mouse"
        opts["joyport1"] = kbd
        opts["joyport1keyboardoverride"] = "yes"
        if _want_cd32_pad(eff, hardware):
            opts["joyport1mode"] = "cd32joy"
        elif eff.get("cd32_pad") == "off":
            opts["joyport1mode"] = "djoy"
    return None, opts
