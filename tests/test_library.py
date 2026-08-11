from easyamiga import library
from easyamiga.paths import Paths


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
    assert "gfx_fullscreen" not in opts
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

    joy, opts = library.launch_args({"controls": "gamepad", "fullscreen": True, "scale": "2x", "filter": "crt"})
    assert joy is None
    assert "joyport1" not in opts
    assert opts["gfx_fullscreen"] == "fullwindow"
    assert "gfx_width" not in opts
    assert opts["shader"] == "crt"


def test_hardware_from_db_and_cd32_detection():
    db = {"bubblebobble_v1.1_2518": {"hardware": {"port0": "cd32", "port1": "cd32"}}}
    hw = library.hardware_from_db("BubbleBobble_v1.1_2518", db)
    assert library.needs_cd32_joystick_mode(hw)
    assert library.hardware_from_db("missing", db) is None
