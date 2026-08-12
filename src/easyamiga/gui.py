"""A simple, friendly desktop GUI for easyamiga.

The window scans the games folder and shows each game in an alphabetical list.
Built with Tkinter so it has no extra Python dependencies (it only needs the
system ``python3-tk`` package, which ``easyamiga install`` sets up).
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Optional

from . import amiberry, install as install_mod, library
from .games import (
    add_game,
    discover_game_sources,
    list_configs,
    prune_orphans,
    resolve_launch,
    scan_games,
)
from .models import DEFAULT_MODEL, get_model
from .paths import Paths
from .roms import DetectedRom, default_model_key, detect_roms, pick_rom_for_model

CONTROL_CHOICES = list(library.CONTROL_LAYOUTS.keys()) + ["gamepad"]
SCALE_CHOICES = ["1x", "2x", "3x"]
FILTER_CHOICES = ["none", "crt"]
SCREEN_CENTER_CHOICES = list(library.SCREEN_CENTER_CHOICES)
VIDEO_STANDARD_CHOICES = list(library.VIDEO_STANDARD_CHOICES)
LINE_MODE_CHOICES = list(library.LINE_MODE_CHOICES)
CD32_PAD_CHOICES = list(library.CD32_PAD_CHOICES)
STOP_KEYPRESS_CHOICES = list(library.STOP_KEYPRESS_CHOICES)

# Palette (Amiga-ish dark blue with a boing-ball red accent)
BG = "#0f172a"
CONTENT_BG = "#0b1220"
CARD = "#1e293b"
CARD_HOVER = "#273449"
ACCENT = "#ff2d2d"
ACCENT_DK = "#b30000"
PLAY_FG = "#ecfdf5"  # play icon on green circle
PLAY_FILL = "#22c55e"  # bright green, no border ring
SAVE_BG = "#10b981"
SAVE_HOVER = "#059669"
FIELD_BG = "#0b1220"       # scroll zones / form panel background
INPUT_BG = "#1e293b"       # inputs (distinct from FIELD_BG)
TOOLBAR_BTN = "#334155"    # stronger toolbar button fill
DIALOG_SEP = "#334155"
TEXT = "#f8fafc"
MUTED = "#94a3b8"
INHERITED = "#64748b"  # weaker than MUTED for inherited per-game values

ROW_H = 38
ROW_BATCH = 30
INPUT_H = 30
LABEL_W = 18
PLAY_SIZE = 22
SPIN_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _blank_default(value: str) -> str:
    return "" if str(value).strip() == "default" else str(value)


def _read_field(path: Path, key: str) -> Optional[str]:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None


def _label_for(config_path: Path) -> str:
    desc = _read_field(config_path, "config_description")
    if desc:
        # Trim the leading "easyamiga: " / "easyamiga " noise for a cleaner card.
        for prefix in ("easyamiga: ", "easyamiga "):
            if desc.startswith(prefix):
                return desc[len(prefix):]
        return desc
    return config_path.stem


class EasyAmigaGUI:
    def __init__(self, base: Optional[str] = None) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.paths = Paths.resolve(base)
        self.paths.ensure()
        self.roms_dir = install_mod.effective_roms_dir(self.paths)
        self.db_by_sha1, self.db_by_name = install_mod.load_whdload_db()
        self._rows: list[tk.Widget] = []
        self._row_by_stem: dict[str, tk.Widget] = {}
        self._row_widgets: dict[str, dict] = {}
        self._library_cache: dict | None = None
        self._pending_configs: list[Path] = []
        self._scanning = False
        self._spin_index = 0

        self.root = tk.Tk()
        self.root.title("easyamiga")
        self.root.geometry("900x620")
        self.root.minsize(560, 420)
        self.root.configure(bg=BG)
        self._setup_widget_styles()

        self._build_header()
        self._build_toolbar()
        self._build_list()
        self._build_statusbar()

        self.refresh()
        self._update_amiberry_banner()
        # Paint the window first; scan can take a moment on large libraries.
        self.root.after(50, lambda: self.do_scan(announce=False))

    def _setup_widget_styles(self) -> None:
        style = self.ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        combo_base = {
            "fieldbackground": INPUT_BG,
            "background": INPUT_BG,
            "foreground": TEXT,
            "arrowcolor": MUTED,
            "bordercolor": INPUT_BG,
            "lightcolor": INPUT_BG,
            "darkcolor": INPUT_BG,
            "borderwidth": 0,
            "relief": "flat",
            "padding": (8, 6),
        }
        style.configure("Ea.TCombobox", **combo_base)
        style.map(
            "Ea.TCombobox",
            fieldbackground=[("readonly", INPUT_BG), ("disabled", INPUT_BG)],
            foreground=[("readonly", TEXT)],
            background=[("readonly", INPUT_BG)],
        )
        style.configure("EaInherited.TCombobox", **{**combo_base, "foreground": INHERITED})
        style.map(
            "EaInherited.TCombobox",
            fieldbackground=[("readonly", INPUT_BG)],
            foreground=[("readonly", INHERITED)],
        )
        scroll_base = {
            "background": CARD_HOVER,
            "troughcolor": FIELD_BG,
            "bordercolor": FIELD_BG,
            "arrowcolor": MUTED,
            "lightcolor": CARD_HOVER,
            "darkcolor": CARD_HOVER,
            "borderwidth": 0,
            "relief": "flat",
            "gripcount": 0,
        }
        style.configure("Ea.Vertical.TScrollbar", **scroll_base)
        style.map(
            "Ea.Vertical.TScrollbar",
            background=[("active", MUTED), ("pressed", TEXT)],
        )

    def _build_header(self) -> None:
        tk = self.tk
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=18, pady=(22, 14))

        badge = tk.Canvas(header, width=44, height=44, bg=BG, highlightthickness=0)
        badge.pack(side="left")
        self._draw_boing(badge, 22, 22, 18)

        text = tk.Frame(header, bg=BG)
        text.pack(side="left", padx=12)
        tk.Label(text, text="easyamiga", bg=BG, fg=TEXT,
                 font=("Sans", 22, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(text, text="Click a game to play it on your Amiga",
                 bg=BG, fg=MUTED, font=("Sans", 11)).pack(anchor="w")

    def _default_model(self) -> str:
        return default_model_key(detect_roms(self.roms_dir), DEFAULT_MODEL)

    def _build_toolbar(self) -> None:
        tk = self.tk
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=18, pady=(6, 10))

        self._toolbar_button(bar, "\u21bb  Scan games folder", self.do_scan)
        self._toolbar_button(bar, "+  Add game file", self.add_file)
        self._toolbar_button(bar, "+  Add game folder", self.add_folder)
        self._toolbar_button(bar, "\U0001F4C1  Open games folder", self.open_games)
        self._toolbar_button(bar, "\u2699  Settings", self.open_default_settings)

    def _toolbar_button(self, parent, text, command):
        tk = self.tk
        btn = tk.Button(
            parent, text=text, command=command, bg=TOOLBAR_BTN, fg=TEXT,
            activebackground=CARD_HOVER, activeforeground=TEXT,
            relief="flat", font=("Sans", 10), padx=10, pady=6,
            cursor="hand2", borderwidth=0, highlightthickness=0,
            highlightbackground=TOOLBAR_BTN, highlightcolor=TOOLBAR_BTN,
        )
        btn.pack(side="left", padx=4, pady=(4, 7))
        return btn

    def _build_list(self) -> None:
        tk = self.tk
        container = tk.Frame(self.root, bg=CONTENT_BG)
        container.pack(fill="both", expand=True, padx=10, pady=4)

        self.banner = tk.Label(container, text="", bg="#7f1d1d", fg=TEXT,
                               font=("Sans", 10, "bold"), anchor="w", padx=12)

        list_zone = tk.Frame(container, bg=FIELD_BG)
        list_zone.pack(fill="both", expand=True, pady=(4, 0))

        outer = tk.Frame(list_zone, bg=FIELD_BG)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(outer, bg=FIELD_BG, highlightthickness=0, bd=0)
        self.scroll = self.ttk.Scrollbar(
            outer, orient="vertical", command=self.canvas.yview,
            style="Ea.Vertical.TScrollbar",
        )
        self.list_frame = tk.Frame(self.canvas, bg=FIELD_BG)
        self._list_window = self.canvas.create_window((0, 0), window=self.list_frame,
                                                       anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.canvas.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.scroll.pack(side="right", fill="y")

        self.list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(seq, self._on_scroll)

        self.scan_overlay = tk.Frame(container, bg=CONTENT_BG)
        self.scan_overlay_label = tk.Label(
            self.scan_overlay, text="", bg=CONTENT_BG, fg=MUTED,
            font=("Sans", 12),
        )
        self.scan_overlay_label.pack(expand=True)
        self._list_container = container
        self._list_zone = list_zone

    def _build_statusbar(self) -> None:
        tk = self.tk
        self.status = tk.Label(self.root, text="", bg="#020617", fg=MUTED,
                               anchor="w", font=("Sans", 9), padx=12, pady=4)
        self.status.pack(fill="x", side="bottom")

    # --- drawing -----------------------------------------------------------
    def _draw_boing(self, canvas, cx, cy, r) -> None:
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=ACCENT,
                           outline=ACCENT_DK, width=2)
        step = r // 2
        for i, dx in enumerate(range(-r, r, step)):
            for j, dy in enumerate(range(-r, r, step)):
                if (i + j) % 2 == 0:
                    continue
                x0, y0 = cx + dx, cy + dy
                if (dx + step / 2) ** 2 + (dy + step / 2) ** 2 <= r * r:
                    canvas.create_rectangle(x0, y0, x0 + step, y0 + step,
                                           fill="#ffffff", outline="")

    # --- library cache (avoid re-reading library.json per row) ------------
    def _invalidate_library_cache(self) -> None:
        self._library_cache = None

    def _library_data(self) -> dict:
        if self._library_cache is None:
            self._library_cache = library.load(self.paths)
        return self._library_cache

    def _get_game_cached(self, key: str) -> dict:
        return dict(self._library_data().get("games", {}).get(key, {}))

    def _sorted_configs(self) -> list[Path]:
        return sorted(list_configs(self.paths), key=lambda p: self._title_for(p).lower())

    # --- behaviour ---------------------------------------------------------
    def _title_for(self, config_path: Path) -> str:
        override = self._get_game_cached(config_path.stem).get("display_name")
        return library.title_for(config_path.stem, override, self.db_by_name)

    def _current_rom(self, model_key: str) -> Optional[DetectedRom]:
        return pick_rom_for_model(detect_roms(self.roms_dir), model_key)

    def do_scan(self, announce: bool = True) -> None:
        if self._scanning:
            return
        self._scanning = True
        self._show_scan_overlay()
        self._animate_scan()

        def work() -> None:
            from tkinter import messagebox

            model = get_model(self._default_model())
            rom = self._current_rom(model.key)
            pruned = prune_orphans(self.paths)
            games = scan_games(
                self.paths, model, rom=rom, roms_dir=self.roms_dir, prune=False,
            )
            added = sum(1 for g in games if g.newly_created)

            def finish() -> None:
                self._hide_scan_overlay()
                self.refresh()
                if announce:
                    msg = (
                        f"Found {len(games)} game(s) in your games folder.\n"
                        f"Added {added} new one(s)."
                    )
                    if pruned:
                        msg += f"\nRemoved {len(pruned)} game(s) whose files were deleted."
                    messagebox.showinfo("Scan complete", msg)

            self.root.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    def _show_scan_overlay(self) -> None:
        self._spin_index = 0
        self.scan_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

    def _hide_scan_overlay(self) -> None:
        self._scanning = False
        self.scan_overlay.place_forget()

    def _animate_scan(self) -> None:
        if not self._scanning:
            return
        ch = SPIN_CHARS[self._spin_index % len(SPIN_CHARS)]
        self._spin_index += 1
        self.scan_overlay_label.configure(text=f"{ch}  Scanning games folder…")
        self.root.after(90, self._animate_scan)

    def add_file(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Choose an Amiga game (ADF disk image or archive)",
            filetypes=[("Amiga games", "*.adf *.adz *.ipf *.lha *.lzx *.zip"),
                       ("All files", "*.*")],
        )
        if path:
            self._add_and_refresh(Path(path))

    def add_folder(self) -> None:
        from tkinter import filedialog

        path = filedialog.askdirectory(title="Choose a WHDLoad game folder")
        if path:
            self._add_and_refresh(Path(path))

    def _add_and_refresh(self, source: Path) -> None:
        from tkinter import messagebox

        model = get_model(self._default_model())
        rom = self._current_rom(model.key)
        try:
            game = add_game(self.paths, source, model, rom=rom, roms_dir=self.roms_dir)
        except Exception as exc:
            messagebox.showerror("Could not add game", str(exc))
            return
        self.refresh()
        messagebox.showinfo("Game added", f"Added '{game.name}'. Click it to play!")

    def open_games(self) -> None:
        try:
            subprocess.Popen(["xdg-open", str(self.paths.games)])
        except Exception:
            pass

    def play(self, config_path: Path) -> None:
        from tkinter import messagebox

        if not amiberry.is_installed():
            messagebox.showerror(
                "Amiberry not found",
                "Amiberry is not installed. Run 'easyamiga install' in a terminal first.",
            )
            return

        eff = library.effective(self.paths, config_path.stem)
        hardware = library.hardware_from_db(config_path.stem, self.db_by_name)
        joyports, options = library.launch_args(eff, hardware=hardware)
        source, kind = resolve_launch(self.paths, config_path)
        try:
            if kind == "whdload" and source is not None:
                # WHDLoad game: boot via Amiberry's WHDLoad Booter (--autoload),
                # regardless of what a stale config said.
                install_mod.sync_kickstarts(self.paths, log=lambda *_: None)
                amiberry.launch_game(source, kind, wait=False, joyports=joyports, options=options)
            else:
                # ADF game (boots the floppy) or a bare machine: use the config.
                amiberry.launch(config_path, wait=False, joyports=joyports, options=options)
        except FileNotFoundError as exc:
            messagebox.showerror("Could not launch game", str(exc))

    # --- settings dialogs --------------------------------------------------
    def _new_dialog(self, title: str, width: int = 500, height: int = 520):
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=CARD)
        win.geometry(f"{width}x{height}")
        win.minsize(width, 400)
        win.transient(self.root)
        return win

    def _dialog_layout(self, win):
        """Pin a footer (Save/Cancel) and return ``(main_area, footer)`` frames."""
        tk = self.tk
        footer = tk.Frame(win, bg=CARD)
        footer.pack(side="bottom", fill="x", padx=16, pady=12)
        tk.Frame(win, bg=DIALOG_SEP, height=1).pack(side="bottom", fill="x", padx=16)
        main = tk.Frame(win, bg=CARD)
        main.pack(fill="both", expand=True)
        return main, footer

    def _scrollable_body(self, parent) -> tuple:
        """Scrollable inner frame; returns ``(body, canvas)`` for wheel binding."""
        tk, ttk = self.tk, self.ttk
        zone = tk.Frame(parent, bg=FIELD_BG)
        zone.pack(fill="both", expand=True, padx=16, pady=(8, 8))

        outer = tk.Frame(zone, bg=FIELD_BG)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        canvas = tk.Canvas(outer, bg=FIELD_BG, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(
            outer, orient="vertical", command=canvas.yview, style="Ea.Vertical.TScrollbar",
        )
        body = tk.Frame(canvas, bg=FIELD_BG)
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)

        def _resize(event):
            canvas.itemconfigure(body_id, width=event.width)

        def _scroll_region(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        body.bind("<Configure>", _scroll_region)
        canvas.bind("<Configure>", _resize)

        def _wheel(event):
            if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
                canvas.yview_scroll(1, "units")
            return "break"

        canvas.bind("<MouseWheel>", _wheel)
        canvas.bind("<Button-4>", _wheel)
        canvas.bind("<Button-5>", _wheel)

        canvas.pack(side="left", fill="both", expand=True, padx=(0, 10))
        scroll.pack(side="right", fill="y")
        return body, canvas

    def _bind_dialog_wheel(self, widget, canvas) -> None:
        """Bind mouse wheel on every widget in the settings form."""

        def _wheel(event):
            if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
                canvas.yview_scroll(1, "units")
            return "break"

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(seq, _wheel)
        for child in widget.winfo_children():
            self._bind_dialog_wheel(child, canvas)

    def _form_label(self, parent, text: str) -> None:
        tk = self.tk
        bg = parent.cget("bg")
        tk.Label(
            parent, text=text, bg=bg, fg=MUTED, font=("Sans", 10),
            width=LABEL_W, anchor="w",
        ).pack(side="left", padx=(0, 10))

    def _input_shell(self, parent) -> tk.Frame:
        tk = self.tk
        shell = tk.Frame(parent, bg=INPUT_BG, height=INPUT_H)
        shell.pack(side="left", fill="x", expand=True)
        shell.pack_propagate(False)
        return shell

    def _dropdown(
        self,
        parent,
        label: str,
        var,
        choices: list[str],
        inherited: bool = False,
        width: int = 20,
    ):
        tk, ttk = self.tk, self.ttk
        bg = parent.cget("bg")
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=3)
        self._form_label(row, label)
        shell = self._input_shell(row)
        style = "EaInherited.TCombobox" if inherited else "Ea.TCombobox"
        combo = ttk.Combobox(
            shell, textvariable=var, values=choices, state="readonly",
            style=style, font=("Sans", 10), width=width,
        )
        combo.pack(fill="both", expand=True, padx=1, pady=1)

        loading = True

        def mark_override(*_):
            if loading:
                return
            combo.configure(style="Ea.TCombobox")

        var.trace_add("write", mark_override)

        def finish_loading():
            nonlocal loading
            loading = False

        combo._ea_finish_loading = finish_loading  # noqa: SLF001
        return combo

    def _entry_row(self, parent, label: str, var, inherited: bool = False, width: int = 12):
        tk = self.tk
        bg = parent.cget("bg")
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=3)
        self._form_label(row, label)
        shell = self._input_shell(row)
        fg = INHERITED if inherited else TEXT
        entry = tk.Entry(
            shell, textvariable=var, bg=INPUT_BG, fg=fg, insertbackground=TEXT,
            relief="flat", font=("Sans", 10), width=width,
            highlightthickness=0, borderwidth=0,
        )
        entry.pack(fill="both", expand=True, padx=8, pady=4)

        loading = True

        def mark_override(*_):
            if loading:
                return
            entry.configure(fg=TEXT)

        var.trace_add("write", mark_override)

        def finish_loading():
            nonlocal loading
            loading = False

        entry._ea_finish_loading = finish_loading  # noqa: SLF001
        return entry

    def _name_entry_row(self, parent, label: str, var):
        tk = self.tk
        bg = parent.cget("bg")
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", pady=3)
        self._form_label(row, label)
        shell = self._input_shell(row)
        entry = tk.Entry(
            shell, textvariable=var, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Sans", 10),
            highlightthickness=0, borderwidth=0,
        )
        entry.pack(fill="both", expand=True, padx=8, pady=4)
        return entry

    def _section_label(self, parent, text: str):
        tk = self.tk
        bg = parent.cget("bg")
        tk.Label(parent, text=text, bg=bg, fg=TEXT, font=("Sans", 11, "bold")).pack(
            anchor="w", pady=(10, 4))

    def _finish_widget_loading(self, widgets) -> None:
        for w in widgets:
            finish = getattr(w, "_ea_finish_loading", None)
            if finish:
                finish()

    def open_default_settings(self) -> None:
        tk = self.tk
        d = library.get_defaults(self.paths)
        win = self._new_dialog("Default settings (all games)", height=540)
        tk.Label(win, text="Default settings", bg=CARD, fg=TEXT,
                 font=("Sans", 14, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(win, text="Applied to every game unless overridden per game.",
                 bg=CARD, fg=MUTED, font=("Sans", 9)).pack(anchor="w", padx=16, pady=(0, 4))
        tk.Frame(win, bg=DIALOG_SEP, height=1).pack(fill="x", padx=16, pady=(4, 0))

        main, footer = self._dialog_layout(win)
        body, scroll_canvas = self._scrollable_body(main)

        controls = tk.StringVar(value=d["controls"])
        scale = tk.StringVar(value=d["scale"])
        filt = tk.StringVar(value=d["filter"])
        full = tk.StringVar(value="on" if d["fullscreen"] else "off")
        cd32 = tk.StringVar(value=d.get("cd32_pad", "default"))
        stop_kp = tk.StringVar(value=d.get("stop_keypresses", "default"))
        center_h = tk.StringVar(value=d.get("screen_center_h", "default"))
        center_v = tk.StringVar(value=d.get("screen_center_v", "default"))
        offset_h = tk.StringVar(value=_blank_default(d.get("screen_offset_h", "default")))
        offset_v = tk.StringVar(value=_blank_default(d.get("screen_offset_v", "default")))
        video_std = tk.StringVar(value=d.get("video_standard", "default"))
        line_mode = tk.StringVar(value=d.get("line_mode", "default"))

        widgets = []
        self._section_label(body, "Display")
        widgets.append(self._dropdown(body, "Fullscreen", full, ["off", "on"]))
        widgets.append(self._dropdown(body, "Window scale", scale, SCALE_CHOICES))
        widgets.append(self._dropdown(body, "Filter", filt, FILTER_CHOICES))
        widgets.append(self._dropdown(body, "Video standard", video_std, VIDEO_STANDARD_CHOICES))
        widgets.append(self._dropdown(body, "Line mode", line_mode, LINE_MODE_CHOICES))
        widgets.append(self._dropdown(body, "Center horizontal", center_h, SCREEN_CENTER_CHOICES))
        widgets.append(self._dropdown(body, "Center vertical", center_v, SCREEN_CENTER_CHOICES))
        widgets.append(self._entry_row(body, "Offset horizontal", offset_h))
        widgets.append(self._entry_row(body, "Offset vertical", offset_v))

        self._section_label(body, "Input")
        widgets.append(self._dropdown(body, "Controls", controls, CONTROL_CHOICES, width=22))
        widgets.append(self._dropdown(body, "CD32 pad mode", cd32, CD32_PAD_CHOICES))
        widgets.append(self._dropdown(body, "Block key dupes", stop_kp, STOP_KEYPRESS_CHOICES))
        self._finish_widget_loading(widgets)
        self._bind_dialog_wheel(body, scroll_canvas)

        def save():
            library.set_defaults(self.paths, {
                "controls": controls.get(),
                "fullscreen": full.get() == "on",
                "scale": scale.get(),
                "filter": filt.get(),
                "cd32_pad": cd32.get(),
                "stop_keypresses": stop_kp.get(),
                "screen_center_h": center_h.get(),
                "screen_center_v": center_v.get(),
                "screen_offset_h": offset_h.get().strip() or "default",
                "screen_offset_v": offset_v.get().strip() or "default",
                "video_standard": video_std.get(),
                "line_mode": line_mode.get(),
            })
            self._invalidate_library_cache()
            win.destroy()

        self._dialog_buttons(footer, save)

    def open_game_settings(self, config_path: Path) -> None:
        tk = self.tk
        key = config_path.stem
        g = library.get_game(self.paths, key)
        defaults = library.get_defaults(self.paths)
        real = library.title_for(key, None, self.db_by_name)
        win = self._new_dialog(f"Settings — {real}", height=560)

        tk.Label(win, text=real, bg=CARD, fg=TEXT, font=("Sans", 14, "bold"),
                 wraplength=440, justify="left").pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(win, text=key, bg=CARD, fg=MUTED, font=("Sans", 8)).pack(anchor="w", padx=16)
        chipset = (_read_field(config_path, "chipset") or "").upper()
        if chipset:
            tk.Label(
                win, text=f"Machine type: {chipset}", bg=CARD, fg=MUTED, font=("Sans", 9),
            ).pack(anchor="w", padx=16, pady=(2, 0))
        tk.Label(
            win,
            text=(
                "You can try to tweak Amiberry settings here if the game doesn't run "
                "as desired. Grayed out values follow the global default."
            ),
            bg=CARD, fg=MUTED, font=("Sans", 9), wraplength=440, justify="left",
        ).pack(anchor="w", padx=16, pady=(4, 0))
        tk.Frame(win, bg=DIALOG_SEP, height=1).pack(fill="x", padx=16, pady=(6, 0))

        main, footer = self._dialog_layout(win)
        body, scroll_canvas = self._scrollable_body(main)

        name_var = tk.StringVar(value=g.get("display_name", ""))
        self._name_entry_row(body, "Display name", name_var)

        controls = tk.StringVar(value=library.display_value(g, defaults, "controls"))
        full = tk.StringVar(value=library.display_value(g, defaults, "fullscreen"))
        scale = tk.StringVar(value=library.display_value(g, defaults, "scale"))
        filt = tk.StringVar(value=library.display_value(g, defaults, "filter"))
        cd32 = tk.StringVar(value=library.display_value(g, defaults, "cd32_pad"))
        stop_kp = tk.StringVar(value=library.display_value(g, defaults, "stop_keypresses"))
        center_h = tk.StringVar(value=library.display_value(g, defaults, "screen_center_h"))
        center_v = tk.StringVar(value=library.display_value(g, defaults, "screen_center_v"))
        offset_h = tk.StringVar(value=library.display_entry_value(g, defaults, "screen_offset_h"))
        offset_v = tk.StringVar(value=library.display_entry_value(g, defaults, "screen_offset_v"))
        video_std = tk.StringVar(value=library.display_value(g, defaults, "video_standard"))
        line_mode = tk.StringVar(value=library.display_value(g, defaults, "line_mode"))

        widgets = []
        self._section_label(body, "Display")
        widgets.append(self._dropdown(
            body, "Fullscreen", full, ["off", "on"],
            inherited=library.fullscreen_inherited(g),
        ))
        widgets.append(self._dropdown(
            body, "Window scale", scale, SCALE_CHOICES,
            inherited=library.field_inherited(g, "scale"),
        ))
        widgets.append(self._dropdown(
            body, "Filter", filt, FILTER_CHOICES,
            inherited=library.field_inherited(g, "filter"),
        ))
        widgets.append(self._dropdown(
            body, "Video standard", video_std, list(VIDEO_STANDARD_CHOICES),
            inherited=library.field_inherited(g, "video_standard"),
        ))
        widgets.append(self._dropdown(
            body, "Line mode", line_mode, list(LINE_MODE_CHOICES),
            inherited=library.field_inherited(g, "line_mode"),
        ))
        widgets.append(self._dropdown(
            body, "Center horizontal", center_h, list(SCREEN_CENTER_CHOICES),
            inherited=library.field_inherited(g, "screen_center_h"),
        ))
        widgets.append(self._dropdown(
            body, "Center vertical", center_v, list(SCREEN_CENTER_CHOICES),
            inherited=library.field_inherited(g, "screen_center_v"),
        ))
        widgets.append(self._entry_row(
            body, "Offset horizontal", offset_h,
            inherited=library.field_inherited(g, "screen_offset_h"),
        ))
        widgets.append(self._entry_row(
            body, "Offset vertical", offset_v,
            inherited=library.field_inherited(g, "screen_offset_v"),
        ))

        self._section_label(body, "Input")
        widgets.append(self._dropdown(
            body, "Controls", controls, CONTROL_CHOICES, width=22,
            inherited=library.field_inherited(g, "controls"),
        ))
        widgets.append(self._dropdown(
            body, "CD32 pad mode", cd32, list(CD32_PAD_CHOICES),
            inherited=library.field_inherited(g, "cd32_pad"),
        ))
        widgets.append(self._dropdown(
            body, "Block key dupes", stop_kp, list(STOP_KEYPRESS_CHOICES),
            inherited=library.field_inherited(g, "stop_keypresses"),
        ))
        self._finish_widget_loading(widgets)

        self._section_label(body, "Notes")
        notes_shell = tk.Frame(body, bg=INPUT_BG)
        notes_shell.pack(fill="x", pady=(2, 0))
        notes = tk.Text(
            notes_shell, height=4, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Sans", 10), wrap="word",
            highlightthickness=0, borderwidth=0,
        )
        notes.pack(fill="both", expand=True, padx=8, pady=6)
        notes.insert("1.0", g.get("notes", ""))
        tk.Label(
            body,
            text="Here you can put your own notes about the game.",
            bg=FIELD_BG, fg=MUTED, font=("Sans", 9),
        ).pack(anchor="w", pady=(2, 8))

        self._bind_dialog_wheel(body, scroll_canvas)

        global_full = "on" if defaults["fullscreen"] else "off"

        def save():
            fv = full.get()
            if fv == global_full:
                fs_choice, fs_val = "default", "default"
            else:
                fs_choice, fs_val = fv, fv == "on"

            values: dict = {
                "display_name": name_var.get().strip(),
                "notes": notes.get("1.0", "end").strip(),
                "controls": library.store_if_matches_global(controls.get(), defaults, "controls"),
                "scale": library.store_if_matches_global(scale.get(), defaults, "scale"),
                "filter": library.store_if_matches_global(filt.get(), defaults, "filter"),
                "cd32_pad": library.store_if_matches_global(cd32.get(), defaults, "cd32_pad"),
                "stop_keypresses": library.store_if_matches_global(stop_kp.get(), defaults, "stop_keypresses"),
                "screen_center_h": library.store_if_matches_global(center_h.get(), defaults, "screen_center_h"),
                "screen_center_v": library.store_if_matches_global(center_v.get(), defaults, "screen_center_v"),
                "screen_offset_h": library.store_if_matches_global(
                    offset_h.get().strip(), defaults, "screen_offset_h",
                ),
                "screen_offset_v": library.store_if_matches_global(
                    offset_v.get().strip(), defaults, "screen_offset_v",
                ),
                "video_standard": library.store_if_matches_global(
                    video_std.get(), defaults, "video_standard",
                ),
                "line_mode": library.store_if_matches_global(
                    line_mode.get(), defaults, "line_mode",
                ),
                "fullscreen_choice": fs_choice,
                "fullscreen": fs_val,
            }
            library.set_game(self.paths, key, values)
            self._invalidate_library_cache()
            win.destroy()
            self._update_row_after_save(config_path)

        self._dialog_buttons(footer, save)

    def _dialog_buttons(self, parent, on_save):
        tk = self.tk
        tk.Button(parent, text="Cancel", command=parent.winfo_toplevel().destroy,
                  bg=CARD, fg=TEXT, activebackground=CARD_HOVER, activeforeground=TEXT,
                  relief="flat", font=("Sans", 11), cursor="hand2", borderwidth=0,
                  highlightthickness=0, padx=12, pady=6).pack(side="right", padx=4)
        tk.Button(parent, text="Save", command=on_save, bg=SAVE_BG, fg="#ffffff",
                  activebackground=SAVE_HOVER, activeforeground="#ffffff", relief="flat",
                  font=("Sans", 11, "bold"), cursor="hand2", borderwidth=0,
                  highlightthickness=0, padx=16, pady=6).pack(side="right", padx=4)

    # --- layout / refresh --------------------------------------------------
    def refresh(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows = []
        self._row_by_stem = {}
        self._row_widgets = {}
        self._invalidate_library_cache()

        self._pending_configs = self._sorted_configs()
        if not self._pending_configs:
            self._finish_refresh()
            return
        self._build_rows_batch(0)

    def _build_rows_batch(self, start: int) -> None:
        end = min(start + ROW_BATCH, len(self._pending_configs))
        for config in self._pending_configs[start:end]:
            self._rows.append(self._make_row(config))
        if end < len(self._pending_configs):
            self.root.after(1, lambda: self._build_rows_batch(end))
        else:
            self._finish_refresh()

    def _finish_refresh(self) -> None:
        n = len(self._rows)
        amiberry_ok = amiberry.is_installed()
        self.status.configure(
            text=f"{n} game(s)  \u2022  games folder: {self.paths.games}  \u2022  "
                 f"Amiberry: {'ready' if amiberry_ok else 'not installed'}"
        )
        self._update_amiberry_banner()

    def _update_row_after_save(self, config_path: Path) -> None:
        stem = config_path.stem
        widgets = self._row_widgets.get(stem)
        if not widgets:
            self.refresh()
            return
        widgets["title_label"].configure(text=self._title_for(config_path))
        self._repack_rows_sorted()

    def _repack_rows_sorted(self) -> None:
        for row in self._rows:
            row.pack_forget()
        for config in self._sorted_configs():
            row = self._row_by_stem.get(config.stem)
            if row is not None:
                row.pack(fill="x", padx=8, pady=3)

    def _square_play_button(self, parent, command):
        tk = self.tk
        box = tk.Frame(
            parent, width=PLAY_SIZE, height=PLAY_SIZE, bg=PLAY_FILL,
            cursor="hand2", highlightthickness=0, bd=0,
        )
        box.pack_propagate(False)
        box.grid_rowconfigure(0, weight=1)
        box.grid_columnconfigure(0, weight=1)
        icon = tk.Label(
            box, text="\u25b8", bg=PLAY_FILL, fg=PLAY_FG,
            font=("Sans", 10, "bold"), cursor="hand2",
        )
        icon.grid(row=0, column=0, padx=(1, 0))

        def on_click(_event=None):
            command()

        box.bind("<Button-1>", on_click)
        icon.bind("<Button-1>", on_click)

        def _paint(_bg: str) -> None:
            pass

        return box, _paint

    def _make_row(self, config_path: Path):
        tk = self.tk
        stem = config_path.stem
        row = tk.Frame(self.list_frame, bg=CARD, height=ROW_H,
                       highlightbackground="#334155", highlightthickness=1)
        row.pack(fill="x", padx=8, pady=3)
        row.pack_propagate(False)
        self._row_by_stem[stem] = row

        play_wrap = tk.Frame(row, bg=CARD)
        play_wrap.pack(side="left", padx=(10, 12), pady=5)
        play, paint_play = self._square_play_button(
            play_wrap, lambda p=config_path: self.play(p),
        )
        play.pack()

        info = tk.Frame(row, bg=CARD)
        info.pack(side="left", fill="both", expand=True, pady=8)
        title_label = tk.Label(
            info, text=self._title_for(config_path), bg=CARD, fg=TEXT,
            font=("Sans", 11, "bold"), anchor="w", justify="left",
        )
        title_label.pack(anchor="w", fill="x")
        self._row_widgets[stem] = {"title_label": title_label, "info": info, "cog": None}

        cog = tk.Label(
            row, text="\u2699", bg=CARD, fg=MUTED, font=("Sans", 15),
            cursor="hand2", padx=10, pady=4,
        )
        cog.pack(side="right", padx=(4, 10))
        cog.bind("<Button-1>", lambda e, p=config_path: self.open_game_settings(p))
        self._row_widgets[stem]["cog"] = cog

        for widget in (row, info, play):
            widget.bind("<Double-Button-1>", lambda e, p=config_path: self.play(p))

        def on_enter(_):
            row.configure(bg=CARD_HOVER)
            info.configure(bg=CARD_HOVER)
            title_label.configure(bg=CARD_HOVER)
            cog.configure(bg=CARD_HOVER)
            play_wrap.configure(bg=CARD_HOVER)
            paint_play(CARD_HOVER)
        def on_leave(_):
            row.configure(bg=CARD)
            info.configure(bg=CARD)
            title_label.configure(bg=CARD)
            cog.configure(bg=CARD)
            play_wrap.configure(bg=CARD)
            paint_play(CARD)
        row.bind("<Enter>", on_enter)
        row.bind("<Leave>", on_leave)
        return row

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._list_window, width=event.width)

    def _on_scroll(self, event) -> None:
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            self.canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            self.canvas.yview_scroll(1, "units")

    def _update_amiberry_banner(self) -> None:
        if amiberry.is_installed():
            self.banner.pack_forget()
        else:
            self.banner.configure(
                text="  Amiberry is not installed. Run 'easyamiga install' in a "
                     "terminal to enable playing games."
            )
            self.banner.pack(fill="x", before=self.canvas)

    def run(self) -> None:
        self.root.mainloop()


def run_gui(base: Optional[str] = None) -> None:
    EasyAmigaGUI(base).run()


def main() -> None:  # console-script entry point (easyamiga-gui)
    run_gui()


if __name__ == "__main__":
    main()
