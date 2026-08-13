from floppycase import library
from floppycase.paths import Paths


def test_prettify_and_title():
    assert library.prettify("DuckTales_v1.1_0299") == "DuckTales"
    assert library.prettify("Sensible_Soccer") == "Sensible Soccer"
    db = {"ducktales_v1.1_0299": {"name": "DuckTales - The Quest for Gold"}}
    # DB name wins over prettified filename; explicit override wins over both.
    assert library.title_for("DuckTales_v1.1_0299", None, db) == "DuckTales - The Quest for Gold"
    assert library.title_for("DuckTales_v1.1_0299", "My Ducks", db) == "My Ducks"
    assert library.title_for("Unknown_v2.0_abcd", None, {}) == "Unknown"


def test_defaults_and_overrides_roundtrip(tmp_path):
    paths = Paths.resolve(tmp_path)
    paths.ensure()
    # Defaults start from DEFAULT_SETTINGS.
    assert library.get_defaults(paths)["controls"] == "keyboard-arrows"
    library.set_defaults(paths, {"fullscreen": True, "scale": "3x"})
    d = library.get_defaults(paths)
    assert d["fullscreen"] is True and d["scale"] == "3x"

    # Per-game override + notes persist and merge over defaults.
    library.set_game(paths, "Turrican", {"controls": "gamepad", "notes": "needs 2 buttons"})
    eff = library.effective(paths, "Turrican")
    assert eff["controls"] == "gamepad"     # overridden
    assert eff["scale"] == "3x"             # inherited from defaults
    assert library.get_game(paths, "Turrican")["notes"] == "needs 2 buttons"

    # "default" sentinel defers to the global default.
    library.set_game(paths, "Turrican", {"controls": "default"})
    assert library.effective(paths, "Turrican")["controls"] == "keyboard-arrows"


def test_launch_args_mapping(tmp_path):
    joy, opts = library.launch_args(
        {"controls": "keyboard-arrows", "fullscreen": False, "scale": "2x", "filter": "none"}
    )
    assert joy is None
    assert opts["joyport0"] == "mouse"
    assert opts["joyport1"] == "kbd4"
    assert opts["joyport1keyboardoverride"] == "yes"
    assert opts["input_keyboard_as_joystick_stop_keypresses"] == "no"
    assert opts["gfx_width"] == "1440" and opts["gfx_height"] == "1136"
    assert opts["gfx_fullscreen_amiga"] == "false"
    assert opts["gfx_fullscreen_picasso"] == "false"
    assert opts["amiberry.ctrl_alt_release"] == "true"
    assert opts["amiberry.quit_amiberry"] == library.QUIT_HOTKEY
    assert opts["amiberry.fullscreen_toggle"] == library.FULLSCREEN_TOGGLE_HOTKEY
    assert opts["whdload_quit_on_exit"] == "true"
    assert "Ctrl+Alt" in opts["config_window_title"]
    assert "joyport1mode" not in opts

    _, opts = library.launch_args(
        {"controls": "keyboard-numpad", "fullscreen": False, "scale": "2x", "filter": "none"}
    )
    assert opts["joyport1"] == "kbd1"

    _, opts = library.launch_args(
        {"controls": "keyboard-arrows", "fullscreen": False, "scale": "2x", "filter": "none"},
        hardware={"port0": "cd32", "port1": "cd32"},
    )
    assert opts["joyport1mode"] == "cd32joy"

    _, opts = library.launch_args(
        {
            "controls": "keyboard-arrows",
            "fullscreen": False,
            "scale": "2x",
            "filter": "none",
            "cd32_pad": "off",
        },
        hardware={"port0": "cd32", "port1": "cd32"},
    )
    assert opts["joyport1mode"] == "djoy"

    _, opts = library.launch_args(
        {
            "controls": "keyboard-arrows",
            "fullscreen": False,
            "scale": "2x",
            "filter": "none",
            "screen_center_h": "smart",
            "screen_center_v": "none",
            "screen_offset_h": "12",
            "screen_offset_v": "-4",
            "stop_keypresses": "on",
        },
    )
    assert opts["gfx_center_horizontal"] == "smart"
    assert opts["gfx_center_vertical"] == "none"
    assert opts["gfx_center_horizontal_position"] == "12"
    assert opts["gfx_center_vertical_position"] == "-4"
    assert opts["input_keyboard_as_joystick_stop_keypresses"] == "yes"

    _, opts = library.launch_args(
        {
            "controls": "keyboard-arrows",
            "fullscreen": False,
            "scale": "2x",
            "filter": "none",
            "video_standard": "ntsc",
            "line_mode": "double",
            "vertical_offset": "-10",
        },
    )
    assert opts["ntsc"] == "true"
    assert opts["gfx_linemode"] == "double"
    assert opts["amiberry.gfx_vertical_offset"] == "-10"

    _, opts = library.launch_args(
        {
            "controls": "keyboard-arrows",
            "fullscreen": False,
            "scale": "2x",
            "filter": "none",
            "video_standard": "pal",
            "line_mode": "single",
        },
    )
    assert opts["ntsc"] == "false"
    assert opts["gfx_linemode"] == "none"

    joy, opts = library.launch_args({"controls": "gamepad", "fullscreen": True, "scale": "2x", "filter": "crt"})
    assert joy is None
    assert "joyport1" not in opts
    assert opts["gfx_fullscreen_amiga"] == "fullwindow"
    assert opts["gfx_fullscreen_picasso"] == "fullwindow"
    assert "gfx_fullscreen" not in opts
    assert "gfx_width" not in opts
    assert opts["amiberry.shader"] == "crt"


def test_hardware_from_db_and_cd32_detection():
    db = {"bubblebobble_v1.1_2518": {"hardware": {"port0": "cd32", "port1": "cd32"}}}
    hw = library.hardware_from_db("BubbleBobble_v1.1_2518", db)
    assert library.needs_cd32_joystick_mode(hw)
    assert library.hardware_from_db("missing", db) is None


def test_display_entry_value_and_empty_store(tmp_path):
    paths = Paths.resolve(tmp_path)
    defaults = library.get_defaults(paths)
    game = {}
    assert library.display_entry_value(game, defaults, "screen_offset_h") == ""
    library.set_game(paths, "G", {"screen_offset_h": "-40"})
    g = library.get_game(paths, "G")
    assert library.display_entry_value(g, defaults, "screen_offset_h") == "-40"
    assert library.store_if_matches_global("", defaults, "screen_offset_h") == "default"


def test_display_value_and_inherited(tmp_path):
    paths = Paths.resolve(tmp_path)
    defaults = library.get_defaults(paths)
    game = {"controls": "default", "scale": "3x"}
    assert library.field_inherited(game, "controls")
    assert not library.field_inherited(game, "scale")
    assert library.display_value(game, defaults, "controls") == defaults["controls"]
    assert library.display_value(game, defaults, "scale") == "3x"
    assert library.store_if_matches_global("keyboard-numpad", defaults, "controls") == "keyboard-numpad"
    assert library.store_if_matches_global(defaults["controls"], defaults, "controls") == "default"
