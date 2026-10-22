"""One window: a 3D atlas on the left, its note editor on the right."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk
from typing import Callable

from . import __version__, theme
from .geometry import Z_BASE
from .model import Atlas, AtlasError, BANDS, CAPACITY, COLORS, LAYERS, Node, PROTOCOLS
from .scene import Scene
from .storage import read_atlas, write_atlas


class AtlasApp:
    def __init__(self, root: tk.Tk, path: Path, document: Atlas) -> None:
        self.root, self.path, self.document = root, path, document
        self.family, self.mono = theme.apply(root)
        self.scene = Scene()
        self.scene.set_nodes(document.nodes)
        self.selected: str | None = None
        self._loading = False
        self._loaded_form: tuple = ()
        self._render_job: str | None = None
        self._hover_job: str | None = None
        self._pressed: tuple[int, int] | None = None
        self._last_pointer = (0, 0)
        self._moved = False
        self._pan_mode = False
        self._closed = False
        self._image: tk.PhotoImage | None = None
        self._image_item: int | None = None
        self._label_hits: list[tuple[str, tuple]] = []
        self._axis_label_boxes: list[tuple] = []
        self.labels_var = tk.BooleanVar(value=True)
        self.filter_var = tk.StringVar(value="All layers")
        self.name_var = tk.StringVar()
        self.layer_var = tk.StringVar(value="7  Application")
        self.protocol_var = tk.StringVar(value="SSH")
        self.depth_var = tk.IntVar(value=2)
        self.layer_values = tuple(f"{i}  {LAYERS[i - 1]}" for i in range(7, 0, -1))
        self.label_font = font.Font(root, family=self.family, size=9)
        self.mono_font = font.Font(root, family=self.mono, size=9)
        self._build()
        self._bind()
        first = document.get("11") or (document.nodes[0] if document.nodes else None)
        self._load_editor(first)
        self._set_status(f"Local atlas  /  {self.path}")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(80, self.request_render)

    def _build(self) -> None:
        root = self.root
        root.title("Cyber Atlas")
        width = min(1300, max(1020, root.winfo_screenwidth() - 90))
        height = min(860, max(780, root.winfo_screenheight() - 110))
        root.geometry(f"{width}x{height}")
        root.minsize(1020, 780)
        outer = ttk.Frame(root, padding=22)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="CYBER / KNOWLEDGE ATLAS", bg=theme.BG, fg=theme.MUTED,
                 font=(self.mono, 9)).grid(row=0, column=0, sticky="w")
        tk.Label(header, text="OSI  \u00b7  Protocols  \u00b7  Services", bg=theme.BG, fg=theme.TEXT,
                 font=(self.family, 19, "bold")).grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Button(header, text="Reset view", command=self.reset_view).grid(row=0, column=1, rowspan=2)

        content = ttk.Frame(outer)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=0, minsize=354)
        content.rowconfigure(0, weight=1)
        left = tk.Frame(content, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.BORDER)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        view_header = tk.Frame(left, bg=theme.PANEL, padx=14, pady=9)
        view_header.grid(row=0, column=0, sticky="ew")
        view_header.columnconfigure(0, weight=1)
        tk.Label(view_header, text="SPATIAL VIEW", bg=theme.PANEL, fg=theme.MUTED,
                 font=(self.mono, 9)).grid(row=0, column=0, sticky="w")
        self.filter_box = ttk.Combobox(view_header, textvariable=self.filter_var,
                                      values=("All layers",) + self.layer_values, state="readonly", width=16)
        self.filter_box.grid(row=0, column=1, padx=(8, 8))
        ttk.Checkbutton(view_header, text="Labels", variable=self.labels_var,
                        command=self.request_render).grid(row=0, column=2)
        self.canvas = tk.Canvas(left, bg=theme.BG, highlightthickness=0, takefocus=True, cursor="fleur")
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.create_text(180, 180, text="Building the atlas...", fill=theme.MUTED, tags="overlay")

        right = tk.Frame(content, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.BORDER)
        right.grid(row=0, column=1, sticky="nsew")
        form = ttk.Frame(right, style="Panel.TFrame", padding=18)
        form.pack(fill="both", expand=True)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(9, weight=1)
        ttk.Label(form, text="NODE EDITOR", style="Muted.TLabel",
                  font=(self.mono, 9)).grid(row=0, column=0, sticky="w")
        self.coordinate_label = tk.Label(form, text="", bg=theme.PANEL, fg=theme.ACCENT, font=(self.mono, 10))
        self.coordinate_label.grid(row=1, column=0, sticky="w", pady=(5, 10))

        self._field_label(form, "Service / concept", 2)
        self.name_entry = ttk.Entry(form, textvariable=self.name_var)
        self.name_entry.grid(row=3, column=0, sticky="ew", pady=(5, 10))
        coords = ttk.Frame(form, style="Panel.TFrame")
        coords.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        coords.columnconfigure(0, weight=1)
        coords.columnconfigure(1, weight=1)
        ttk.Label(coords, text="OSI layer", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(coords, text="Protocol", style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=(9, 0))
        self.layer_box = ttk.Combobox(coords, textvariable=self.layer_var, values=self.layer_values,
                                     state="readonly", width=15)
        self.layer_box.grid(row=1, column=0, sticky="ew", pady=(5, 0), padx=(0, 4))
        self.protocol_box = ttk.Combobox(coords, textvariable=self.protocol_var, values=PROTOCOLS,
                                        state="readonly", width=10)
        self.protocol_box.grid(row=1, column=1, sticky="ew", pady=(5, 0), padx=(5, 0))
        self._field_label(form, "Radial depth / detail level", 5)
        band_frame = ttk.Frame(form, style="Panel.TFrame")
        band_frame.grid(row=6, column=0, sticky="ew", pady=(5, 2))
        band_frame.columnconfigure(0, weight=1)
        self.scale_widget = theme.BandSlider(band_frame, self.depth_var)
        self.scale_widget.grid(row=0, column=0, sticky="ew")
        ticks = ttk.Frame(band_frame, style="Panel.TFrame")
        ticks.grid(row=1, column=0, sticky="ew", pady=(1, 0))
        for i in range(5):
            ticks.columnconfigure(i, weight=1)
            ttk.Label(ticks, text=f"0{i}", style="Muted.TLabel", font=(self.mono, 8)).grid(
                row=0, column=i, sticky="w" if i == 0 else "e" if i == 4 else "")
        self.band_label = tk.Label(form, bg=theme.PANEL, fg=theme.MUTED, font=(self.family, 9))
        self.band_label.grid(row=7, column=0, sticky="w", pady=(2, 10))
        self._field_label(form, "Personal notes", 8)
        notes_frame = ttk.Frame(form, style="Panel.TFrame")
        notes_frame.grid(row=9, column=0, sticky="nsew", pady=(5, 10))
        notes_frame.rowconfigure(0, weight=1)
        notes_frame.columnconfigure(0, weight=1)
        self.notes = tk.Text(notes_frame, wrap="word", height=9, width=31, undo=True,
                             bg=theme.FIELD, fg=theme.TEXT, insertbackground=theme.TEXT,
                             selectbackground="#29556a", relief="flat", padx=11, pady=10,
                             highlightbackground=theme.BORDER, highlightcolor=theme.ACCENT,
                             highlightthickness=1, font=(self.family, 10), spacing1=2, spacing3=3)
        self.notes.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(notes_frame, orient="vertical", command=self.notes.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.notes.configure(yscrollcommand=scrollbar.set)
        self.editor_state = tk.Label(form, text="", bg=theme.PANEL, fg=theme.MUTED,
                                     anchor="w", justify="left", wraplength=300, font=(self.family, 9))
        self.editor_state.grid(row=10, column=0, sticky="ew", pady=(0, 10))
        buttons = ttk.Frame(form, style="Panel.TFrame")
        buttons.grid(row=11, column=0, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        self.save_button = ttk.Button(buttons, text="Save node", style="Primary.TButton", command=self.save_node)
        self.save_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(buttons, text="New", command=self.new_node).grid(row=0, column=1, padx=(0, 6))
        self.delete_button = ttk.Button(buttons, text="Delete", command=self.delete_node)
        self.delete_button.grid(row=0, column=2)
        ttk.Separator(form).grid(row=12, column=0, sticky="ew", pady=(12, 10))
        ttk.Label(form, text="Save locally. Keep a portable JSON copy.", style="Muted.TLabel").grid(row=13, column=0, sticky="w")
        files = ttk.Frame(form, style="Panel.TFrame")
        files.grid(row=14, column=0, sticky="ew", pady=(8, 0))
        files.columnconfigure(0, weight=1)
        files.columnconfigure(1, weight=1)
        ttk.Button(files, text="Export JSON", command=self.export_json).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(files, text="Import JSON", command=self.import_json).grid(row=0, column=1, sticky="ew")

        legend = ttk.Frame(outer)
        legend.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        for i in range(7, 0, -1):
            item = ttk.Frame(legend)
            item.pack(side="left", padx=(0, 18))
            dot = tk.Canvas(item, width=8, height=10, bg=theme.BG, highlightthickness=0)
            dot.create_oval(0, 2, 6, 8, fill=COLORS[i - 1], outline="")
            dot.pack(side="left", padx=(0, 5))
            tk.Label(item, text=f"L{i} {LAYERS[i - 1]}", bg=theme.BG, fg=theme.MUTED,
                     font=(self.family, 8)).pack(side="left")
        footer = ttk.Frame(outer)
        footer.grid(row=3, column=0, sticky="ew", pady=(13, 0))
        footer.columnconfigure(0, weight=1)
        self.status = tk.Label(footer, bg=theme.BG, fg=theme.MUTED, font=(self.family, 8), anchor="w")
        self.status.grid(row=0, column=0, sticky="ew")
        tk.Label(footer, text=f"LOCAL ONLY  /  v{__version__}", bg=theme.BG, fg=theme.MUTED,
                 font=(self.mono, 8)).grid(row=0, column=1, padx=(15, 0))

    @staticmethod
    def _field_label(parent: ttk.Frame, text: str, row: int) -> None:
        ttk.Label(parent, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="w")

    def _bind(self) -> None:
        for variable in (self.name_var, self.layer_var, self.protocol_var, self.depth_var):
            variable.trace_add("write", lambda *_: self._changed())
        self.notes.bind("<<Modified>>", self._notes_changed)
        self.filter_box.bind("<<ComboboxSelected>>", self._filter_changed)
        c = self.canvas
        c.bind("<Configure>", lambda _: self.request_render())
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<ButtonPress-2>", self._press)
        c.bind("<B2-Motion>", self._drag)
        c.bind("<ButtonRelease-2>", self._release)
        c.bind("<Motion>", self._hover)
        c.bind("<MouseWheel>", self._wheel)
        c.bind("<Button-4>", lambda _: self._zoom(1))
        c.bind("<Button-5>", lambda _: self._zoom(-1))
        c.bind("<Key-r>", lambda _: self.reset_view())
        c.bind("<Key-plus>", lambda _: self._zoom(1))
        c.bind("<Key-equal>", lambda _: self._zoom(1))
        c.bind("<Key-minus>", lambda _: self._zoom(-1))
        c.bind("<Left>", lambda _: self._rotate_key(-20, 0))
        c.bind("<Right>", lambda _: self._rotate_key(20, 0))
        c.bind("<Up>", lambda _: self._rotate_key(0, -15))
        c.bind("<Down>", lambda _: self._rotate_key(0, 15))
        c.bind("<Tab>", lambda _: self._cycle_node(1))
        c.bind("<Shift-Tab>", lambda _: self._cycle_node(-1))
        c.bind("<ISO_Left_Tab>", lambda _: self._cycle_node(-1))
        c.bind("<Return>", lambda _: self.name_entry.focus_set())
        for key, callback in (("<Control-s>", self.save_node), ("<Control-n>", self.new_node),
                              ("<Control-o>", self.import_json), ("<Control-Shift-S>", self.export_json)):
            self.root.bind(key, lambda _, fn=callback: self._shortcut(fn))

    @staticmethod
    def _shortcut(callback: Callable) -> str:
        callback()
        return "break"

    def _form_state(self) -> tuple:
        return (self.name_var.get(), self.layer_var.get(), self.protocol_var.get(),
                self.depth_var.get(), self.notes.get("1.0", "end-1c"))

    @property
    def dirty(self) -> bool:
        return bool(self._loaded_form) and self._form_state() != self._loaded_form

    def _changed(self) -> None:
        if self._loading or not hasattr(self, "band_label"):
            return
        depth = self.depth_var.get()
        self.band_label.configure(text=f"{depth}  /  {BANDS[depth]}")
        layer = int(self.layer_var.get().split()[0])
        self.coordinate_label.configure(text=f"L{layer}  /  {self.protocol_var.get()}  /  BAND {depth:02d}")
        self.editor_state.configure(text="Unsaved changes" if self.dirty else "Saved locally" if self.selected else "Choose a coordinate, then save to allocate.",
                                    fg=theme.GOLD if self.dirty else theme.MUTED)

    def _notes_changed(self, _event=None) -> None:
        if self.notes.edit_modified():
            self._changed()
            self.notes.edit_modified(False)

    def _load_editor(self, node: Node | None, coordinate: tuple[int, str, int] | None = None) -> None:
        self._loading = True
        self.selected = node.id if node else None
        layer, protocol, depth = node.coordinate if node else coordinate or (7, "SSH", 2)
        self.name_var.set(node.name if node else "")
        self.layer_var.set(f"{layer}  {LAYERS[layer - 1]}")
        self.protocol_var.set(protocol)
        self.depth_var.set(depth)
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", node.notes if node else "")
        self.notes.edit_reset()
        self.notes.edit_modified(False)
        self._loaded_form = self._form_state()
        self._loading = False
        self.delete_button.state(["!disabled"] if node else ["disabled"])
        self.scene.set_selected(self.selected)
        self._changed()
        self.request_render()

    def _allow_leave(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved note", "Save this note before continuing?", parent=self.root)
        return self.save_node() if answer is True else answer is False

    def select_node(self, node_id: str) -> bool:
        if node_id == self.selected:
            return True
        node = self.document.get(node_id)
        if node is None or not self._allow_leave():
            return False
        self._load_editor(node)
        return True

    def _commit(self, document: Atlas) -> bool:
        try:
            write_atlas(self.path, document)
        except (OSError, AtlasError) as exc:
            messagebox.showerror("Could not save the atlas", f"No changes were committed.\n\n{exc}", parent=self.root)
            return False
        self.document = document
        self.scene.set_nodes(document.nodes)
        self._set_status(f"Saved {datetime.now():%H:%M:%S}  /  {self.path}")
        return True

    def save_node(self) -> bool:
        try:
            layer = int(self.layer_var.get().split()[0])
            values = dict(name=self.name_var.get().strip(), layer=layer, protocol=self.protocol_var.get(),
                          depth=self.depth_var.get(), notes=self.notes.get("1.0", "end-1c"))
            existing = self.document.get(self.selected)
            node = replace(existing, **values) if existing else Node.create(**values)
            candidate = self.document.with_node(node)
        except (AtlasError, ValueError) as exc:
            self.editor_state.configure(text=str(exc), fg=theme.ERROR)
            return False
        if not self._commit(candidate):
            return False
        if self.scene.layer_filter is not None and self.scene.layer_filter != node.layer:
            self.filter_var.set("All layers")
            self.scene.set_layer_filter(None)
        self._load_editor(node)
        return True

    def new_node(self) -> None:
        if not self._allow_leave():
            return
        coordinate = self.document.next_free(int(self.layer_var.get().split()[0]), self.protocol_var.get())
        if coordinate is None:
            messagebox.showinfo("The grid is full", "All 595 coordinates are allocated. Edit or delete an existing note.", parent=self.root)
            return
        self._load_editor(None, coordinate)
        self.name_entry.focus_set()

    def delete_node(self) -> bool:
        node = self.document.get(self.selected)
        if node is None:
            return False
        if not messagebox.askyesno("Delete volume", f"Delete '{node.name}'?\n\nIts volume and notes will be removed. Any unsaved edits to this note will be discarded.", parent=self.root):
            return False
        if not self._commit(self.document.without_node(node.id)):
            return False
        visible = [n for n in self.document.nodes if self.scene.layer_filter is None or n.layer == self.scene.layer_filter]
        self._load_editor(visible[0] if visible else None)
        return True

    def import_json(self) -> None:
        filename = filedialog.askopenfilename(parent=self.root, title="Import an atlas",
                                              filetypes=[("Cyber Atlas JSON", "*.json"), ("All files", "*")])
        if not filename:
            return
        if Path(filename).resolve() == self.path.resolve():
            messagebox.showinfo("Atlas already open", "This is already your active atlas. No import is needed.", parent=self.root)
            return
        try:
            candidate = read_atlas(Path(filename))
        except (OSError, AtlasError) as exc:
            messagebox.showerror("Import stopped", str(exc), parent=self.root)
            return
        if not self._allow_leave():
            return
        if not messagebox.askyesno("Replace the current atlas?", f"Load {len(candidate.nodes)} volumes from this file?\n\nThis replaces the current atlas. A backup of the previous atlas is retained next to the local data file.", parent=self.root):
            return
        if self._commit(candidate):
            self.filter_var.set("All layers")
            self.scene.set_layer_filter(None)
            self._load_editor(candidate.get("11") or (candidate.nodes[0] if candidate.nodes else None))
            self.reset_view()

    def export_json(self) -> None:
        if not self._allow_leave():
            return
        filename = filedialog.asksaveasfilename(parent=self.root, title="Export your atlas",
                                                defaultextension=".json", initialfile="cyber-atlas.json",
                                                filetypes=[("Cyber Atlas JSON", "*.json")])
        if not filename:
            return
        try:
            write_atlas(Path(filename), self.document, backup=False)
        except (OSError, AtlasError) as exc:
            messagebox.showerror("Export failed", str(exc), parent=self.root)
            return
        self._set_status(f"Exported  /  {filename}")

    def _filter_changed(self, _event=None) -> None:
        value = self.filter_var.get()
        self.scene.set_layer_filter(None if value == "All layers" else int(value.split()[0]))
        self.request_render()

    def reset_view(self) -> None:
        self.scene.reset_camera()
        self.request_render()

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def request_render(self) -> None:
        if not self._closed and self._render_job is None:
            self._render_job = self.root.after(16, self._render)

    def _render(self) -> None:
        self._render_job = None
        if self._closed:
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width < 10 or height < 10:
            return
        ppm = self.scene.frame(width, height)
        self._image = tk.PhotoImage(master=self.root, data=ppm, format="PPM")
        if self._image_item is None:
            self._image_item = self.canvas.create_image(0, 0, anchor="nw", image=self._image)
        else:
            self.canvas.itemconfigure(self._image_item, image=self._image)
        self.canvas.tag_lower(self._image_item)
        self.canvas.delete("overlay")
        self._label_hits.clear()
        visible = [n for n in self.document.nodes if self.scene.layer_filter is None or self.scene.layer_filter == n.layer]
        self.canvas.create_text(width - 17, 18, anchor="ne", text=f"{len(visible):02d} FILLED VOLUMES",
                                fill=theme.MUTED, font=(self.mono, 8), tags="overlay")
        self._axis_label_boxes.clear()
        for layer in range(1, 8):
            x, y, _ = self.scene.project((0.0, 0.0, Z_BASE + layer - 0.5))
            # Reference labels must not float through a solid in front of them.
            if self.scene.pick(x - 24, y) is not None:
                continue
            color = COLORS[layer - 1] if self.scene.layer_filter in (None, layer) else "#41566a"
            self.canvas.create_text(x - 16, y, text=f"L{layer}", anchor="e", fill=color,
                                    font=(self.mono, 9), tags="overlay")
            self._axis_label_boxes.append((x - 37, y - 10, x - 10, y + 10))
        if self.labels_var.get():
            self._draw_labels(visible, width, height)
        self.canvas.create_text(18, height - 44, anchor="sw", text="DRAG  ROTATE     WHEEL  ZOOM     CLICK  EDIT",
                                fill=theme.MUTED, font=(self.mono, 8), tags="overlay")
        self.canvas.create_text(18, height - 24, anchor="sw", text="SHIFT + DRAG  PAN     TAB  NEXT NOTE",
                                fill="#6d879f", font=(self.mono, 8), tags="overlay")
        if not visible:
            text = "No volumes on this layer." if self.document.nodes else "Your atlas starts here."
            self.canvas.create_text(width / 2, height / 2 - 20, text=text, fill=theme.TEXT,
                                    font=(self.family, 16), tags="overlay")
            self.canvas.create_text(width / 2, height / 2 + 12, text="Create a note and save it to allocate a volume.",
                                    fill=theme.MUTED, font=(self.family, 10), tags="overlay")

    def _draw_labels(self, nodes: list[Node], width: int, height: int) -> None:
        boxes: list[tuple[float, float, float, float]] = list(self._axis_label_boxes)
        ordered = sorted(nodes, key=lambda n: n.id != self.selected)
        for node in ordered:
            x, y, depth = self.scene.project(self.scene.meshes[node.id].label_anchor)
            if not (0 <= depth <= 1 and 0 < x < width and 0 < y < height):
                continue
            selected = node.id == self.selected
            # Hidden surfaces don't get floating labels through other volumes.
            if not selected and self.scene.pick(x, y) != node.id:
                continue
            text = node.name
            while self.label_font.measure(text) > 176 and len(text) > 2:
                text = text[:-2] + "\u2026"
            text_width = self.label_font.measure(text)
            total_width = text_width + 14
            right = x >= width * 0.5
            shifts = [(12, -25), (12, 8), (12, -49), (-total_width - 12, -25), (-total_width - 12, 8)]
            if not right:
                shifts = [(-total_width - 12, -25), (-total_width - 12, 8), (-total_width - 12, -49), (12, -25), (12, 8)]
            placement = None
            for dx, dy in shifts:
                bx, by = x + dx, y + dy
                box = (bx, by, bx + total_width, by + 23)
                if not (8 <= box[0] and box[2] <= width - 8 and 36 <= box[1] and box[3] < height - 82):
                    continue
                if any(not (box[2] + 4 < b[0] or box[0] - 4 > b[2] or box[3] + 4 < b[1] or box[1] - 4 > b[3]) for b in boxes):
                    continue
                placement = box
                break
            if placement is None:
                continue
            boxes.append(placement)
            bx, by, ex, ey = placement
            end_x = bx if bx > x else ex
            self.canvas.create_line(x, y, end_x, (by + ey) / 2, fill=theme.GOLD if selected else "#456279", tags="overlay")
            self.canvas.create_rectangle(bx, by, ex, ey, fill="#1b3044" if selected else "#101e2e",
                                         outline="#9d8d69" if selected else "#2a4155", width=1, tags="overlay")
            self.canvas.create_text(bx + 7, (by + ey) / 2, text=text, fill="#fff0ca" if selected else theme.TEXT,
                                    font=self.label_font, anchor="w", tags="overlay")
            self._label_hits.append((node.id, placement))

    def _pick_at(self, x: float, y: float) -> str | None:
        for node_id, (x0, y0, x1, y1) in reversed(self._label_hits):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return node_id
        return self.scene.pick(x, y)

    def _press(self, event) -> str:
        self.canvas.focus_set()
        self._pressed = (event.x, event.y)
        self._last_pointer = self._pressed
        self._moved = False
        self._pan_mode = bool(event.state & 0x0001) or event.num == 2
        return "break"

    def _drag(self, event) -> str:
        if self._pressed is None:
            return "break"
        if not self._moved and (event.x - self._pressed[0]) ** 2 + (event.y - self._pressed[1]) ** 2 < 16:
            return "break"
        self._moved = True
        dx, dy = event.x - self._last_pointer[0], event.y - self._last_pointer[1]
        self._last_pointer = (event.x, event.y)
        if self._pan_mode:
            self.scene.pan(dx, dy)
        else:
            self.scene.rotate(dx, dy)
        self.request_render()
        return "break"

    def _release(self, event) -> str:
        if self._pressed is not None and not self._moved and event.num == 1:
            node_id = self._pick_at(event.x, event.y)
            if node_id:
                self.select_node(node_id)
        self._pressed = None
        self.canvas.configure(cursor="fleur")
        return "break"

    def _hover(self, event) -> None:
        if self._pressed is not None or self._closed:
            return
        if self._hover_job is not None:
            self.root.after_cancel(self._hover_job)
        x, y = event.x, event.y
        self._hover_job = self.root.after(70, lambda: self._hover_at(x, y))

    def _hover_at(self, x: int, y: int) -> None:
        self._hover_job = None
        if not self._closed:
            self.canvas.configure(cursor="hand2" if self._pick_at(x, y) else "fleur")

    def _wheel(self, event) -> str:
        steps = event.delta / 120 if abs(event.delta) >= 120 else event.delta
        return self._zoom(steps)

    def _zoom(self, steps: float) -> str:
        self.scene.zoom(steps)
        self.request_render()
        return "break"

    def _rotate_key(self, dx: float, dy: float) -> str:
        self.scene.rotate(dx, dy)
        self.request_render()
        return "break"

    def _cycle_node(self, direction: int) -> str:
        ids = [n.id for n in self.document.nodes if self.scene.layer_filter in (None, n.layer)]
        if ids:
            if self.selected in ids:
                index = (ids.index(self.selected) + direction) % len(ids)
            else:
                index = 0 if direction > 0 else -1
            self.select_node(ids[index])
        return "break"

    def close(self) -> bool:
        if not self._allow_leave():
            return False
        self.shutdown()
        return True

    def shutdown(self) -> None:
        """Release resources. Tests also use this without a confirmation dialog."""
        self._closed = True
        for job in (self._render_job, self._hover_job):
            if job is not None:
                self.root.after_cancel(job)
        self.scene.close()
        self.root.destroy()
