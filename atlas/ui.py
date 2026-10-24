"""One window: a 3D atlas on the left, its note editor on the right."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk
from typing import Callable

from . import __version__, theme
from .model import ANGULAR_SLOTS, Atlas, AtlasError, BANDS, BLOCK_SIZES, CENTER_DEPTH, LayerId, Node, NO_PROTOCOL_LABEL
from .design_editor import DesignEditor
from .scene import NO_PROTOCOL_FILTER, Scene
from .storage import read_atlas, write_atlas


class AtlasApp:
    def __init__(self, root: tk.Tk, path: Path, document: Atlas) -> None:
        self.root, self.path, self.document = root, path, document
        self.family, self.mono = theme.apply(root)
        self.scene = Scene(document.design)
        self.scene.set_nodes(document.nodes)
        self.selected: str | None = None
        self.placement_state = "locked"
        self._placement_origin: Node | None = None
        self._floating_position: tuple[int, int] | None = None
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
        self.protocol_filter_var = tk.StringVar(value="All protocols")
        self.name_var = tk.StringVar()
        self.layer_var = tk.StringVar(value="7  Application")
        self.protocol_var = tk.StringVar(value="SSH")
        self.depth_var = tk.IntVar(value=2)
        self.size_var = tk.StringVar(value="1/16")
        self.slot_var = tk.StringVar(value="01")
        self._last_size = "1/16"
        self._design_maps()
        self.label_font = font.Font(root, family=self.family, size=9)
        self.mono_font = font.Font(root, family=self.mono, size=9)
        self.coordinate_font = font.Font(root, family=self.mono, size=10)
        self._build()
        self._refresh_design_controls()
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
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="CYBER / KNOWLEDGE ATLAS", bg=theme.BG, fg=theme.MUTED,
                 font=(self.mono, 9)).grid(row=0, column=0, sticky="w")
        self.title_label = tk.Label(header, text="Knowledge Atlas", bg=theme.BG, fg=theme.TEXT,
                                    font=(self.family, 19, "bold"))
        self.title_label.grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.design_button = ttk.Button(header, text="Edit design", command=self.edit_design)
        self.design_button.grid(row=0, column=1, rowspan=2, padx=(0, 8))
        self.empty_button = ttk.Button(header, text="Empty atlas", command=self.new_empty_atlas)
        self.empty_button.grid(row=0, column=2, rowspan=2, padx=(0, 8))
        ttk.Button(header, text="Reset view", command=self.reset_view).grid(row=0, column=3, rowspan=2)

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
        self.protocol_filter_box = ttk.Combobox(view_header, textvariable=self.protocol_filter_var,
                                                values=("All protocols",) + self.protocol_values, state="readonly", width=13)
        self.protocol_filter_box.grid(row=0, column=2, padx=(0, 8))
        ttk.Checkbutton(view_header, text="Labels", variable=self.labels_var,
                        command=self.request_render).grid(row=0, column=3)
        self.canvas = tk.Canvas(left, bg=theme.BG, highlightthickness=0, takefocus=True, cursor="fleur")
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.create_text(180, 180, text="Building the atlas...", fill=theme.MUTED, tags="overlay")

        right = tk.Frame(content, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.BORDER)
        right.grid(row=0, column=1, sticky="nsew")
        form = ttk.Frame(right, style="Panel.TFrame", padding=10)
        form.pack(fill="both", expand=True)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(9, weight=1)
        ttk.Label(form, text="NODE EDITOR", style="Muted.TLabel",
                  font=(self.mono, 9)).grid(row=0, column=0, sticky="w")
        self.coordinate_label = tk.Label(form, text="", bg=theme.PANEL, fg=theme.ACCENT,
                                         font=self.coordinate_font, anchor="w")
        self.coordinate_label.grid(row=1, column=0, sticky="w", pady=(3, 4))

        self._field_label(form, "Service / concept", 2)
        self.name_entry = ttk.Entry(form, textvariable=self.name_var)
        self.name_entry.grid(row=3, column=0, sticky="ew", pady=(4, 5))
        coords = ttk.Frame(form, style="Panel.TFrame")
        coords.grid(row=4, column=0, sticky="ew", pady=(0, 5))
        for column in range(3):
            coords.columnconfigure(column, weight=1)
        self.layer_caption = ttk.Label(coords, text="OSI layer", style="Muted.TLabel")
        self.layer_caption.grid(row=0, column=0, sticky="w")
        self.protocol_caption = ttk.Label(coords, text="Protocol", style="Muted.TLabel")
        self.protocol_caption.grid(row=0, column=1, sticky="w", padx=(9, 0))
        self.layer_box = ttk.Combobox(coords, textvariable=self.layer_var, values=self.layer_values,
                                     state="readonly", width=15)
        self.layer_box.grid(row=1, column=0, sticky="ew", pady=(5, 0), padx=(0, 4))
        self.protocol_box = ttk.Combobox(coords, textvariable=self.protocol_var, values=self.protocol_values,
                                        state="readonly", width=10)
        self.protocol_box.grid(row=1, column=1, sticky="ew", pady=(5, 0), padx=(5, 0))
        ttk.Label(coords, text="Block size", style="Muted.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.size_box = ttk.Combobox(coords, textvariable=self.size_var, values=tuple(BLOCK_SIZES), state="readonly", width=5)
        self.size_box.grid(row=1, column=2, sticky="ew", pady=(5, 0), padx=(8, 0))
        radial_header = ttk.Frame(form, style="Panel.TFrame")
        radial_header.grid(row=5, column=0, sticky="ew")
        radial_header.columnconfigure(0, weight=1)
        self.band_label = tk.Label(radial_header, bg=theme.PANEL, fg=theme.MUTED, font=(self.family, 9), anchor="w")
        self.band_label.grid(row=0, column=0, sticky="w", padx=(0, 6))
        band_frame = ttk.Frame(form, style="Panel.TFrame")
        band_frame.grid(row=6, column=0, sticky="ew", pady=(4, 1))
        band_frame.columnconfigure(0, weight=1)
        self.scale_widget = theme.BandSlider(band_frame, self.depth_var, label_font=(self.mono, 8))
        self.scale_widget.grid(row=0, column=0, sticky="ew")
        slot_frame = ttk.Frame(form, style="Panel.TFrame")
        slot_frame.grid(row=7, column=0, sticky="ew", pady=(2, 4))
        slot_frame.columnconfigure(0, weight=1)
        self.slot_label = tk.Label(slot_frame, bg=theme.PANEL, fg=theme.MUTED, font=(self.family, 9), anchor="w")
        self.slot_label.grid(row=0, column=0, sticky="w")
        self.slot_slider = theme.SlotSlider(slot_frame, self.slot_var, on_begin=self._begin_slot_placement,
                                            on_commit=self._commit_slot_placement, label_font=(self.mono, 8))
        self.slot_slider.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._field_label(form, "Personal notes", 8)
        notes_frame = ttk.Frame(form, style="Panel.TFrame")
        notes_frame.grid(row=9, column=0, sticky="nsew", pady=(4, 6))
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
        self.editor_state.grid(row=10, column=0, sticky="ew", pady=(0, 6))
        buttons = ttk.Frame(form, style="Panel.TFrame")
        buttons.grid(row=11, column=0, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        self.save_button = ttk.Button(buttons, text="Save node", style="Primary.TButton", command=self.save_node)
        self.save_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.add_button = ttk.Button(buttons, text="Add here", command=self.new_node)
        self.add_button.grid(row=0, column=1, padx=(0, 6))
        self.delete_button = ttk.Button(buttons, text="Delete", command=self.delete_node)
        self.delete_button.grid(row=0, column=2)
        ttk.Separator(form).grid(row=12, column=0, sticky="ew", pady=(8, 8))
        ttk.Label(form, text="Save locally. Keep a portable JSON copy.", style="Muted.TLabel").grid(row=13, column=0, sticky="w")
        files = ttk.Frame(form, style="Panel.TFrame")
        files.grid(row=14, column=0, sticky="ew", pady=(6, 0))
        files.columnconfigure(0, weight=1)
        files.columnconfigure(1, weight=1)
        ttk.Button(files, text="Export JSON", command=self.export_json).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(files, text="Import JSON", command=self.import_json).grid(row=0, column=1, sticky="ew")

        self.legend = tk.Canvas(outer, height=19, bg=theme.BG, highlightthickness=0)
        self.legend.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.legend_scroll = ttk.Scrollbar(outer, orient="horizontal", command=self.legend.xview)
        self.legend_scroll.grid(row=3, column=0, sticky="ew")
        self.legend.configure(xscrollcommand=self.legend_scroll.set)
        self.legend.bind("<Configure>", self._update_legend_scroll)
        footer = ttk.Frame(outer)
        footer.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        footer.columnconfigure(0, weight=1)
        self.status = tk.Label(footer, bg=theme.BG, fg=theme.MUTED, font=(self.family, 8), anchor="w")
        self.status.grid(row=0, column=0, sticky="ew")
        tk.Label(footer, text=f"LOCAL ONLY  /  v{__version__}", bg=theme.BG, fg=theme.MUTED,
                 font=(self.mono, 8)).grid(row=0, column=1, padx=(15, 0))

    def _design_maps(self) -> None:
        design = self.document.design
        self._layer_displays = {layer.id: f"{i + 1}  {layer.name}" for i, layer in enumerate(design.layers)}
        self._layer_ids = {display: key for key, display in self._layer_displays.items()}
        self.layer_values = tuple(reversed(tuple(self._layer_ids)))
        self._protocol_displays = {p.id: p.name for p in design.protocols}
        self._no_protocol = NO_PROTOCOL_LABEL
        while self._no_protocol in self._protocol_displays.values():
            self._no_protocol += " (unassigned)"
        self._protocol_displays = {None: self._no_protocol, **self._protocol_displays}
        self._protocol_ids = {p.name: p.id for p in design.protocols}
        self._protocol_ids = {self._no_protocol: None, **self._protocol_ids}
        self.protocol_values = tuple(self._protocol_ids)
        self._all_protocols = "All protocols"
        while self._all_protocols in self._protocol_ids:
            self._all_protocols += " (any)"

    def _layer_id(self) -> LayerId:
        return self._layer_ids[self.layer_var.get()]

    def _protocol_id(self) -> str | None:
        return self._protocol_ids[self.protocol_var.get()]

    def _refresh_design_controls(self) -> None:
        self._design_maps()
        design = self.document.design
        self.layer_box.configure(values=self.layer_values)
        self.protocol_box.configure(values=self.protocol_values)
        self.filter_box.configure(values=("All layers",) + self.layer_values)
        self.protocol_filter_box.configure(values=(self._all_protocols,) + self.protocol_values)
        self.filter_var.set(self._layer_displays.get(self.scene.layer_filter, "All layers"))
        active_protocol = self.scene.protocol_filter
        self.protocol_filter_var.set(self._all_protocols if active_protocol is None else self._no_protocol
                                     if active_protocol is NO_PROTOCOL_FILTER else self._protocol_displays[active_protocol])
        self.layer_caption.configure(text=design.layer_caption)
        self.protocol_caption.configure(text=design.protocol_caption)
        self.legend.delete("all")
        x = 0
        for i, layer in reversed(tuple(enumerate(design.layers, 1))):
            self.legend.create_oval(x, 6, x + 6, 12, fill=layer.color, outline="")
            item = self.legend.create_text(x + 13, 9, text=f"L{i} {layer.name}", anchor="w",
                                           fill=theme.MUTED, font=(self.family, 8))
            x = self.legend.bbox(item)[2] + 18
        self.legend.configure(scrollregion=(0, 0, x, 19))
        self._legend_width = x
        self._update_legend_scroll()

    def _update_legend_scroll(self, _event=None) -> None:
        if getattr(self, "_legend_width", 0) > self.legend.winfo_width():
            self.legend_scroll.grid()
        else:
            self.legend_scroll.grid_remove()

    def edit_design(self) -> None:
        if not self._allow_leave():
            return
        dialog = DesignEditor(self.root, self.document, self.apply_design)
        self.root.wait_window(dialog)

    def apply_design(self, candidate: Atlas) -> bool:
        selected = self.selected
        layers_changed = candidate.design.layers != self.document.design.layers
        if candidate == self.document:
            return True
        if not self._commit(candidate):
            return False
        self._load_editor(candidate.get(selected) or (candidate.nodes[0] if candidate.nodes else None))
        if layers_changed:
            self.reset_view()
        return True

    @staticmethod
    def _field_label(parent: ttk.Frame, text: str, row: int) -> None:
        ttk.Label(parent, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="w")

    def _bind(self) -> None:
        for variable in (self.name_var, self.layer_var, self.protocol_var, self.depth_var, self.size_var, self.slot_var):
            variable.trace_add("write", lambda *_: self._changed())
        self.notes.bind("<<Modified>>", self._notes_changed)
        self.filter_box.bind("<<ComboboxSelected>>", self._filter_changed)
        self.protocol_filter_box.bind("<<ComboboxSelected>>", self._filter_changed)
        self.size_box.bind("<<ComboboxSelected>>", self._size_changed)
        c = self.canvas
        c.bind("<Configure>", lambda _: self.request_render())
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<ButtonPress-2>", self._press)
        c.bind("<B2-Motion>", self._drag)
        c.bind("<ButtonRelease-2>", self._release)
        c.bind("<Motion>", self._hover)
        c.bind("<Leave>", lambda _: self._restore_preview())
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
        self.root.bind("<Escape>", lambda _: self.cancel_placement())
        for key, callback in (("<Control-s>", self.save_node), ("<Control-n>", self.new_node),
                              ("<Control-o>", self.import_json), ("<Control-Shift-S>", self.export_json)):
            self.root.bind(key, lambda _, fn=callback: self._shortcut(fn))

    @staticmethod
    def _shortcut(callback: Callable) -> str:
        callback()
        return "break"

    def _form_state(self) -> tuple:
        return (self.name_var.get(), self.layer_var.get(), self.protocol_var.get(),
                self.depth_var.get(), self.size_var.get(), self.slot_var.get(), self.notes.get("1.0", "end-1c"))

    @property
    def dirty(self) -> bool:
        return bool(self._loaded_form) and self._form_state() != self._loaded_form

    def _changed(self) -> None:
        if self._loading or not hasattr(self, "band_label"):
            return
        depth = self.depth_var.get()
        layer = self._layer_id()
        position = "CENTER" if depth == CENTER_DEPTH else f"BAND {depth:02d}"
        coordinate = f"L{self.document.design.layer_index(layer) + 1}  /  {self.protocol_var.get()}  /  {position}"
        while self.coordinate_font.measure(coordinate) > 300 and len(coordinate) > 2:
            coordinate = coordinate[:-2] + "\u2026"
        self.coordinate_label.configure(text=coordinate)
        detail = "Center" if depth == CENTER_DEPTH else f"{depth:02d}  /  {BANDS[depth]}"
        span = BLOCK_SIZES[self.size_var.get()]
        self.band_label.configure(text=f"Position: {detail}")
        slot = int(self.slot_var.get()) - 1
        end = (slot + span - 1) % ANGULAR_SLOTS
        footprint = " / All slots" if span == ANGULAR_SLOTS else (
            f" / Slots {slot + 1:02d}{' → ' if end < slot else '–'}{end + 1:02d}" if span > 1 else ""
        )
        self.slot_label.configure(text=f"Start slot {slot + 1:02d} / 16 · {slot * 360 / ANGULAR_SLOTS:g}°{footprint}")
        self.slot_slider.set_context(span, self.document.free_starts(layer, depth, span, exclude_id=self.selected))
        placing = self.placement_state == "placing"
        self.save_button.state(["disabled"] if placing else ["!disabled"])
        text = "Placing: click to lock (Esc cancels)" if placing else (
            "Locked: click block to move. Save node to keep." if self.dirty or not self.selected
            else "Saved / Locked: click block to move."
        )
        self.editor_state.configure(text=text,
                                    fg=theme.GOLD if self.dirty else theme.MUTED)
        if not self._refresh_preview():
            text = "Placing: space occupied; choose another slot." if placing else "Space occupied. Choose another start slot or a smaller size."
            self.editor_state.configure(text=text, fg=theme.ERROR)
        self.request_render()

    def _preview_candidate(self, depth: int | None = None, slot: int | None = None) -> Node:
        return Node("preview", "Placement", self._layer_id(), self._protocol_id(),
                    self.depth_var.get() if depth is None else depth,
                    slot=int(self.slot_var.get()) - 1 if slot is None else slot, span=BLOCK_SIZES[self.size_var.get()])

    def _refresh_preview(self, depth: int | None = None, slot: int | None = None) -> bool:
        if depth is None and self.placement_state == "placing" and self._floating_position is not None:
            depth, slot = self._floating_position
        candidate = self._preview_candidate(depth, slot)
        valid = candidate.slot in self.document.free_starts(candidate.layer, candidate.depth, candidate.span, exclude_id=self.selected)
        existing = self.document.get(self.selected)
        changed = self.placement_state == "placing" or existing is None or (candidate.position, candidate.slot, candidate.span) != (existing.position, existing.slot, existing.span)
        self.scene.set_preview(candidate if changed and self.scene.is_visible(candidate) else None, valid)
        return valid

    def _restore_preview(self) -> None:
        if not self._closed:
            self._cancel_hover()
            self._refresh_preview()
            self.request_render()

    def _cancel_hover(self) -> None:
        if self._hover_job is not None:
            self.root.after_cancel(self._hover_job)
            self._hover_job = None

    def begin_placement(self) -> None:
        self._cancel_hover()
        self._placement_origin = self._preview_candidate()
        self._floating_position = None
        self.placement_state = "placing"
        self._changed()

    def _begin_slot_placement(self) -> None:
        if self.placement_state != "placing":
            self.begin_placement()
        self._cancel_hover()
        self._floating_position = None

    def _commit_slot_placement(self) -> None:
        self.place_at(self.depth_var.get(), int(self.slot_var.get()) - 1)

    def cancel_placement(self) -> str:
        self.slot_slider.cancel_drag()
        if self.placement_state == "placing":
            self._cancel_hover()
            self._floating_position = None
            self.placement_state = "locked"
            origin = self._placement_origin
            if origin is not None:
                self._loading = True
                self.layer_var.set(self._layer_displays[origin.layer])
                self.depth_var.set(origin.depth)
                self.slot_var.set(f"{origin.slot + 1:02d}")
                self.size_var.set(next(label for label, span in BLOCK_SIZES.items() if span == origin.span))
                self._loading = False
            self._changed()
        return "break"

    def _size_changed(self, _event=None) -> None:
        self._last_size = self.size_var.get()
        if self.selected is None:
            candidate = self._preview_candidate()
            slot = self.document.next_free(candidate.layer, candidate.depth, candidate.span, start=candidate.slot)
            if slot is not None:
                self.slot_var.set(f"{slot + 1:02d}")
        self._changed()

    def _notes_changed(self, _event=None) -> None:
        if self.notes.edit_modified():
            self._changed()
            self.notes.edit_modified(False)

    def _load_editor(self, node: Node | None, coordinate: tuple[LayerId, str | None, int] | None = None,
                     *, slot: int | None = None, size: str | None = None, placing: bool = False) -> None:
        self.slot_slider.cancel_drag()
        self._cancel_hover()
        self.placement_state = "placing" if placing else "locked"
        self._floating_position = None
        self._loading = True
        self.selected = node.id if node else None
        protocols = self.document.design.protocols
        default_protocol = "SSH" if "SSH" in self._protocol_displays else protocols[0].id if protocols else None
        layer, protocol, depth = node.coordinate if node else coordinate or (self.document.design.layers[-1].id, default_protocol, 2)
        self.name_var.set(node.name if node else "")
        self.layer_var.set(self._layer_displays[layer])
        self.protocol_var.set(self._protocol_displays[protocol])
        self.depth_var.set(depth)
        self.size_var.set(next(label for label, span in BLOCK_SIZES.items() if span == node.span) if node else size or self._last_size)
        if node:
            slot = node.slot
        elif slot is None:
            slot = self.document.next_free(layer, depth, BLOCK_SIZES[self.size_var.get()])
        self.slot_var.set(f"{(slot if slot is not None else 0) + 1:02d}")
        self._placement_origin = self._preview_candidate() if node or placing else None
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
        design_changed = self.document.design != document.design
        self.document = document
        if design_changed:
            self.scene.set_design(document.design)
            if self.scene.layer_filter not in {e.id for e in document.design.layers}:
                self.scene.layer_filter = None
            if self.scene.protocol_filter is not NO_PROTOCOL_FILTER and self.scene.protocol_filter not in {e.id for e in document.design.protocols}:
                self.scene.protocol_filter = None
            self._refresh_design_controls()
        self.scene.set_nodes(document.nodes)
        self._set_status(f"Saved {datetime.now():%H:%M:%S}  /  {self.path}")
        return True

    def save_node(self) -> bool:
        if self.placement_state == "placing":
            self.editor_state.configure(text="Placing: click a valid location to lock before saving.", fg=theme.GOLD)
            return False
        try:
            layer = self._layer_id()
            values = dict(name=self.name_var.get().strip(), layer=layer, protocol=self._protocol_id(),
                          depth=self.depth_var.get(), notes=self.notes.get("1.0", "end-1c"),
                          slot=int(self.slot_var.get()) - 1, span=BLOCK_SIZES[self.size_var.get()])
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
        expected_filter = NO_PROTOCOL_FILTER if node.protocol is None else node.protocol
        if self.scene.protocol_filter is not None and self.scene.protocol_filter != expected_filter:
            self.protocol_filter_var.set(self._all_protocols)
            self.scene.set_protocol_filter(None)
        self._load_editor(node)
        return True

    def new_node(self) -> None:
        if not self._allow_leave():
            return
        coordinate = (self._layer_id(), self._protocol_id(), self.depth_var.get())
        existing = self.document.get(self.selected)
        start = existing.slot + existing.span if existing else int(self.slot_var.get()) - 1
        slot = self.document.next_free(coordinate[0], coordinate[2], BLOCK_SIZES[self._last_size], start=start)
        if slot is None:
            self.editor_state.configure(text=f"No room for {self._last_size} here. Choose a smaller size or another radial position.", fg=theme.ERROR)
            return
        self._load_editor(None, coordinate, slot=slot, size=self._last_size, placing=True)
        self.name_entry.focus_set()

    def new_empty_atlas(self) -> bool:
        if not self._allow_leave():
            return False
        if self.document.nodes:
            if not messagebox.askyesno(
                "Start an empty atlas?",
                f"Replace all {len(self.document.nodes)} saved blocks with an empty atlas?\n\n"
                "The current saved atlas will be kept as the previous-version backup. "
                "Use Export JSON first to keep a separate copy.",
                parent=self.root,
            ):
                return False
            if not self._commit(Atlas(design=self.document.design)):
                return False
        # Repeating this action on an empty document must preserve its backup.
        self.filter_var.set("All layers")
        self.protocol_filter_var.set(self._all_protocols)
        self.scene.set_layer_filter(None)
        self.scene.set_protocol_filter(None)
        self._last_size = "1/16"
        self._load_editor(None)
        self.reset_view()
        self._set_status(f"Empty atlas  /  {self.path}")
        self.name_entry.focus_set()
        return True

    def delete_node(self) -> bool:
        node = self.document.get(self.selected)
        if node is None:
            return False
        if not messagebox.askyesno("Delete volume", f"Delete '{node.name}'?\n\nIts volume and notes will be removed. Any unsaved edits to this note will be discarded.", parent=self.root):
            return False
        if not self._commit(self.document.without_node(node.id)):
            return False
        visible = [n for n in self.document.nodes if self.scene.is_visible(n)]
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
            self.protocol_filter_var.set(self._all_protocols)
            self.scene.set_layer_filter(None)
            self.scene.set_protocol_filter(None)
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
        self.scene.set_layer_filter(None if value == "All layers" else self._layer_ids[value])
        protocol = self.protocol_filter_var.get()
        selected_protocol = None if protocol == self._all_protocols else self._protocol_ids[protocol]
        self.scene.set_protocol_filter(None if protocol == self._all_protocols else
                                       NO_PROTOCOL_FILTER if selected_protocol is None else selected_protocol)
        self._refresh_preview()
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
        visible = [n for n in self.document.nodes if self.scene.is_visible(n)]
        self.canvas.create_text(width - 17, 18, anchor="ne", text=f"{len(visible):02d} FILLED VOLUMES",
                                fill=theme.MUTED, font=(self.mono, 8), tags="overlay")
        self._axis_label_boxes.clear()
        for i, layer in enumerate(self.document.design.layers, 1):
            x, y, _ = self.scene.project((0.0, 0.0, self.document.design.z_base + i - 0.5))
            # Reference labels must not float through a solid in front of them.
            if self.scene.pick(x - 24, y) is not None:
                continue
            color = layer.color if self.scene.layer_filter in (None, layer.id) else "#41566a"
            axis_text = f"L{i} {layer.name}"
            while self.mono_font.measure(axis_text) > 170 and len(axis_text) > 4:
                axis_text = axis_text[:-2] + "\u2026"
            self.canvas.create_text(x - 16, y, text=axis_text, anchor="e", fill=color,
                                    font=(self.mono, 9), tags="overlay")
            self._axis_label_boxes.append((x - 20 - self.mono_font.measure(axis_text), y - 10, x - 10, y + 10))
        if self.labels_var.get():
            self._draw_labels(visible, width, height)
        self.canvas.create_text(18, height - 44, anchor="sw", text="DRAG  ROTATE     WHEEL  ZOOM     CLICK  EDIT",
                                fill=theme.MUTED, font=(self.mono, 8), tags="overlay")
        self.canvas.create_text(18, height - 24, anchor="sw", text="SHIFT + DRAG  PAN     TAB  NEXT NOTE",
                                fill="#6d879f", font=(self.mono, 8), tags="overlay")
        self.canvas.create_text(18, height - 64, anchor="sw",
                                text="PLACING: CLICK TO LOCK / ESC CANCEL" if self.placement_state == "placing" else "LOCKED: CLICK BLOCK TO MOVE",
                                fill=theme.ACCENT, font=(self.mono, 8), tags="overlay")
        if not visible:
            text = "No volumes match these filters." if self.document.nodes else "Your atlas starts here."
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
            design = self.document.design
            text = design.block_label(node)
            if design.label_mode == "combined":
                text = f"{node.name}\n{design.layer(node.layer).name} · {design.protocol_name(node.protocol)}"
            max_label_width = min(300, width - 50) if design.label_mode != "title" else 176
            lines = text.splitlines()
            for i, line in enumerate(lines):
                while self.label_font.measure(line) > max_label_width and len(line) > 2:
                    line = line[:-2] + "\u2026"
                lines[i] = line
            text = "\n".join(lines)
            text_width = max(self.label_font.measure(line) for line in lines)
            box_height = 23 + 17 * (len(lines) - 1)
            total_width = text_width + 14
            right = x >= width * 0.5
            shifts = [(12, -25), (12, 8), (12, -49), (-total_width - 12, -25), (-total_width - 12, 8)]
            if not right:
                shifts = [(-total_width - 12, -25), (-total_width - 12, 8), (-total_width - 12, -49), (12, -25), (12, 8)]
            placement = None
            for dx, dy in shifts:
                bx, by = x + dx, y + dy
                box = (bx, by, bx + total_width, by + box_height)
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
        self._cancel_hover()
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
            if self.placement_state == "placing":
                position = self.scene.position_at(event.x, event.y, self._layer_id())
                if position is not None:
                    self.place_at(*position)
            elif self.scene.pick_preview(event.x, event.y):
                self.begin_placement()
            else:
                node_id = self._pick_at(event.x, event.y)
                if node_id == self.selected and node_id is not None:
                    self.begin_placement()
                elif node_id:
                    self.select_node(node_id)
                elif self.selected is not None or self._placement_origin is None:
                    position = self.scene.position_at(event.x, event.y, self._layer_id())
                    if position is not None:
                        self.place_at(*position)
        self._pressed = None
        self.canvas.configure(cursor="fleur")
        return "break"

    def place_at(self, depth: int, slot: int) -> bool:
        """Lock a new block or a picked-up block at a valid draft location."""
        moving = self.placement_state == "placing"
        if self.selected is not None and not moving and not self._allow_leave():
            return False
        layer = self._layer_id()
        size = self.size_var.get() if moving or self.selected is None else self._last_size
        if slot not in self.document.free_starts(layer, depth, BLOCK_SIZES[size], exclude_id=self.selected if moving else None):
            if moving:
                self._floating_position = depth, slot
                self._changed()
            else:
                self.editor_state.configure(text="That space is occupied. Choose another location or a smaller size.", fg=theme.ERROR)
            return False
        if moving or self.selected is None:
            # Positioning a draft keeps its title and notes.
            self._loading = True
            self.depth_var.set(depth)
            self.slot_var.set(f"{slot + 1:02d}")
            self._loading = False
        else:
            self._load_editor(None, (layer, self._protocol_id(), depth), slot=slot, size=size)
        self._cancel_hover()
        self.placement_state = "locked"
        self._floating_position = None
        self._placement_origin = self._preview_candidate()
        self._changed()
        return True

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
            hit = self._pick_at(x, y)
            self.canvas.configure(cursor="hand2" if hit or self.scene.pick_preview(x, y) else "fleur")
            if self.placement_state == "placing" and self._pressed is None:
                position = self.scene.position_at(x, y, self._layer_id())
                if position is not None:
                    self._floating_position = position
                    self._changed()
                    self.canvas.configure(cursor="crosshair")
                else:
                    self._refresh_preview()
                self.request_render()

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
        ids = [n.id for n in self.document.nodes if self.scene.is_visible(n)]
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
