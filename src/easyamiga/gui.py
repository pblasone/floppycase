"""A simple, friendly desktop GUI for easyamiga.

The window scans the games folder and shows each game as a big, clickable
"Play" tile. It's intentionally simple so it's usable by kids and adults alike:
open it, and your games are there to click.

Built with Tkinter so it has no extra Python dependencies (it only needs the
system ``python3-tk`` package, which ``easyamiga install`` sets up).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from . import amiberry, install as install_mod
from .games import add_game, discover_game_sources, list_configs, resolve_launch, scan_games
from .models import DEFAULT_MODEL, MODELS, get_model
from .paths import Paths
from .roms import DetectedRom, default_model_key, detect_roms, pick_rom_for_model

# Palette (Amiga-ish dark blue with a boing-ball red accent)
BG = "#0f172a"
CONTENT_BG = "#0b1220"
CARD = "#1e293b"
CARD_HOVER = "#273449"
ACCENT = "#ff2d2d"
ACCENT_DK = "#b30000"
TEXT = "#f8fafc"
MUTED = "#94a3b8"

CARD_W = 250
CARD_H = 150


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
        self._cards: list[tk.Widget] = []
        self._columns = 3

        self.root = tk.Tk()
        self.root.title("easyamiga")
        self.root.geometry("900x620")
        self.root.minsize(560, 420)
        self.root.configure(bg=BG)

        self._build_header()
        self._build_toolbar()
        self._build_grid()
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

    def _build_toolbar(self) -> None:
        tk = self.tk
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=18, pady=(6, 10))

        tk.Label(bar, text="Machine:", bg=BG, fg=MUTED,
                 font=("Sans", 10)).pack(side="left")
        default_model = default_model_key(detect_roms(self.roms_dir), DEFAULT_MODEL)
        self.model_var = tk.StringVar(value=default_model)
        model_menu = tk.OptionMenu(bar, self.model_var, *MODELS.keys())
        model_menu.configure(bg=CARD, fg=TEXT, activebackground=CARD_HOVER,
                             activeforeground=TEXT, highlightthickness=0,
                             relief="flat", font=("Sans", 10), width=7)
        model_menu["menu"].configure(bg=CARD, fg=TEXT)
        model_menu.pack(side="left", padx=(6, 16))

        self._toolbar_button(bar, "\u21bb  Scan games folder", self.do_scan)
        self._toolbar_button(bar, "+  Add game file", self.add_file)
        self._toolbar_button(bar, "+  Add game folder", self.add_folder)
        self._toolbar_button(bar, "\U0001F4C1  Open games folder", self.open_games)

    def _toolbar_button(self, parent, text, command):
        tk = self.tk
        btn = tk.Button(parent, text=text, command=command, bg=CARD, fg=TEXT,
                        activebackground=CARD_HOVER, activeforeground=TEXT,
                        relief="flat", font=("Sans", 10), padx=10, pady=6,
                        cursor="hand2", borderwidth=0)
        btn.pack(side="left", padx=4)
        return btn

    def _build_grid(self) -> None:
        tk = self.tk
        container = tk.Frame(self.root, bg=CONTENT_BG)
        container.pack(fill="both", expand=True, padx=10, pady=4)

        self.banner = tk.Label(container, text="", bg="#7f1d1d", fg=TEXT,
                               font=("Sans", 10, "bold"), anchor="w", padx=12)

        self.canvas = tk.Canvas(container, bg=CONTENT_BG, highlightthickness=0)
        self.scroll = self.ttk.Scrollbar(container, orient="vertical",
                                         command=self.canvas.yview)
        self.grid_frame = tk.Frame(self.canvas, bg=CONTENT_BG)
        self._grid_window = self.canvas.create_window((0, 0), window=self.grid_frame,
                                                      anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

        self.grid_frame.bind(
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
    def _current_rom(self, model_key: str) -> Optional[DetectedRom]:
        return pick_rom_for_model(detect_roms(self.roms_dir), model_key)

    def do_scan(self, announce: bool = True) -> None:
        from tkinter import messagebox

        model = get_model(self.model_var.get())
        rom = self._current_rom(model.key)
        games = scan_games(self.paths, model, rom=rom, roms_dir=self.roms_dir)
        added = sum(1 for g in games if g.newly_created)
        self.refresh()
        if announce:
            messagebox.showinfo(
                "Scan complete",
                f"Found {len(games)} game(s) in your games folder.\n"
                f"Added {added} new one(s).",
            )

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

        model = get_model(self.model_var.get())
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

        source, kind = resolve_launch(self.paths, config_path)
        try:
            if kind == "whdload" and source is not None:
                # WHDLoad game: boot via Amiberry's WHDLoad Booter (--autoload),
                # regardless of what a stale config said.
                install_mod.sync_kickstarts(self.paths, log=lambda *_: None)
                amiberry.launch_game(source, kind, wait=False)
            else:
                # ADF game (boots the floppy) or a bare machine: use the config.
                amiberry.launch(config_path, wait=False)
        except FileNotFoundError as exc:
            messagebox.showerror("Could not launch game", str(exc))

    # --- layout / refresh --------------------------------------------------
    def refresh(self) -> None:
        for card in self._cards:
            card.destroy()
        self._cards = []

        for config in list_configs(self.paths):
            self._cards.append(self._make_card(config))
        self._reflow()

        n = len(self._cards)
        amiberry_ok = amiberry.is_installed()
        self.status.configure(
            text=f"{n} game(s)  \u2022  games folder: {self.paths.games}  \u2022  "
                 f"Amiberry: {'ready' if amiberry_ok else 'not installed'}"
        )
        self._update_amiberry_banner()

    def _make_card(self, config_path: Path):
        tk = self.tk
        card = tk.Frame(self.grid_frame, bg=CARD, width=CARD_W, height=CARD_H,
                        highlightbackground="#334155", highlightthickness=1)
        card.pack_propagate(False)

        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", padx=12, pady=(12, 4))
        badge = tk.Canvas(top, width=34, height=34, bg=CARD, highlightthickness=0)
        badge.pack(side="left")
        self._draw_boing(badge, 17, 17, 14)

        name = _label_for(config_path)
        info = tk.Frame(top, bg=CARD)
        info.pack(side="left", fill="x", padx=8)
        tk.Label(info, text=name, bg=CARD, fg=TEXT, font=("Sans", 12, "bold"),
                 anchor="w", justify="left", wraplength=150).pack(anchor="w")
        chipset = (_read_field(config_path, "chipset") or "").upper()
        tk.Label(info, text=chipset or "Amiga", bg=CARD, fg=MUTED,
                 font=("Sans", 9)).pack(anchor="w")

        play = tk.Button(card, text="\u25B6  Play", command=lambda p=config_path: self.play(p),
                         bg=ACCENT, fg="#ffffff", activebackground=ACCENT_DK,
                         activeforeground="#ffffff", relief="flat",
                         font=("Sans", 12, "bold"), cursor="hand2", borderwidth=0)
        play.pack(side="bottom", fill="x", padx=12, pady=12)

        for widget in (card, top, info, badge):
            widget.bind("<Double-Button-1>", lambda e, p=config_path: self.play(p))

        def on_enter(_):
            card.configure(bg=CARD_HOVER)
        def on_leave(_):
            card.configure(bg=CARD)
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)
        return card

    def _reflow(self) -> None:
        for i, card in enumerate(self._cards):
            r, c = divmod(i, max(1, self._columns))
            card.grid(row=r, column=c, padx=10, pady=10, sticky="nw")

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._grid_window, width=event.width)
        cols = max(1, event.width // (CARD_W + 20))
        if cols != self._columns:
            self._columns = cols
            self._reflow()

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
