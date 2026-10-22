"""A quiet dark palette, reusing the colors of the original HTML prototype."""
import tkinter as tk
from tkinter import font, ttk

BG = "#080f1b"
PANEL = "#101c2a"
FIELD = "#152536"
BORDER = "#2b4054"
TEXT = "#dce6ef"
MUTED = "#91a6bb"
ACCENT = "#70cbd8"
GOLD = "#edbb69"
ERROR = "#ee9a9a"


def apply(root: tk.Tk) -> tuple[str, str]:
    families = set(font.families(root))
    family = next((f for f in ("Segoe UI", "SF Pro Text", "DejaVu Sans") if f in families), "TkDefaultFont")
    mono = next((f for f in ("Cascadia Mono", "Consolas", "DejaVu Sans Mono") if f in families), "TkFixedFont")
    root.configure(bg=BG)
    root.option_add("*Font", (family, 10))
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", "#285268")
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=TEXT, font=(family, 10))
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=(family, 9))
    style.configure("TButton", background=FIELD, foreground=TEXT, bordercolor=BORDER,
                    lightcolor=FIELD, darkcolor=FIELD, padding=(13, 7), borderwidth=1, font=(family, 9))
    style.map("TButton", background=[("active", "#20384e"), ("pressed", "#244559")],
              foreground=[("disabled", "#546778")])
    style.configure("Primary.TButton", background="#163c49", foreground=ACCENT, bordercolor="#397a87")
    style.map("Primary.TButton", background=[("active", "#20505d"), ("pressed", "#235967")])
    style.configure("TEntry", fieldbackground=FIELD, foreground=TEXT, bordercolor=BORDER,
                    insertcolor=TEXT, lightcolor=FIELD, darkcolor=FIELD, padding=7)
    style.map("TEntry", bordercolor=[("focus", ACCENT)])
    style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=TEXT,
                    arrowcolor=MUTED, bordercolor=BORDER, lightcolor=FIELD, darkcolor=FIELD, padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)],
              selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", TEXT)])
    style.configure("TCheckbutton", background=PANEL, foreground=MUTED, font=(family, 9),
                    indicatorbackground=FIELD, indicatorforeground=ACCENT, indicatormargin=6)
    style.map("TCheckbutton", background=[("active", PANEL)])
    style.configure("Horizontal.TScale", background=ACCENT, troughcolor=FIELD, bordercolor=FIELD,
                    lightcolor=ACCENT, darkcolor=ACCENT, sliderlength=16, borderwidth=0)
    style.configure("TSeparator", background=BORDER)
    style.configure("Vertical.TScrollbar", background="#355166", troughcolor=FIELD,
                    bordercolor=FIELD, arrowcolor=MUTED)
    return family, mono


class BandSlider(tk.Canvas):
    """A small, keyboard-accessible slider with five discrete positions."""

    def __init__(self, parent, variable: tk.IntVar):
        super().__init__(parent, height=23, bg=PANEL, highlightthickness=0, takefocus=True)
        self.variable = variable
        self._trace_id = variable.trace_add("write", lambda *_: self.draw())
        self.bind("<Configure>", lambda _: self.draw())
        self.bind("<Button-1>", self._pointer)
        self.bind("<B1-Motion>", self._pointer)
        self.bind("<Left>", lambda _: self._step(-1))
        self.bind("<Right>", lambda _: self._step(1))
        self.bind("<Home>", lambda _: self._set(0))
        self.bind("<End>", lambda _: self._set(4))
        self.bind("<FocusIn>", lambda _: self.draw())
        self.bind("<FocusOut>", lambda _: self.draw())

    def _set(self, value: int) -> str:
        self.variable.set(max(0, min(4, value)))
        return "break"

    def _step(self, direction: int) -> str:
        return self._set(self.variable.get() + direction)

    def _pointer(self, event) -> str:
        self.focus_set()
        return self._set(round((event.x - 8) / max(1, self.winfo_width() - 16) * 4))

    def draw(self) -> None:
        self.delete("all")
        width = max(16, self.winfo_width())
        x = 8 + (width - 16) * self.variable.get() / 4
        self.create_line(8, 11, width - 8, 11, fill=BORDER, width=3)
        self.create_line(8, 11, x, 11, fill=ACCENT, width=3)
        self.create_oval(x - 5, 6, x + 5, 16, fill=ACCENT, outline=ACCENT)
        if self.focus_get() == self:
            self.create_oval(x - 8, 3, x + 8, 19, outline=ACCENT)
