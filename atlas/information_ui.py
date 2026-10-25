"""Recorded-entry editor and the two information-heat presentations."""
from math import expm1, log1p
import tkinter as tk
from tkinter import messagebox, ttk

from . import theme
from .heat import CLUSTER_SUPPORT_LIMIT, HEAT_STOPS, InformationHeat, heat_color
from .model import AtlasError, InformationEntry


class InformationManager:
    def __init__(self, app):
        self.app = app
        self.dialog = None
        self.owner_id = self.entry_id = None
        self.entry_ids = []
        self._loaded = ("", "")
        self._headers = []
        self.color_mode = tk.StringVar(value="Layer colors")
        self.bar = ttk.Frame(app.canvas.master, style="Panel.TFrame", padding=(10, 5))
        ttk.Label(self.bar, text="Color", style="Muted.TLabel").pack(side="left", padx=(0, 8))
        self.color_box = ttk.Combobox(self.bar, textvariable=self.color_mode, state="readonly", width=19,
                                     values=("Layer colors", "Information heat"))
        self.color_box.pack(side="left")
        self.color_box.bind("<<ComboboxSelected>>", self.change_color)
        ttk.Label(self.bar, text="Recorded entries", style="Muted.TLabel").pack(side="right")
        self.legend = tk.Canvas(app.canvas.master, bg=theme.PANEL, height=54, highlightthickness=0)
        self._attach_header(app.editor_form, 8)
        self._attach_header(app.clusters.form, 6)

    def _attach_header(self, parent, row):
        for widget in parent.grid_slaves(row=row, column=0):
            widget.grid_remove()
        header = ttk.Frame(parent, style="Panel.TFrame")
        header.grid(row=row, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        caption = ttk.Label(header, text="Personal notes", style="Muted.TLabel")
        caption.grid(row=0, column=0, sticky="w")
        button = ttk.Button(header, text="Entries (0)", style="Inline.TButton", command=self.open)
        button.grid(row=0, column=1, sticky="e")
        panel = ttk.Frame(header, style="Panel.TFrame")
        panel.columnconfigure(1, weight=1)
        sample = tk.Canvas(panel, width=66, height=66, bg=theme.PANEL, highlightthickness=0)
        sample.grid(row=0, column=0)
        summary = ttk.Label(panel, style="Muted.TLabel", justify="left")
        summary.grid(row=0, column=1, sticky="w", padx=(5, 0))
        notes_caption = ttk.Label(header, text="Personal notes", style="Muted.TLabel")
        self._headers.append((button, panel, sample, summary, caption, notes_caption))

    def selected_id(self):
        return self.app.clusters.child_id if self.app.clusters.editing else self.app.selected

    def concept(self, identity):
        return self.app.document.get(identity) or self.app.document.child(identity)

    def change_color(self, _event=None):
        self.app.scene.set_heat_enabled(self.color_mode.get() == "Information heat")
        self.app.request_render()

    def sync(self):
        app, scene = self.app, self.app.scene
        available = scene.mode == "nodes" and app._template_origin is None
        self.bar.grid(row=1, column=0, sticky="ew") if available else self.bar.grid_remove()
        self.legend.grid(row=4, column=0, sticky="ew") if scene.heat_active else self.legend.grid_remove()
        identity = self.selected_id()
        metric = scene.heat_metrics.get(identity, InformationHeat())
        cluster_total = metric.own + sum(scene.heat_metrics.get(child.id, InformationHeat()).own
                                       for child in app.document.children(identity))
        inspecting = (app._node_move_origin is None and not app.clusters.moving
                      and app.placement_state != "placing")
        for button, panel, sample, summary, caption, notes_caption in self._headers:
            button.configure(text=f"Entries ({metric.own})")
            button.state(["!disabled"] if self.concept(identity) and app._template_origin is None else ["disabled"])
            if available and scene.heat_active and inspecting and self.concept(identity):
                caption.configure(text="Recorded information")
                panel.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 3))
                notes_caption.grid(row=2, column=0, columnspan=2, sticky="w")
                summary.configure(text=f"Own entries: {metric.own}\nSupport: {metric.support:g} / 4\nCluster entries: {cluster_total}")
                self._sample(sample, identity, metric)
            else:
                caption.configure(text="Personal notes")
                panel.grid_remove()
                notes_caption.grid_remove()

    def _sample(self, canvas, identity, metric):
        canvas.delete("all")
        canvas.create_oval(14, 14, 52, 52, fill=heat_color(metric.own), outline="")
        if self.app.document.children(identity):
            canvas.create_oval(9, 9, 57, 57, outline=theme.BORDER, width=2)
            if metric.support:
                canvas.create_arc(9, 9, 57, 57, start=90, extent=-360 * metric.support / CLUSTER_SUPPORT_LIMIT,
                                  style="arc", outline=theme.GOLD, width=2)
        canvas.create_oval(5, 5, 61, 61, outline=theme.TEXT, width=1)

    def draw(self):
        scene, canvas = self.app.scene, self.app.canvas
        if not scene.heat_active:
            return
        legend = self.legend
        legend.delete("all")
        width = max(300, legend.winfo_width())
        left, right = 138, width - 20
        legend.create_text(10, 13, text="Recorded entries", anchor="w", fill=theme.TEXT,
                           font=(self.app.family, 9))
        for step in range(100):
            start = left + (right-left) * step / 100
            end = left + (right-left) * (step+1) / 100
            value = expm1(log1p(32) * (step + .5) / 100)
            legend.create_rectangle(start, 9, end+1, 16, fill=heat_color(value), outline="")
        for count, _ in HEAT_STOPS:
            x = left + (right-left) * log1p(count) / log1p(32)
            legend.create_text(x, 26, text=f"{count}{'+' if count == 32 else ''}", fill=theme.MUTED,
                               font=(self.app.mono, 8))
        focused = scene.focused_parent is not None
        caption = ("Focus: fill = own entries; rim = support (max 4)." if focused else
                   "Overview: own entries + capped support. Fixed scale.")
        legend.create_text(10, 45, text=caption, anchor="w", fill=theme.MUTED, font=(self.app.family, 8))
        if focused:
            parent = scene.orbit_parent()
            if parent is not None and scene.is_visible(parent):
                x, y, depth = scene.project(scene.node_anchor(parent))
                if 0 <= depth <= 1 and scene.pick(x, y) == parent.id:
                    metric = scene.heat_metrics.get(parent.id, InformationHeat())
                    radius = .065 * scene.height / (2 * scene.scale) + 3
                    bounds = x-radius, y-radius, x+radius, y+radius
                    canvas.create_oval(*bounds, outline=theme.BORDER, width=2, tags=("overlay", "support-rim"))
                    if metric.support:
                        canvas.create_arc(*bounds, start=90, extent=-360 * metric.support / CLUSTER_SUPPORT_LIMIT,
                                          style="arc", outline=theme.GOLD, width=2, tags=("overlay", "support-arc"))

    def open(self):
        if self.app._template_origin is not None:
            return False
        if self.dialog is not None:
            self.dialog.lift()
            return True
        identity = self.selected_id()
        owner = self.concept(identity)
        if owner is None:
            return False
        self.owner_id, self.entry_id = identity, None
        dialog = self.dialog = tk.Toplevel(self.app.root)
        dialog.title(f"Information entries - {owner.name}")
        dialog.transient(self.app.root)
        dialog.geometry("760x590")
        dialog.minsize(640, 480)
        dialog.configure(bg=theme.BG)
        dialog.protocol("WM_DELETE_WINDOW", self.close)
        dialog.bind("<Escape>", lambda _: self.close())
        dialog.bind("<Control-s>", lambda _: (self.save(), "break")[1])
        outer = ttk.Frame(dialog, padding=14)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(2, weight=1)
        self.dialog_summary = ttk.Label(outer, text="", style="Muted.TLabel", wraplength=700)
        self.dialog_summary.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(outer, text="Saved entries", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(outer, text="Entry title", style="Muted.TLabel").grid(row=1, column=1, sticky="w")
        listing = ttk.Frame(outer)
        listing.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        listing.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(listing, width=25, exportselection=False, bg=theme.FIELD, fg=theme.TEXT,
                                  selectbackground="#29556a", relief="flat", font=(self.app.family, 10))
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(listing, command=self.listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.bind("<<ListboxSelect>>", self.select_entry)
        field = ttk.Frame(outer)
        field.grid(row=2, column=1, sticky="nsew")
        field.columnconfigure(0, weight=1)
        field.rowconfigure(2, weight=1)
        self.title = tk.StringVar()
        self.title_entry = ttk.Entry(field, textvariable=self.title)
        self.title_entry.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(field, text="Information", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        body_frame = ttk.Frame(field)
        body_frame.grid(row=2, column=0, sticky="nsew", pady=(4, 0))
        body_frame.columnconfigure(0, weight=1)
        body_frame.rowconfigure(0, weight=1)
        self.body = tk.Text(body_frame, width=35, height=12, wrap="word", undo=True, bg=theme.FIELD,
                            fg=theme.TEXT, insertbackground=theme.TEXT, relief="flat", padx=10, pady=10,
                            font=(self.app.family, 10))
        self.body.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body_frame, command=self.body.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.body.configure(yscrollcommand=scroll.set)
        self.status = ttk.Label(outer, text="", style="Muted.TLabel", wraplength=700)
        self.status.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 8))
        buttons = ttk.Frame(outer)
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew")
        ttk.Button(buttons, text="New entry", command=self.new).pack(side="left")
        self.copy_button = ttk.Button(buttons, text="Use notes as one entry", command=self.use_notes)
        self.copy_button.pack(side="left", padx=5)
        self.copy_button.state(["!disabled"] if owner.notes.strip() else ["disabled"])
        ttk.Button(buttons, text="Close", command=self.close).pack(side="right")
        self.delete_button = ttk.Button(buttons, text="Delete entry", command=self.delete)
        self.delete_button.pack(side="right", padx=5)
        ttk.Button(buttons, text="Save entry", style="Primary.TButton", command=self.save).pack(side="right")
        def wrap_labels(event):
            width = max(250, event.width - 30)
            self.dialog_summary.configure(wraplength=width)
            self.status.configure(wraplength=width)
        outer.bind("<Configure>", wrap_labels)
        self._load(None)
        self.refresh_list()
        dialog.update_idletasks()
        dialog.grab_set()
        self.title_entry.focus_set()
        return True

    def state(self):
        return self.title.get(), self.body.get("1.0", "end-1c")

    @property
    def dirty(self):
        return self.dialog is not None and self.state() != self._loaded

    def _load(self, entry):
        self.entry_id = entry.id if entry else None
        self.title.set(entry.title if entry else "")
        self.body.delete("1.0", "end")
        self.body.insert("1.0", entry.body if entry else "")
        self.body.edit_reset()
        self._loaded = self.state()
        self.status.configure(text="Each saved entry counts once. Personal notes are kept separately.")
        self.delete_button.state(["!disabled"] if entry else ["disabled"])

    def refresh_list(self):
        entries = self.app.document.entries_for(self.owner_id)
        self.entry_ids = [entry.id for entry in entries]
        self.listbox.delete(0, "end")
        for entry in entries:
            self.listbox.insert("end", entry.title)
        if self.entry_id in self.entry_ids:
            self.listbox.selection_set(self.entry_ids.index(self.entry_id))
        self.dialog_summary.configure(text=f"{self.concept(self.owner_id).name} / {len(entries)} recorded entries. "
                                     "Add one explanation, observation or example per entry.")

    def allow_leave(self):
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved information", "Save this information entry before continuing?", parent=self.dialog)
        return self.save() if answer is True else answer is False

    def new(self):
        if not self.allow_leave():
            return False
        self._load(None)
        self.listbox.selection_clear(0, "end")
        self.title_entry.focus_set()
        return True

    def select_entry(self, _event=None):
        selection = self.listbox.curselection()
        if not selection:
            return False
        identity = self.entry_ids[selection[0]]
        if identity == self.entry_id:
            return True
        if not self.allow_leave():
            self.listbox.selection_clear(0, "end")
            if self.entry_id in self.entry_ids:
                self.listbox.selection_set(self.entry_ids.index(self.entry_id))
            return False
        entry = next(entry for entry in self.app.document.entries_for(self.owner_id) if entry.id == identity)
        self._load(entry)
        return True

    def save(self):
        if self.entry_id and not self.dirty:
            return True
        try:
            title, body = self.state()
            entry = (InformationEntry(self.entry_id, self.owner_id, title.strip(), body) if self.entry_id else
                     InformationEntry.create(self.owner_id, title, body))
            document = self.app.document.with_entry(entry)
        except AtlasError as exc:
            self.status.configure(text=str(exc))
            return False
        if not self.app._commit(document):
            return False
        self.entry_id = entry.id
        self._loaded = self.state()
        self.delete_button.state(["!disabled"])
        self.refresh_list()
        self.status.configure(text="Saved. Editing this entry keeps its count at one.")
        self.app.request_render()
        return True

    def delete(self):
        if self.entry_id is None:
            return False
        if not messagebox.askyesno("Delete entry", "Delete this saved information entry and discard its draft?\n\nPersonal notes are kept.", parent=self.dialog):
            return False
        if not self.app._commit(self.app.document.without_entry(self.entry_id)):
            return False
        self._load(None)
        self.refresh_list()
        self.app.request_render()
        return True

    def use_notes(self):
        owner = self.concept(self.owner_id)
        if not owner.notes.strip() or not self.new():
            return False
        self.title.set(owner.name)
        self.body.insert("1.0", owner.notes)
        self.status.configure(text="Notes copied into one draft entry. Save entry to count it; the original notes are kept.")
        return True

    def close(self):
        if self.dialog is None:
            return True
        if not self.allow_leave():
            return False
        self.dialog.grab_release()
        self.dialog.destroy()
        self.dialog = None
        return True
