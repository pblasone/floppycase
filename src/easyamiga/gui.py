"""A simple, friendly desktop GUI for easyamiga.

The window scans the games folder and shows each game in an alphabetical list.
Built with Tkinter so it has no extra Python dependencies (it only needs the
system ``python3-tk`` package, which ``easyamiga install`` sets up).
"""

from __future__ import annotations

import subprocess
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
CD32_PAD_CHOICES = list(library.CD32_PAD_CHOICES)
STOP_KEYPRESS_CHOICES = list(library.STOP_KEYPRESS_CHOICES)

# Palette (Amiga-ish dark blue with a boing-ball red accent)
BG = "#0f172a"
CONTENT_BG = "#0b1220"
CARD = "#1e293b"
CARD_HOVER = "#273449"
ACCENT = "#ff2d2d"
ACCENT_DK = "#b30000"
TEXT = "#f8fafc"
MUTED = "#94a3b8"

ROW_H = 52


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

        self.root = tk.Tk()
        self.root.title("easyamiga")
        self.root.geometry("900x620")
        self.root.minsize(560, 420)
        self.root.configure(bg=BG)

        self._build_header()
        self._build_toolbar()
        self._build_list()
        self._build_statusbar()

        # Auto-scan on open so games appear with zero effort.
        self.do_scan(announce=False)
        self._update_amiberry_banner()

    # --- UI construction ---------------------------------------------------
    def _build_header(self) -> None:
        tk = self.tk
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=18, pady=(16, 6))

        badge = tk.Canvas(header, width=44, height=44, bg=BG, highlightthickness=0)
        badge.pack(side="left")
        self._draw_boing(badge, 22, 22, 18)

        text = tk.Frame(header, bg=BG)
        text.pack(side="left", padx=12)
        tk.Label(text, text="easyamiga", bg=BG, fg=TEXT,
                 font=("Sans", 22, "bold")).pack(anchor="w")
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
        btn = tk.Button(parent, text=text, command=command, bg=CARD, fg=TEXT,
                        activebackground=CARD_HOVER, activeforeground=TEXT,
                        relief="flat", font=("Sans", 10), padx=10, pady=6,
                        cursor="hand2", borderwidth=0)
        btn.pack(side="left", padx=4)
        return btn

    def _build_list(self) -> None:
        tk = self.tk
        container = tk.Frame(self.root, bg=CONTENT_BG)
        container.pack(fill="both", expand=True, padx=10, pady=4)

        self.banner = tk.Label(container, text="", bg="#7f1d1d", fg=TEXT,
                               font=("Sans", 10, "bold"), anchor="w", padx=12)

        self.canvas = tk.Canvas(container, bg=CONTENT_BG, highlightthickness=0)
        self.scroll = self.ttk.Scrollbar(container, orient="vertical",
                                         command=self.canvas.yview)
        self.list_frame = tk.Frame(self.canvas, bg=CONTENT_BG)
        self._list_window = self.canvas.create_window((0, 0), window=self.list_frame,
                                                       anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

        self.list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(seq, self._on_scroll)

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

    # --- behaviour ---------------------------------------------------------
    def _title_for(self, config_path: Path) -> str:
        override = library.get_game(self.paths, config_path.stem).get("display_name")
        return library.title_for(config_path.stem, override, self.db_by_name)

    def _current_rom(self, model_key: str) -> Optional[DetectedRom]:
        return pick_rom_for_model(detect_roms(self.roms_dir), model_key)

    def do_scan(self, announce: bool = True) -> None:
        from tkinter import messagebox

        model = get_model(self._default_model())
        rom = self._current_rom(model.key)
        pruned = prune_orphans(self.paths)  # drop games whose files were deleted
        games = scan_games(self.paths, model, rom=rom, roms_dir=self.roms_dir, prune=False)
        added = sum(1 for g in games if g.newly_created)
        self.refresh()
        if announce:
            msg = (
                f"Found {len(games)} game(s) in your games folder.\n"
                f"Added {added} new one(s)."
            )
            if pruned:
                msg += f"\nRemoved {len(pruned)} game(s) whose files were deleted."
            messagebox.showinfo("Scan complete", msg)

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
    def _dropdown(self, parent, label, var, choices, width=16):
        tk = self.tk
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=CARD, fg=MUTED, font=("Sans", 10), width=12,
                 anchor="w").pack(side="left")
        menu = tk.OptionMenu(row, var, *choices)
        menu.configure(bg=BG, fg=TEXT, activebackground=CARD_HOVER, activeforeground=TEXT,
                       highlightthickness=0, relief="flat", font=("Sans", 10), width=width)
        menu["menu"].configure(bg=BG, fg=TEXT)
        menu.pack(side="left")

    def _new_dialog(self, title, width=440, height=460):
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=CARD)
        win.geometry(f"{width}x{height}")
        win.transient(self.root)
        return win

    def _entry_row(self, parent, label, var, width=10):
        tk = self.tk
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=CARD, fg=MUTED, font=("Sans", 10), width=18,
                 anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, bg=BG, fg=TEXT, insertbackground=TEXT,
                 relief="flat", font=("Sans", 10), width=width).pack(side="left")

    def _section_label(self, parent, text):
        tk = self.tk
        tk.Label(parent, text=text, bg=CARD, fg=TEXT, font=("Sans", 11, "bold")).pack(
            anchor="w", pady=(10, 4))

    def open_default_settings(self) -> None:
        tk = self.tk
        d = library.get_defaults(self.paths)
        win = self._new_dialog("Default settings (all games)", height=560)
        tk.Label(win, text="Default settings", bg=CARD, fg=TEXT,
                 font=("Sans", 14, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(win, text="Applied to every game unless overridden per game.",
                 bg=CARD, fg=MUTED, font=("Sans", 9)).pack(anchor="w", padx=16, pady=(0, 8))
        body = tk.Frame(win, bg=CARD)
        body.pack(fill="x", padx=16)

        controls = tk.StringVar(value=d["controls"])
        scale = tk.StringVar(value=d["scale"])
        filt = tk.StringVar(value=d["filter"])
        full = tk.StringVar(value="on" if d["fullscreen"] else "off")
        cd32 = tk.StringVar(value=d.get("cd32_pad", "default"))
        stop_kp = tk.StringVar(value=d.get("stop_keypresses", "default"))
        center_h = tk.StringVar(value=d.get("screen_center_h", "default"))
        center_v = tk.StringVar(value=d.get("screen_center_v", "default"))
        offset_h = tk.StringVar(value=d.get("screen_offset_h", "default"))
        offset_v = tk.StringVar(value=d.get("screen_offset_v", "default"))

        self._section_label(body, "Display")
        self._dropdown(body, "Fullscreen", full, ["off", "on"])
        self._dropdown(body, "Window scale", scale, SCALE_CHOICES)
        self._dropdown(body, "Filter", filt, FILTER_CHOICES)
        self._dropdown(body, "Center horizontal", center_h, SCREEN_CENTER_CHOICES)
        self._dropdown(body, "Center vertical", center_v, SCREEN_CENTER_CHOICES)
        self._entry_row(body, "Offset horizontal", offset_h)
        self._entry_row(body, "Offset vertical", offset_v)

        self._section_label(body, "Input")
        self._dropdown(body, "Controls", controls, CONTROL_CHOICES, width=22)
        self._dropdown(body, "CD32 pad mode", cd32, CD32_PAD_CHOICES)
        self._dropdown(body, "Block key dupes", stop_kp, STOP_KEYPRESS_CHOICES)

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
            })
            win.destroy()
            self.refresh()

        self._dialog_buttons(win, save)

    def open_game_settings(self, config_path: Path) -> None:
        tk = self.tk
        key = config_path.stem
        g = library.get_game(self.paths, key)
        real = library.title_for(key, None, self.db_by_name)
        win = self._new_dialog(f"Settings - {real}", height=620)

        tk.Label(win, text=real, bg=CARD, fg=TEXT, font=("Sans", 14, "bold"),
                 wraplength=400, justify="left").pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(win, text=key, bg=CARD, fg=MUTED, font=("Sans", 8)).pack(anchor="w", padx=16)
        body = tk.Frame(win, bg=CARD)
        body.pack(fill="x", padx=16, pady=(8, 0))

        name_var = tk.StringVar(value=g.get("display_name", ""))
        row = tk.Frame(body, bg=CARD)
        row.pack(fill="x", pady=4)
        tk.Label(row, text="Display name", bg=CARD, fg=MUTED, font=("Sans", 10), width=12,
                 anchor="w").pack(side="left")
        tk.Entry(row, textvariable=name_var, bg=BG, fg=TEXT, insertbackground=TEXT,
                 relief="flat", font=("Sans", 10), width=26).pack(side="left")

        # "default" defers to the global default for that setting.
        controls = tk.StringVar(value=g.get("controls", "default"))
        full = tk.StringVar(value=g.get("fullscreen_choice", "default"))
        scale = tk.StringVar(value=g.get("scale", "default"))
        filt = tk.StringVar(value=g.get("filter", "default"))
        cd32 = tk.StringVar(value=g.get("cd32_pad", "default"))
        stop_kp = tk.StringVar(value=g.get("stop_keypresses", "default"))
        center_h = tk.StringVar(value=g.get("screen_center_h", "default"))
        center_v = tk.StringVar(value=g.get("screen_center_v", "default"))
        offset_h = tk.StringVar(value=g.get("screen_offset_h", "default"))
        offset_v = tk.StringVar(value=g.get("screen_offset_v", "default"))

        self._section_label(body, "Display")
        self._dropdown(body, "Fullscreen", full, ["default", "off", "on"])
        self._dropdown(body, "Window scale", scale, ["default"] + SCALE_CHOICES)
        self._dropdown(body, "Filter", filt, ["default"] + FILTER_CHOICES)
        self._dropdown(body, "Center horizontal", center_h, ["default"] + SCREEN_CENTER_CHOICES[1:])
        self._dropdown(body, "Center vertical", center_v, ["default"] + SCREEN_CENTER_CHOICES[1:])
        self._entry_row(body, "Offset horizontal", offset_h)
        self._entry_row(body, "Offset vertical", offset_v)

        self._section_label(body, "Input")
        self._dropdown(body, "Controls", controls, ["default"] + CONTROL_CHOICES, width=22)
        self._dropdown(body, "CD32 pad mode", cd32, ["default"] + CD32_PAD_CHOICES[1:])
        self._dropdown(body, "Block key dupes", stop_kp, ["default"] + STOP_KEYPRESS_CHOICES[1:])

        tk.Label(win, text="Notes", bg=CARD, fg=MUTED, font=("Sans", 10)).pack(
            anchor="w", padx=16, pady=(8, 0))
        notes = tk.Text(win, height=5, bg=BG, fg=TEXT, insertbackground=TEXT,
                        relief="flat", font=("Sans", 10), wrap="word")
        notes.pack(fill="both", expand=True, padx=16, pady=(2, 6))
        notes.insert("1.0", g.get("notes", ""))

        def save():
            values: dict = {
                "display_name": name_var.get().strip(),
                "notes": notes.get("1.0", "end").strip(),
                "controls": controls.get(),
                "scale": scale.get(),
                "filter": filt.get(),
                "cd32_pad": cd32.get(),
                "stop_keypresses": stop_kp.get(),
                "screen_center_h": center_h.get(),
                "screen_center_v": center_v.get(),
                "screen_offset_h": offset_h.get().strip() or "default",
                "screen_offset_v": offset_v.get().strip() or "default",
                "fullscreen_choice": full.get(),
            }
            # Translate the tri-state fullscreen choice into the effective setting.
            if full.get() == "on":
                values["fullscreen"] = True
            elif full.get() == "off":
                values["fullscreen"] = False
            else:
                values["fullscreen"] = "default"
            library.set_game(self.paths, key, values)
            win.destroy()
            self.refresh()

        self._dialog_buttons(win, save)

    def _dialog_buttons(self, win, on_save):
        tk = self.tk
        bar = tk.Frame(win, bg=CARD)
        bar.pack(fill="x", side="bottom", padx=16, pady=12)
        tk.Button(bar, text="Save", command=on_save, bg=ACCENT, fg="#ffffff",
                  activebackground=ACCENT_DK, activeforeground="#ffffff", relief="flat",
                  font=("Sans", 11, "bold"), cursor="hand2", borderwidth=0,
                  padx=16, pady=6).pack(side="right", padx=4)
        tk.Button(bar, text="Cancel", command=win.destroy, bg=BG, fg=TEXT,
                  activebackground=CARD_HOVER, activeforeground=TEXT, relief="flat",
                  font=("Sans", 11), cursor="hand2", borderwidth=0,
                  padx=16, pady=6).pack(side="right", padx=4)

    # --- layout / refresh --------------------------------------------------
    def refresh(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows = []

        configs = sorted(list_configs(self.paths), key=lambda p: self._title_for(p).lower())
        for config in configs:
            self._rows.append(self._make_row(config))

        n = len(self._rows)
        amiberry_ok = amiberry.is_installed()
        self.status.configure(
            text=f"{n} game(s)  \u2022  games folder: {self.paths.games}  \u2022  "
                 f"Amiberry: {'ready' if amiberry_ok else 'not installed'}"
        )
        self._update_amiberry_banner()

    def _make_row(self, config_path: Path):
        tk = self.tk
        row = tk.Frame(self.list_frame, bg=CARD, height=ROW_H,
                       highlightbackground="#334155", highlightthickness=1)
        row.pack(fill="x", padx=8, pady=3)
        row.pack_propagate(False)

        play = tk.Button(
            row, text="\u25B6", command=lambda p=config_path: self.play(p),
            bg=ACCENT, fg="#ffffff", activebackground=ACCENT_DK,
            activeforeground="#ffffff", relief="flat", font=("Sans", 14, "bold"),
            cursor="hand2", borderwidth=0, width=2, padx=6, pady=4,
        )
        play.pack(side="left", padx=(10, 12), pady=8)

        info = tk.Frame(row, bg=CARD)
        info.pack(side="left", fill="both", expand=True, pady=8)
        name = self._title_for(config_path)
        tk.Label(info, text=name, bg=CARD, fg=TEXT, font=("Sans", 13, "bold"),
                 anchor="w", justify="left").pack(anchor="w")
        chipset = (_read_field(config_path, "chipset") or "").upper()
        note = library.get_game(self.paths, config_path.stem).get("notes", "")
        subtitle = chipset or "Amiga"
        if note:
            subtitle += "  \u270e"
        tk.Label(info, text=subtitle, bg=CARD, fg=MUTED, font=("Sans", 9)).pack(anchor="w")

        cog = tk.Button(
            row, text="\u2699", command=lambda p=config_path: self.open_game_settings(p),
            bg=CARD, fg=MUTED, activebackground=CARD_HOVER, activeforeground=TEXT,
            relief="flat", font=("Sans", 14), cursor="hand2", borderwidth=0,
            padx=10, pady=4,
        )
        cog.pack(side="right", padx=(4, 10))

        for widget in (row, info, play):
            widget.bind("<Double-Button-1>", lambda e, p=config_path: self.play(p))

        def on_enter(_):
            row.configure(bg=CARD_HOVER)
            info.configure(bg=CARD_HOVER)
            cog.configure(bg=CARD_HOVER)
        def on_leave(_):
            row.configure(bg=CARD)
            info.configure(bg=CARD)
            cog.configure(bg=CARD)
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
