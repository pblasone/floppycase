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
  # Amiga framebuffer / manual-crop size seen by WHDLoad titles. Short RetroPlay
  # heights (e.g. 200) crop the picture; taller presets show more of the screen.
  "amiga_screen": "640x512",      # 640x512 | 720x568 | 720x284 | default | auto
  # Display alignment (``default`` = leave WHDLoad / Amiberry booter values)
  "screen_center_h": "default",   # default | none | simple | smart
  "screen_center_v": "default",
  "screen_offset_h": "default",   # default | pixel offset (integer string)
  "screen_offset_v": "default",
  # Video timing / viewport (fixes cropped tops on some titles)
  "video_standard": "default",    # default | pal | ntsc
  "line_mode": "default",         # default | single | double (scanline height)
  "vertical_offset": "default",   # legacy alias for screen_offset_v
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
AMIGA_SCREEN_CHOICES = ("640x512", "720x568", "720x284", "default", "auto")
VIDEO_STANDARD_CHOICES = ("default", "pal", "ntsc")
LINE_MODE_CHOICES = ("default", "single", "double")
CD32_PAD_CHOICES = ("default", "on", "off")
STOP_KEYPRESS_CHOICES = ("default", "off", "on")

# Amiga framebuffer sizes for the ``amiga_screen`` preset (not host window size).
_AMIGA_SCREEN_PRESETS = {
    "640x512": (640, 512),
    "720x568": (720, 568),
    "720x284": (720, 284),
}

#: PAL-ish base resolution used to compute integer window scales.
_BASE_W, _BASE_H = 720, 568

#: Host hotkeys we always pass to Amiberry so players can leave fullscreen /
#: release the mouse without hunting through Amiberry's own GUI.
QUIT_HOTKEY = "F10"
FULLSCREEN_TOGGLE_HOTKEY = "F11"
WINDOW_TITLE_HINT = "Ctrl+Alt: mouse back to Linux  |  F10: quit emulator  |  F11: fullscreen"


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


def _apply_amiga_screen(eff: dict, opts: dict[str, str]) -> None:
    """Override WHDLoad DB crop size so games are not clipped.

    Amiberry's WHDLoad Booter maps XML ``SCREEN_HEIGHT`` into
    ``amiberry.gfx_manual_crop_*``. Short heights (often ~200) cut off the top
    of many titles. Default ``640x512`` is a full double-line viewport that
    keeps more vertical content visible than the older 720×284 suggestion.
    """
    preset = eff.get("amiga_screen", "640x512")
    if preset in _AMIGA_SCREEN_PRESETS:
        width, height = _AMIGA_SCREEN_PRESETS[preset]
        opts["amiberry.gfx_auto_crop"] = "false"
        opts["amiberry.gfx_manual_crop"] = "true"
        opts["amiberry.gfx_manual_crop_width"] = str(width)
        opts["amiberry.gfx_manual_crop_height"] = str(height)
        # Smart centering pairs well with a full viewport; leave alone if the
        # user already chose an explicit center mode.
        if eff.get("screen_center_h", "default") == "default":
            opts["gfx_center_horizontal"] = "smart"
        if eff.get("screen_center_v", "default") == "default":
            opts["gfx_center_vertical"] = "smart"
    elif preset == "auto":
        opts["amiberry.gfx_auto_crop"] = "true"
        opts["amiberry.gfx_manual_crop"] = "false"


def _apply_int_opt(opts: dict[str, str], key: str, raw) -> None:
    if raw in (None, "", "default"):
        return
    try:
        opts[key] = str(int(str(raw).strip()))
    except ValueError:
        pass


def _apply_display_opts(eff: dict, opts: dict[str, str]) -> None:
    _apply_amiga_screen(eff, opts)

    h = eff.get("screen_center_h", "default")
    if h in ("none", "simple", "smart"):
        opts["gfx_center_horizontal"] = h
    v = eff.get("screen_center_v", "default")
    if v in ("none", "simple", "smart"):
        opts["gfx_center_vertical"] = v

    # WHDLoad Booter / Amiberry use these target offsets — NOT the WinUAE
    # ``gfx_center_*_position`` keys we previously passed (which were ignored).
    _apply_int_opt(opts, "amiberry.gfx_horizontal_offset", eff.get("screen_offset_h", "default"))
    offset_v = eff.get("screen_offset_v", "default")
    if offset_v in (None, "", "default"):
        offset_v = eff.get("vertical_offset", "default")
    _apply_int_opt(opts, "amiberry.gfx_vertical_offset", offset_v)

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
        # Amiberry .uae keys (not the old WinUAE-only ``gfx_fullscreen`` name).
        # ``fullwindow`` = borderless desktop fullscreen; preferred over exclusive
        # ``true`` which switches the monitor resolution.
        opts["gfx_fullscreen_amiga"] = "fullwindow"
        opts["gfx_fullscreen_picasso"] = "fullwindow"
    else:
        opts["gfx_fullscreen_amiga"] = "false"
        opts["gfx_fullscreen_picasso"] = "false"
        scale = str(eff.get("scale", "2x"))
        if scale in ("1x", "2x", "3x"):
            factor = int(scale[0])
            opts["gfx_width"] = str(_BASE_W * factor)
            opts["gfx_height"] = str(_BASE_H * factor)
            opts["amiberry.gfx_correct_aspect"] = "true"
    if eff.get("filter") == "crt":
        opts["amiberry.shader"] = "crt"
    _apply_display_opts(eff, opts)

    # Host escape hatches (Amiberry grabs the keyboard while the emu has focus,
    # which also swallows laptop volume keys until the mouse is released).
    # These are Amiberry *target* options and must use the ``amiberry.`` prefix
    # or ``-s`` silently ignores them (unknown config entry).
    opts["amiberry.ctrl_alt_release"] = "true"
    opts["amiberry.quit_amiberry"] = QUIT_HOTKEY
    opts["amiberry.fullscreen_toggle"] = FULLSCREEN_TOGGLE_HOTKEY
    opts["config_window_title"] = WINDOW_TITLE_HINT
    # WHDLoad's own quit (often F10) returns to Workbench; this closes Amiberry
    # immediately afterwards so you are not left at a Shell prompt.
    # Must be applied *before* ``--autoload`` (see amiberry.build_game_command).
    opts["whdload_quit_on_exit"] = "true"

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
