"""A fixed-size, clickable camera compass, independent of saved atlas data."""
from math import hypot, pi
from time import monotonic
import tkinter as tk

from . import theme
from .orientation import (
    DEFAULT_ELEVATION, DEFAULT_YAW, aligned_view, axis_orientation, camera_basis,
)


class Compass(tk.Canvas):
    WIDTH, HEIGHT = 132, 168
    DURATION = .22

    def __init__(self, parent, scene, on_change, *, family, mono, embedded=False):
        super().__init__(parent, width=self.WIDTH, height=self.HEIGHT, bg=theme.PANEL,
                         highlightthickness=1, highlightbackground=theme.BORDER,
                         takefocus=True, cursor="hand2")
        self.scene, self.on_change = scene, on_change
        self.family, self.mono = family, mono
        self._job = None
        self._goal = None
        self._last_angles = None
        self._pressed = None
        self._hovered = None
        self._tooltip = None
        self._tooltip_job = None
        self.hits = {}
        self.compact = False
        self.reservation_provider = None
        if not embedded:
            self.place(relx=1, x=-12, y=42, anchor="ne")
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", self._leave)
        self.bind("<FocusIn>", lambda _: self.draw())
        self.bind("<FocusOut>", lambda _: self.draw())
        for axis in "xyz":
            self.bind(f"<Key-{axis}>", lambda _, a=axis: self.activate(a.upper()))
        self.bind("<Home>", lambda _: self.activate("home"))
        self.bind("<Escape>", lambda _: self.cancel_animation())
        self.draw()

    @property
    def reserved_box(self):
        if self.reservation_provider is not None:
            return self.reservation_provider()
        width = self.master.winfo_width()
        return (width - self.WIDTH - 16, 38, width - 8, 42 + self.HEIGHT + 5)

    def set_compact(self, compact):
        if self.compact != compact:
            self.compact = compact
            self.configure(height=128 if compact else self.HEIGHT)
            self.draw()

    def _next_view(self, axis):
        current = self._goal or aligned_view(self.scene.yaw, self.scene.elevation)
        sign = -current[1] if current and current[0] == axis else 1
        return axis, sign

    def activate(self, key):
        """Animate orientation only: zoom, pan, focus and documents stay intact."""
        goal = self._next_view(key) if key != "home" else None
        self.cancel_animation()
        self._hide_tooltip()
        target = axis_orientation(*goal) if goal else (DEFAULT_YAW, DEFAULT_ELEVATION)
        self._goal = goal
        start = (self.scene.yaw, self.scene.elevation)
        yaw_delta = (target[0] - start[0] + pi) % (2 * pi) - pi
        started = monotonic()
        self._last_angles = start

        def tick():
            self._job = None
            if (self.scene.yaw, self.scene.elevation) != self._last_angles:
                self.cancel_animation()
                return
            amount = min(1.0, (monotonic() - started) / self.DURATION)
            eased = amount * amount * (3 - 2 * amount)
            self.scene.yaw = target[0] if amount == 1 else start[0] + yaw_delta * eased
            self.scene.elevation = target[1] if amount == 1 else start[1] + (target[1] - start[1]) * eased
            self.scene._apply_camera()
            self._last_angles = (self.scene.yaw, self.scene.elevation)
            if amount == 1:
                self._goal = None
            else:
                self._job = self.after(16, tick)
            self.draw()
            self.on_change()

        tick()
        return "break"

    def cancel_animation(self):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        self._goal = None
        return "break"

    def draw(self):
        if self._job is not None and (self.scene.yaw, self.scene.elevation) != self._last_angles:
            self.cancel_animation()
        self.delete("all")
        self.configure(highlightbackground=theme.ACCENT if theme.has_focus(self) else theme.BORDER)
        self.create_text(66, 10 if self.compact else 13, text="ORIENTATION", fill=theme.MUTED, font=(self.mono, 8))
        right, up, toward = camera_basis(self.scene.yaw, self.scene.elevation)
        active = aligned_view(self.scene.yaw, self.scene.elevation)
        origin = (66, 56 if self.compact else 67)
        length, radius = (30, 8) if self.compact else (34, 12)
        points = {axis: [origin[0] + length * right[i], origin[1] - length * up[i]]
                  for i, axis in enumerate("XYZ")}
        # Near-coincident projections still need separate, usable click targets.
        minimum = 21 if self.compact else 27
        for _ in range(4):
            for a, b in (("X", "Y"), ("X", "Z"), ("Y", "Z")):
                dx, dy = points[a][0]-points[b][0], points[a][1]-points[b][1]
                distance = hypot(dx, dy)
                if distance < minimum:
                    ux, uy = (dx/distance, dy/distance) if distance > 1e-6 else (1, 0)
                    shift = (minimum-distance)/2
                    points[a][0] += ux*shift
                    points[a][1] += uy*shift
                    points[b][0] -= ux*shift
                    points[b][1] -= uy*shift
        for i in sorted(range(3), key=lambda i: toward[i]):
            axis = "XYZ"[i]
            x, y = points[axis]
            self.create_line(*origin, x, y, fill=theme.MUTED, width=1, arrow="last")
            selected = active is not None and active[0] == axis
            color = theme.ACCENT if selected or self._hovered == axis else theme.MUTED
            self.create_oval(x - radius, y - radius, x + radius, y + radius, fill=theme.FIELD,
                             outline=color, width=2 if selected else 1, tags=f"axis-{axis}")
            self.create_text(x, y, text=axis, fill=color, font=(self.mono, 10, "bold"), tags=f"axis-{axis}")
        self.hits = {axis: (x - radius-2, y - radius-2, x + radius+2, y + radius+2) for axis, (x, y) in points.items()}
        caption = f"Viewing {'+' if active[1] > 0 else '-'}{active[0]}" if active else "Click X, Y or Z"
        if not self.compact:
            self.create_text(66, 112, text=caption, fill=theme.ACCENT if active else theme.MUTED, font=(self.family, 8))
        self.hits["home"] = (28, 100, 104, 124) if self.compact else (28, 129, 104, 156)
        self.create_rectangle(*self.hits["home"], fill=theme.FIELD,
                              outline=theme.ACCENT if self._hovered == "home" else theme.BORDER)
        self.create_text(66, 112 if self.compact else 142, text="⌂  Home", fill=theme.TEXT, font=(self.family, 9))

    def hit(self, x, y):
        return next((key for key, (x0, y0, x1, y1) in self.hits.items()
                     if x0 <= x <= x1 and y0 <= y <= y1), None)

    def _press(self, event):
        self.focus_set()
        self._pressed = self.hit(event.x, event.y)
        self._press_point = (event.x, event.y)
        self._hide_tooltip()
        return "break"

    def _release(self, event):
        if self._pressed and self._pressed == self.hit(event.x, event.y):
            if hypot(event.x - self._press_point[0], event.y - self._press_point[1]) < 4:
                self.activate(self._pressed)
        self._pressed = None
        return "break"

    def _motion(self, event):
        hovered = self.hit(event.x, event.y)
        if hovered != self._hovered:
            self._hide_tooltip()
            self._hovered = hovered
            self.draw()
            if hovered:
                self._tooltip_job = self.after(400, self._show_tooltip)
        self.configure(cursor="hand2" if hovered else "arrow")

    def _show_tooltip(self):
        self._tooltip_job = None
        if not self._hovered:
            return
        if self._hovered == "home":
            text = "Default angled view · keep zoom and focus"
        else:
            axis, sign = self._next_view(self._hovered)
            text = f"View from {'+' if sign > 0 else '-'}{axis} · click again to flip"
            if axis == "Z":
                text += "\nLayers overlap; X or Y separates the layers."
        self._tooltip = window = tk.Toplevel(self)
        window.wm_overrideredirect(True)
        window.geometry(f"+{max(0, self.winfo_rootx() - 155)}+{self.winfo_rooty() + self.HEIGHT + 5}")
        tk.Label(window, text=text, bg=theme.FIELD, fg=theme.TEXT, font=(self.family, 9),
                 padx=8, pady=5, relief="solid", borderwidth=1).pack()

    def _hide_tooltip(self):
        if self._tooltip_job is not None:
            self.after_cancel(self._tooltip_job)
            self._tooltip_job = None
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None

    def _leave(self, _event):
        self._hovered = None
        self._hide_tooltip()
        self.draw()

    def close(self):
        self.cancel_animation()
        self._hide_tooltip()
