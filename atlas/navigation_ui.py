"""Retractable camera and visible-layer controls over the viewport."""
from math import ceil
import tkinter as tk
from tkinter import font, ttk

from . import theme
from .compass_ui import Compass
from .runtime import LOGGER
from .view_settings import navigation_collapsed, save_navigation_collapsed


class LayerSlider(tk.Canvas):
    def __init__(self, parent, on_select, *, family, mono):
        super().__init__(parent, width=132, height=190, bg=theme.PANEL,
                         highlightthickness=1, highlightbackground=theme.PANEL,
                         takefocus=True, cursor="hand2")
        self.on_select, self.family, self.mono = on_select, family, mono
        self.caption_font = font.Font(self, family=family, size=8)
        self.layers, self.selected = (), None
        self.stops = []
        self._dragging = False
        self._tooltip = self._tooltip_job = None
        self._hovered = None
        self.bind("<Configure>", lambda _: self.draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Up>", lambda _: self._step(-1))
        self.bind("<Down>", lambda _: self._step(1))
        self.bind("<Home>", lambda _: self._choose(0))
        self.bind("<End>", lambda _: self._choose(len(self.layers) - 1))
        self.bind("<Key-a>", lambda _: self._choose(None))
        self.bind("<FocusIn>", lambda _: self.draw())
        self.bind("<FocusOut>", lambda _: self.draw())
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda _: self._hide_tooltip())

    def set_context(self, layers, selected):
        context = tuple(reversed(layers))
        if (context, selected) != (self.layers, self.selected):
            self.layers, self.selected = context, selected
            self._hide_tooltip()
            self.draw()

    def draw(self):
        self.delete("all")
        self.configure(highlightbackground=theme.ACCENT if theme.has_focus(self) else theme.PANEL)
        count = len(self.layers)
        if not count:
            self.stops = []
            return
        height, width = max(70, self.winfo_height()), max(100, self.winfo_width())
        top, bottom = 13, height - 38
        self.stops = [(top + bottom)/2] if count == 1 else [top + (bottom - top)*i/(count - 1) for i in range(count)]
        x = 42
        self.create_line(x, self.stops[0], x, self.stops[-1], fill=theme.BORDER, width=2)
        label_stride = 1 if count <= 8 else max(1, ceil(count / max(1, (bottom - top) / 16)))
        label_size = 7 if count > 1 and (bottom - top)/(count - 1) < 15 else 8
        radius = 4 if count == 1 else min(4, max(1.5, (bottom - top)/(count - 1)/3))
        selected_layer = None
        for index, (layer, y) in enumerate(zip(self.layers, self.stops)):
            active = layer.id == self.selected
            color = theme.ACCENT if active else theme.MUTED
            r = 6 if active else radius
            self.create_oval(x-r, y-r, x+r, y+r, fill=color if active else theme.FIELD,
                             outline=color, width=1, tags=("layer-stop", f"layer-stop:{index}"))
            if active or index in (0, count - 1) or index % label_stride == 0:
                self.create_text(x+19, y, text=f"L{count-index}", fill=color, anchor="w",
                                 font=(self.mono, label_size), tags="layer-label")
            if active:
                selected_layer = (count-index, layer)
        text = f"L{selected_layer[0]} / {selected_layer[1].name}" if selected_layer else "All layers"
        while self.caption_font.measure(text) > width - 12 and len(text) > 3:
            text = text[:-2] + "…"
        self.create_text(width/2, height-15, text=text, fill=theme.ACCENT if selected_layer else theme.MUTED,
                         font=self.caption_font, tags="layer-caption")

    def _choose(self, index):
        if self.layers:
            layer_id = None if index is None else self.layers[max(0, min(len(self.layers)-1, index))].id
            if layer_id != self.selected:
                self.on_select(layer_id)
        return "break"

    def _step(self, direction):
        current = next((i for i, layer in enumerate(self.layers) if layer.id == self.selected), None)
        return self._choose(0 if current is None else current + direction)

    def _at(self, y):
        return min(range(len(self.stops)), key=lambda i: abs(self.stops[i] - y)) if self.stops else None

    def _press(self, event):
        self.focus_set()
        self._hide_tooltip()
        self._dragging = bool(self.stops and event.y <= self.stops[-1] + 12)
        if self._dragging:
            self._choose(self._at(event.y))
        return "break"

    def _drag(self, event):
        if self._dragging:
            self._choose(self._at(event.y))
        return "break"

    def _release(self, event):
        self._drag(event)
        self._dragging = False
        return "break"

    def _hover(self, event):
        index = self._at(event.y)
        if index != self._hovered:
            self._hide_tooltip()
            self._hovered = index
            if index is not None and not self._dragging:
                self._tooltip_job = self.after(400, self._show_tooltip)

    def _show_tooltip(self):
        self._tooltip_job = None
        if self._hovered is None or self._hovered >= len(self.layers):
            return
        layer = self.layers[self._hovered]
        self._tooltip = window = tk.Toplevel(self)
        window.wm_overrideredirect(True)
        window.geometry(f"+{max(0, self.winfo_rootx()-170)}+{self.winfo_rooty()+round(self.stops[self._hovered])+12}")
        tk.Label(window, text=f"L{len(self.layers)-self._hovered} / {layer.name}", bg=theme.FIELD,
                 fg=theme.TEXT, font=(self.family, 9), padx=7, pady=4, relief="solid", borderwidth=1).pack()

    def _hide_tooltip(self):
        if self._tooltip_job is not None:
            self.after_cancel(self._tooltip_job)
            self._tooltip_job = None
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        self._hovered = None

    def cancel_pointer(self):
        self._dragging = False
        self._hide_tooltip()


class NavigationPanel(tk.Frame):
    WIDTH = 146

    def __init__(self, parent, scene, on_render, on_layer, settings_path, *, family, mono, on_status):
        super().__init__(parent, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.BORDER)
        self.on_render, self.settings_path, self.on_status = on_render, settings_path, on_status
        self.collapsed = navigation_collapsed(settings_path)
        self._height = 0
        self.pack_propagate(False)
        self.body = tk.Frame(self, bg=theme.PANEL)
        self.header = tk.Frame(self.body, bg=theme.PANEL)
        self.header.pack(fill="x", padx=5, pady=(4, 0))
        tk.Label(self.header, text="NAVIGATION", bg=theme.PANEL, fg=theme.MUTED, font=(mono, 8)).pack(side="left")
        self.toggle_button = tk.Button(self.header, text="›", command=self.toggle, width=2,
                                      bg=theme.FIELD, fg=theme.TEXT, relief="flat", activebackground=theme.BORDER)
        self.toggle_button.pack(side="right")
        self.compass = Compass(self.body, scene, on_render, family=family, mono=mono, embedded=True)
        self.compass.pack(fill="x", padx=4)
        self.compass.reservation_provider = lambda: self.reserved_box
        ttk.Separator(self.body).pack(fill="x", padx=8, pady=3)
        tk.Label(self.body, text="VISIBLE LAYER", bg=theme.PANEL, fg=theme.MUTED,
                 font=(mono, 8)).pack(pady=(1, 3))
        self.all_button = tk.Button(self.body, text="All", command=lambda: on_layer(None), bg=theme.FIELD,
                                    fg=theme.ACCENT, relief="flat", highlightthickness=1,
                                    highlightbackground=theme.ACCENT, activebackground=theme.BORDER, padx=15, pady=2)
        self.all_button.pack()
        self.slider = LayerSlider(self.body, on_layer, family=family, mono=mono)
        self.slider.pack(fill="both", expand=True, padx=4, pady=(3, 0))
        self.tab = tk.Button(self, text="‹\nNav", command=self.toggle, bg=theme.FIELD, fg=theme.TEXT,
                             activebackground=theme.BORDER, relief="flat", padx=0, pady=0, borderwidth=0,
                             highlightthickness=1, highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT,
                             font=(family, 8))
        self.bind("<Escape>", lambda _: "break")
        self.layout()

    @property
    def reserved_box(self):
        width = self.master.winfo_width()
        if self.collapsed:
            return (width-33, 38, width, 124)
        return (width-self.WIDTH-16, 38, width-8, 42+self._height+4)

    def layout(self):
        available = max(290, self.master.winfo_height() - 58)
        self.compass.set_compact(available < 420)
        height = min(474, available)
        if self.collapsed:
            self.body.pack_forget()
            self.tab.pack(fill="both", expand=True)
            self.place(relx=1, x=-1, y=42, width=28, height=78, anchor="ne")
        else:
            self.tab.pack_forget()
            if not self.body.winfo_manager():
                self.body.pack(fill="both", expand=True)
            self.place(relx=1, x=-12, y=42, width=self.WIDTH, height=height, anchor="ne")
        self._height = height

    def sync(self, layers, selected):
        self.layout()
        self.slider.set_context(layers, selected)
        self.all_button.configure(fg=theme.ACCENT if selected is None else theme.MUTED,
                                  highlightbackground=theme.ACCENT if selected is None else theme.BORDER)
        if not self.collapsed:
            self.compass.draw()

    def toggle(self):
        self.compass._hide_tooltip()
        self.slider.cancel_pointer()
        self.collapsed = not self.collapsed
        self.layout()
        (self.tab if self.collapsed else self.toggle_button).focus_set()
        try:
            save_navigation_collapsed(self.settings_path, self.collapsed)
        except OSError:
            LOGGER.warning("Could not save navigation preference", exc_info=True)
            self.on_status("Navigation changed for this session; its preference could not be saved.")
        self.on_render()
        return "break"

    def close(self):
        self.slider.cancel_pointer()
        self.compass.close()
