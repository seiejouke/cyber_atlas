"""A separate, read-only scene for browsing committed atlas revisions."""
from __future__ import annotations

from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import theme
from .history import HistoryStore
from .model import AtlasError
from .scene import Scene


def local_time(value, *, include_zone=True):
    return datetime.fromisoformat(value).astimezone().strftime("%d %b %Y %H:%M:%S" + (" %Z" if include_zone else ""))


class HistoryManager:
    def __init__(self, app):
        self.app = app
        self.store = HistoryStore(app.path)
        self.dialog = None
        self.scene = None
        self._render_job = None
        self._image = None
        self.current_revision = None
        try:
            self.store.initialize(app.document)
        except (OSError, AtlasError) as exc:
            messagebox.showwarning("History unavailable", f"Your atlas is open, but history could not start.\n\n{exc}\n\nSaving will retry history recording. Export JSON remains available.", parent=app.root)

    def open(self):
        if self.dialog is not None:
            self.dialog.lift()
            return True
        if self.app._template_origin is not None or not self.app._allow_leave():
            return False
        # Discard was explicitly chosen; do not leave a stale draft behind the browser.
        if self.app.clusters.editing or self.app.dirty:
            self.app._load_editor(self.app.document.get(self.app.selected))
        try:
            self.store.initialize(self.app.document)
            self.revisions = self.store.revisions()
        except (OSError, AtlasError) as exc:
            messagebox.showerror("Could not open history", str(exc), parent=self.app.root)
            return False
        self._build()
        self._populate()
        return True

    def _build(self):
        app = self.app
        self.dialog = window = tk.Toplevel(app.root)
        window.title("Atlas history — read-only")
        window.transient(app.root)
        window.geometry("1250x800")
        window.minsize(1020, 700)
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.bind("<Escape>", lambda _: self.close())
        outer = ttk.Frame(window, padding=14)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(3, weight=1)
        outer.columnconfigure(0, weight=1)
        ttk.Label(outer, text="HISTORY / READ-ONLY", font=(app.mono, 11)).grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text="Browsing leaves your current atlas untouched. Restore creates a new saved revision.").grid(row=1, column=0, sticky="w", pady=(5, 10))
        tools = ttk.Frame(outer)
        tools.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.older_button = ttk.Button(tools, text="← Previous", command=lambda: self.step(1))
        self.older_button.pack(side="left")
        self.newer_button = ttk.Button(tools, text="Next →", command=lambda: self.step(-1))
        self.newer_button.pack(side="left", padx=5)
        self.mode_var = tk.StringVar(value=app.scene.mode.title())
        mode = ttk.Combobox(tools, textvariable=self.mode_var, values=("Nodes", "Blocks"), state="readonly", width=8)
        mode.pack(side="left", padx=(12, 6))
        mode.bind("<<ComboboxSelected>>", lambda _: self.change_view())
        self.reset_button = ttk.Button(tools, text="Reset view", command=self.reset_view)
        self.reset_button.pack(side="left", padx=(0, 6))
        self.heat_var = tk.BooleanVar(value=app.scene.heat_enabled)
        self.heat_check = ttk.Checkbutton(tools, text="Information heat (Nodes)", variable=self.heat_var, command=self.change_view)
        self.heat_check.pack(side="left")
        self.heat_check.state(["!disabled" if app.scene.mode == "nodes" else "disabled"])
        self.export_button = ttk.Button(tools, text="Export with history…", command=self.export)
        self.export_button.pack(side="right")
        self.restore_button = ttk.Button(tools, text="Restore this version…", command=self.restore)
        self.restore_button.pack(side="right", padx=6)
        panels = ttk.Panedwindow(outer, orient="horizontal")
        panels.grid(row=3, column=0, sticky="nsew")
        left, middle, right = (ttk.Frame(panels) for _ in range(3))
        panels.add(left, weight=2)
        panels.add(middle, weight=4)
        panels.add(right, weight=2)
        for pane in (left, middle, right):
            pane.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Saved revisions · newest first").grid(row=0, column=0, sticky="w", pady=5)
        style = ttk.Style(window)
        style.configure("History.Treeview", background=theme.FIELD, fieldbackground=theme.FIELD,
                        foreground=theme.TEXT, bordercolor=theme.BORDER, rowheight=27, font=(app.family, 9))
        style.map("History.Treeview", background=[("selected", "#214f5d")], foreground=[("selected", theme.ACCENT)])
        style.configure("History.Treeview.Heading", background=theme.PANEL, foreground=theme.MUTED,
                        relief="flat", font=(app.family, 9))
        style.map("History.Treeview.Heading", background=[("active", theme.FIELD)])
        self.tree = ttk.Treeview(left, columns=("number", "time"), show="headings", selectmode="browse", height=10, style="History.Treeview")
        self.tree.heading("number", text="Revision")
        self.tree.heading("time", text="Recorded locally")
        self.tree.column("number", width=64, minwidth=52, stretch=False)
        self.tree.column("time", width=176, minwidth=125)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._selected_revision)
        self.change_text = ScrolledText(left, height=9, width=27, wrap="word", bg=theme.FIELD, fg=theme.TEXT, relief="flat", font=(app.family, 9))
        self.change_text.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        middle.rowconfigure(1, weight=1)
        self.heading = ttk.Label(middle, text="", wraplength=450)
        self.heading.grid(row=0, column=0, sticky="ew", padx=9, pady=5)
        self.canvas = tk.Canvas(middle, bg=theme.BG, highlightthickness=0, cursor="fleur")
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=9)
        ttk.Label(middle, text="Drag to rotate · wheel to zoom · click a concept to inspect").grid(row=2, column=0, sticky="w", padx=9, pady=6)
        right.rowconfigure(3, weight=1)
        ttk.Label(right, text="Concepts in this revision").grid(row=0, column=0, sticky="w", pady=5)
        listing = ttk.Frame(right)
        listing.grid(row=1, column=0, sticky="ew")
        listing.columnconfigure(0, weight=1)
        self.concept_list = tk.Listbox(listing, height=9, width=25, exportselection=False, bg=theme.FIELD, fg=theme.TEXT,
                                      selectbackground="#214f5d", selectforeground=theme.ACCENT, relief="flat", font=(app.family, 9))
        self.concept_list.grid(row=0, column=0, sticky="ew")
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self.concept_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.concept_list.configure(yscrollcommand=scrollbar.set)
        self.concept_list.bind("<<ListboxSelect>>", self._selected_concept)
        ttk.Label(right, text="Saved notes and additional information").grid(row=2, column=0, sticky="w", pady=8)
        self.notes = ScrolledText(right, width=28, height=10, wrap="word", bg=theme.FIELD, fg=theme.TEXT, relief="flat", font=(app.family, 10))
        self.notes.grid(row=3, column=0, sticky="nsew")
        footer = ttk.Frame(outer)
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.storage_label = ttk.Label(footer)
        self.storage_label.pack(side="left")
        ttk.Button(footer, text="Return to present", command=self.close).pack(side="right")
        self.scene = Scene(app.document.design)
        self.scene.set_mode(app.scene.mode)
        self.scene.set_heat_ceiling(app.scene.heat_ceiling)
        self.scene.set_heat_enabled(self.heat_var.get())
        self.scene.yaw, self.scene.elevation, self.scene.scale = app.scene.yaw, app.scene.elevation, app.scene.scale
        self.scene.target = list(app.scene.target)
        self.scene._apply_camera()
        self._pointer = None
        self._dragged = False
        self.selected_id = app.selected
        self.canvas.bind("<Configure>", lambda _: self.request_render())
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<MouseWheel>", lambda event: self._zoom(event.delta / 120))
        self.canvas.bind("<Button-4>", lambda _: self._zoom(1))
        self.canvas.bind("<Button-5>", lambda _: self._zoom(-1))
        window.grab_set()
        self.tree.focus_set()

    @staticmethod
    def _text(widget, content):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def _populate(self, preferred=None):
        self.revisions = self.store.revisions()
        self.tree.delete(*self.tree.get_children())
        for revision in self.revisions:
            self.tree.insert("", "end", iid=revision.id, values=(f"#{revision.sequence}", local_time(revision.recorded_at, include_zone=False)))
        self.storage_label.configure(text=f"{len(self.revisions)} saved states · {self.store.size_bytes / 1048576:.2f} MiB · heat range 1–{self.scene.heat_ceiling} · timestamps mark recorded saves")
        if self.revisions:
            identity = preferred or self.revisions[0].id
            self.tree.selection_set(identity)
            self.tree.see(identity)
            self.show_revision(identity)

    def _selected_revision(self, _event=None):
        selection = self.tree.selection()
        if selection and (self.current_revision is None or selection[0] != self.current_revision.id):
            self.show_revision(selection[0])

    def show_revision(self, identity):
        try:
            revision = next(r for r in self.revisions if r.id == identity)
            document = self.store.load(identity)
        except (OSError, AtlasError, StopIteration) as exc:
            messagebox.showerror("Could not read revision", str(exc), parent=self.dialog)
            if self.current_revision:
                self.tree.selection_set(self.current_revision.id)
            return False
        self.current_revision, self.document = revision, document
        self.scene.collapse_orbit()
        self.scene.set_subconcepts(())
        self.scene.set_nodes(())
        self.scene.set_design(document.design)
        self.scene.set_nodes(document.nodes)
        self.scene.set_subconcepts(document.subconcepts)
        self.scene.set_information(document)
        self.heading.configure(text=f"#{revision.sequence} · {local_time(revision.recorded_at)}\n{revision.summary}")
        changes = [f"{c['action'].capitalize()} {c['entity']}: {c['name']}" + (f" ({', '.join(c['fields'])})" if c['fields'] else "") for c in revision.changes]
        self._text(self.change_text, revision.summary + "\n\n" + ("\n".join(changes) if changes else "Existing concepts were present when recording began. Their original creation dates are unknown."))
        self.concepts = []
        self.concept_list.delete(0, "end")
        for node in document.nodes:
            self.concepts.append(node)
            self.concept_list.insert("end", node.name)
            for child in document.children(node.id):
                self.concepts.append(child)
                self.concept_list.insert("end", "  ↳ " + child.name)
        selected = next((i for i, c in enumerate(self.concepts) if c.id == self.selected_id), 0)
        if self.concepts:
            self.concept_list.selection_set(selected)
            self.concept_list.see(selected)
            self._selected_concept()
        else:
            self.selected_id = None
            self._text(self.notes, "This saved atlas is empty.")
        index = self.revisions.index(revision)
        self.older_button.state(["!disabled" if index < len(self.revisions) - 1 else "disabled"])
        self.newer_button.state(["!disabled" if index > 0 else "disabled"])
        self.restore_button.state(["disabled" if document == self.app.document else "!disabled"])
        self.request_render()
        return True

    def _selected_concept(self, _event=None):
        selection = self.concept_list.curselection()
        if not selection:
            return
        concept = self.concepts[selection[0]]
        self.selected_id = concept.id
        parent_id = getattr(concept, "parent_id", concept.id)
        self.scene.set_selected(parent_id)
        self.scene.expand_orbit(parent_id)
        self.scene.selected_child = concept.id if hasattr(concept, "parent_id") else None
        self.scene._sync_orbits()
        heat = self.scene.heat_metrics[concept.id]
        lines = [concept.name, f"Main note: 1 · Additional items: {heat.own - 1} · Subconcept information: {heat.support} · Total: {heat.blended}",
                 "\nMain note\n" + (concept.notes or "(No note text saved)"), "\nAdditional records"]
        entries = [entry for entry in self.document.information_entries if entry.concept_id == concept.id]
        lines.extend(f"\n{entry.title}\n{entry.body}" for entry in entries)
        if not entries:
            lines.append("(None)")
        self._text(self.notes, "\n".join(lines))
        self.request_render()

    def change_view(self):
        if self.scene is not None:
            self.scene.set_mode(self.mode_var.get().lower())
            self.scene.set_heat_enabled(self.heat_var.get())
            self.heat_check.state(["!disabled" if self.scene.mode == "nodes" else "disabled"])
            self.request_render()

    def reset_view(self):
        self.scene.collapse_orbit()
        self.scene.reset_camera()
        self._selected_concept()
        self.request_render()

    def step(self, direction):
        if self.current_revision:
            index = self.revisions.index(self.current_revision) + direction
            if 0 <= index < len(self.revisions):
                identity = self.revisions[index].id
                self.tree.selection_set(identity)
                self.tree.see(identity)
                self.show_revision(identity)

    def restore(self):
        if self.current_revision is None or self.document == self.app.document:
            return False
        revision = self.current_revision
        if not messagebox.askyesno("Restore saved version?", f"Restore revision #{revision.sequence} from {local_time(revision.recorded_at)}?\n\nThis becomes a new saved revision. All later history is retained.", parent=self.dialog, default="no"):
            return False
        if not self.app._commit(self.document, kind="restore", summary=f"Restored revision #{revision.sequence} from {revision.recorded_at}", error_parent=self.dialog):
            self.dialog.lift()
            return False
        app = self.app
        app.scene.collapse_orbit()
        app.filter_var.set("All layers")
        app.protocol_filter_var.set(app._all_protocols)
        app.scene.set_layer_filter(None)
        app.scene.set_protocol_filter(None)
        app._load_editor(app.document.get(app.selected) or (app.document.nodes[0] if app.document.nodes else None))
        app.request_render()
        self.close()
        return True

    def export(self):
        filename = filedialog.asksaveasfilename(parent=self.dialog, title="Export atlas with history", defaultextension=".zip",
                                              initialfile="cyber-atlas-history.zip", filetypes=[("Atlas history archive", "*.zip")])
        if not filename:
            return False
        try:
            from pathlib import Path
            self.store.export(Path(filename))
        except (OSError, AtlasError) as exc:
            messagebox.showerror("Could not export history", str(exc), parent=self.dialog)
            return False
        self.storage_label.configure(text="Exported current atlas, dated revisions and change summaries. Each JSON state can be imported.")
        return True

    def request_render(self):
        if self.dialog is not None and self._render_job is None:
            self._render_job = self.dialog.after(25, self._render)

    def _render(self):
        self._render_job = None
        if self.dialog is None:
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width < 10 or height < 10:
            return
        self._image = tk.PhotoImage(master=self.dialog, data=self.scene.frame(width, height), format="PPM")
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._image)
        for layer in self.document.design.layers:
            actor = self.scene.axis_markers.get(layer.id)
            if actor is not None:
                x, y, depth = self.scene.project(actor.GetPosition())
                if 0 <= depth <= 1 and 0 <= y <= height:
                    self.canvas.create_text(x + 10, y, text=layer.name, anchor="w", fill=layer.color, font=(self.app.mono, 8))
        if self.selected_id:
            concept = next((c for c in self.concepts if c.id == self.selected_id), None)
            if concept:
                self.canvas.create_text(12, 12, text=concept.name, anchor="nw", fill=theme.ACCENT, font=(self.app.family, 10))

    def _press(self, event):
        self._pointer = (event.x, event.y)
        self._dragged = False

    def _drag(self, event):
        if self._pointer is not None:
            dx, dy = event.x - self._pointer[0], event.y - self._pointer[1]
            if abs(dx) + abs(dy) > 2:
                self._dragged = True
            self.scene.rotate(dx, dy)
            self._pointer = (event.x, event.y)
            self.request_render()

    def _release(self, event):
        if not self._dragged:
            identity = self.scene.pick(event.x, event.y)
            index = next((i for i, c in enumerate(self.concepts) if c.id == identity), None)
            if index is not None:
                self.concept_list.selection_clear(0, "end")
                self.concept_list.selection_set(index)
                self.concept_list.see(index)
                self._selected_concept()
        self._pointer = None

    def _zoom(self, steps):
        self.scene.zoom(steps)
        self.request_render()

    def close(self):
        if self.dialog is None:
            return
        window, self.dialog = self.dialog, None
        if self._render_job:
            window.after_cancel(self._render_job)
            self._render_job = None
        if self.scene:
            self.scene.close()
            self.scene = None
        self.current_revision = None
        self.document = None
        self.revisions = []
        self.concepts = []
        self._image = None
        window.grab_release()
        window.destroy()
        self.app.canvas.focus_set()
