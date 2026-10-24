"""A quiet dark palette, reusing the colors of the original HTML prototype."""
import tkinter as tk
from tkinter import font, ttk

from .model import ANGULAR_SLOTS, CENTER_DEPTH, POSITIONS

BG = "#080f1b"
PANEL = "#101c2a"
FIELD = "#152536"
BORDER = "#2b4054"
TEXT = "#dce6ef"
MUTED = "#91a6bb"
ACCENT = "#70cbd8"
GOLD = "#edbb69"
ERROR = "#ee9a9a"


def has_focus(widget: tk.Misc) -> bool:
    """Compare raw Tk paths without resolving temporary combobox popdowns."""
    try:
        return widget.tk.call("focus") == str(widget)
    except tk.TclError:
        return False


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
    style.configure("Compact.TButton", padding=(8, 2))
    style.map("Primary.TButton", background=[("active", "#20505d"), ("pressed", "#235967")])
    # Radio buttons use the Toolbutton layout to form a compact view selector.
    style.layout("View.Toolbutton", style.layout("Toolbutton"))
    style.configure("View.Toolbutton", background=FIELD, foreground=MUTED, bordercolor=BORDER,
                    lightcolor=FIELD, darkcolor=FIELD, padding=(10, 5), borderwidth=1,
                    relief="flat", font=(family, 9))
    style.map("View.Toolbutton",
              background=[("disabled", FIELD), ("selected", ACCENT), ("active", "#20384e")],
              foreground=[("disabled", "#546778"), ("selected", BG), ("active", TEXT)],
              bordercolor=[("selected", ACCENT)],
              lightcolor=[("selected", ACCENT)],
              darkcolor=[("selected", ACCENT)])
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
    style.configure("TNotebook", background=BG, borderwidth=0, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.configure("TNotebook.Tab", background=FIELD, foreground=MUTED, padding=(14, 9),
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", ACCENT)])
    style.configure("Vertical.TScrollbar", background="#355166", troughcolor=FIELD,
                    bordercolor=FIELD, arrowcolor=MUTED)
    style.configure("Horizontal.TScrollbar", background="#355166", troughcolor=FIELD,
                    bordercolor=FIELD, arrowcolor=MUTED)
    return family, mono


class BandSlider(tk.Canvas):
    """Six discrete positions, with stops and labels on the same coordinates."""

    def __init__(self, parent, variable: tk.IntVar, label_font=None):
        super().__init__(parent, height=36, bg=PANEL, highlightthickness=0, takefocus=True)
        self.variable = variable
        self.label_font = label_font or ("TkDefaultFont", 8)
        self._trace_id = variable.trace_add("write", lambda *_: self.draw())
        self.bind("<Configure>", lambda _: self.draw())
        self.bind("<Button-1>", self._pointer)
        self.bind("<B1-Motion>", self._pointer)
        self.bind("<Left>", lambda _: self._step(-1))
        self.bind("<Right>", lambda _: self._step(1))
        self.bind("<Home>", lambda _: self._set(CENTER_DEPTH))
        self.bind("<End>", lambda _: self._set(CENTER_DEPTH + len(POSITIONS) - 1))
        self.bind("<FocusIn>", lambda _: self.draw())
        self.bind("<FocusOut>", lambda _: self.draw())

    def _set(self, value: int) -> str:
        self.variable.set(max(CENTER_DEPTH, min(CENTER_DEPTH + len(POSITIONS) - 1, value)))
        return "break"

    def _step(self, direction: int) -> str:
        return self._set(self.variable.get() + direction)

    def _pointer(self, event) -> str:
        self.focus_set()
        left, right = self._track_bounds()
        return self._set(CENTER_DEPTH + round((event.x - left) / max(1, right - left) * (len(POSITIONS) - 1)))

    def _track_bounds(self) -> tuple[float, float]:
        return 26, max(27, self.winfo_width() - 26)

    def draw(self) -> None:
        self.delete("all")
        left, right = self._track_bounds()
        x = left + (right - left) * (self.variable.get() - CENTER_DEPTH) / (len(POSITIONS) - 1)
        self.create_line(left, 11, right, 11, fill=BORDER, width=3)
        self.create_line(left, 11, x, 11, fill=ACCENT, width=3)
        for index, label in enumerate(POSITIONS):
            stop = left + (right - left) * index / (len(POSITIONS) - 1)
            selected = self.variable.get() == CENTER_DEPTH + index
            self.create_line(stop, 8, stop, 16, fill=ACCENT if selected else MUTED, tags="stop")
            self.create_text(stop, 22, text=label, anchor="n", font=self.label_font,
                             fill=ACCENT if selected else MUTED, tags="label")
        self.create_oval(x - 5, 6, x + 5, 16, fill=ACCENT, outline=ACCENT, tags="handle")
        if has_focus(self):
            self.create_oval(x - 8, 3, x + 8, 19, outline=ACCENT)


class SlotSlider(tk.Canvas):
    """Sixteen snapping start positions with occupancy and footprint feedback."""

    def __init__(self, parent, variable: tk.StringVar, *, on_begin, on_commit, label_font=None):
        super().__init__(parent, height=36, bg=PANEL, highlightthickness=0, takefocus=True)
        self.variable = variable
        self.on_begin, self.on_commit = on_begin, on_commit
        self.label_font = label_font or ("TkDefaultFont", 8)
        self.span = 1
        self.free_starts = frozenset(range(ANGULAR_SLOTS))
        self._dragging = False
        self._trace_id = variable.trace_add("write", lambda *_: self.draw())
        self.bind("<Configure>", lambda _: self.draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Left>", lambda _: self._key(int(self.variable.get()) - 2))
        self.bind("<Right>", lambda _: self._key(int(self.variable.get())))
        self.bind("<Home>", lambda _: self._key(0))
        self.bind("<End>", lambda _: self._key(ANGULAR_SLOTS - 1))
        self.bind("<FocusIn>", lambda _: self.draw())
        self.bind("<FocusOut>", lambda _: self.draw())

    def set_context(self, span: int, free_starts) -> None:
        self.span, self.free_starts = span, frozenset(free_starts)
        self.draw()

    def _track_bounds(self) -> tuple[float, float]:
        return 26, max(27, self.winfo_width() - 26)

    def _set(self, slot: int) -> None:
        self.variable.set(f"{max(0, min(ANGULAR_SLOTS - 1, slot)) + 1:02d}")

    def _pointer(self, event) -> None:
        left, right = self._track_bounds()
        self._set(round((event.x - left) / max(1, right - left) * (ANGULAR_SLOTS - 1)))

    def _press(self, event) -> str:
        self.focus_set()
        self._dragging = True
        self.on_begin()
        self._pointer(event)
        return "break"

    def _drag(self, event) -> str:
        if self._dragging:
            self._pointer(event)
        return "break"

    def _release(self, event) -> str:
        if self._dragging:
            self._pointer(event)
            self._dragging = False
            self.on_commit()
        return "break"

    def _key(self, slot: int) -> str:
        self.on_begin()
        self._set(slot)
        self.on_commit()
        return "break"

    def cancel_drag(self) -> None:
        self._dragging = False

    def draw(self) -> None:
        self.delete("all")
        start = int(self.variable.get()) - 1
        selected = {(start + offset) % ANGULAR_SLOTS for offset in range(self.span)}
        color = ACCENT if start in self.free_starts else ERROR
        left, right = self._track_bounds()
        step = (right - left) / (ANGULAR_SLOTS - 1)
        self.create_line(left, 11, right, 11, fill=BORDER, width=3)
        for slot in range(ANGULAR_SLOTS):
            x = left + slot * step
            if slot in selected:
                if slot > 0 and slot - 1 in selected:
                    self.create_line(x - step, 11, x, 11, fill=color, width=3, tags="range")
                self.create_rectangle(x - 4, 6, x + 4, 16, fill=color, outline="", tags=("footprint", f"slot-{slot}"))
            free = slot in self.free_starts
            self.create_line(x, 8, x, 16, fill=color if slot in selected else MUTED if free else ERROR,
                             tags=("stop", "free" if free else "blocked", f"slot-{slot}"))
            if slot in (0, 3, 7, 11, 15):
                self.create_text(x, 22, text=f"{slot + 1:02d}", anchor="n", font=self.label_font,
                                 fill=color if slot in selected else MUTED, tags="label")
        x = left + start * step
        self.create_oval(x - 5, 6, x + 5, 16, fill=color, outline=color, tags="handle")
        if has_focus(self):
            self.create_oval(x - 8, 3, x + 8, 19, outline=color)
