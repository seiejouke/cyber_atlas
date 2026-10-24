"""A local design draft. Only Apply writes the complete, validated atlas."""
from __future__ import annotations

from dataclasses import replace
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from typing import Callable
from uuid import uuid4

from . import theme
from .design_draft import DesignDraft
from .model import Atlas, AtlasError, LABEL_MODES, Layer, Node, Protocol


class ReassignDialog(tk.Toplevel):
    def __init__(self, parent, entry, choices, count):
        super().__init__(parent)
        self.title("Reassign blocks")
        self.configure(bg=theme.BG)
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        self.choices = {choice.name: choice.id for choice in choices}
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f'“{entry.name}” is used by {count} block(s).', wraplength=420).pack(anchor="w")
        ttk.Label(frame, text="Choose where those blocks should move before removing this entry.",
                  wraplength=420).pack(anchor="w", pady=(6, 12))
        self.choice = tk.StringVar(self)
        box = ttk.Combobox(frame, values=tuple(self.choices), textvariable=self.choice, state="readonly", width=40)
        box.pack(fill="x")
        self.confirm = ttk.Button(frame, text="Reassign and remove", command=self.accept, state="disabled")
        self.confirm.pack(side="right", pady=(16, 0))
        ttk.Button(frame, text="Cancel", command=self.destroy).pack(side="right", padx=8, pady=(16, 0))
        self.choice.trace_add("write", lambda *_: self.confirm.state(["!disabled"]))
        self.bind("<Escape>", self.cancel)
        self.grab_set()
        box.focus_set()

    def accept(self):
        if self.choice.get() in self.choices:
            self.result = self.choices[self.choice.get()]
            self.destroy()

    def cancel(self, _event=None):
        self.destroy()
        return "break"


class ReassignListDialog(tk.Toplevel):
    """Explicit destinations for every removed entry that still has blocks."""
    def __init__(self, parent, draft: DesignDraft, kind: str):
        super().__init__(parent)
        self.draft, self.kind, self.result = draft, kind, False
        self.title(f"Reassign {kind}")
        self.configure(bg=theme.BG)
        self.transient(parent)
        self.geometry("650x480")
        self.minsize(600, 400)
        self.choices = {entry.name: entry.id for entry in draft.entries(kind)}
        self.variables = {}
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text=f"Choose a new {kind[:-1]} for blocks from each removed entry.",
                  wraplength=590).grid(row=0, column=0, sticky="w", pady=(0, 12))
        body = ttk.Frame(frame)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        canvas = tk.Canvas(body, bg=theme.BG, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(body, command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        rows = ttk.Frame(canvas)
        rows.columnconfigure(1, weight=1)
        window = canvas.create_window(0, 0, anchor="nw", window=rows)
        rows.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        for row, entry in enumerate(draft.pending(kind)):
            ttk.Label(rows, text=f"{entry.name}\n{entry.count} block(s)", wraplength=225,
                      width=28).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=7)
            variable = tk.StringVar(self)
            self.variables[entry.id] = variable
            ttk.Combobox(rows, textvariable=variable, values=tuple(self.choices), state="readonly",
                         width=25).grid(row=row, column=1, sticky="ew", pady=7)
            variable.trace_add("write", lambda *_: self._selection_changed())
        self.error = tk.StringVar(self)
        tk.Label(frame, textvariable=self.error, bg=theme.BG, fg=theme.ERROR, wraplength=600,
                 justify="left", anchor="w").grid(row=2, column=0, sticky="ew", pady=10)
        actions = ttk.Frame(frame)
        actions.grid(row=3, column=0, sticky="ew")
        self.confirm = ttk.Button(actions, text="Reassign blocks", command=self.accept, state="disabled")
        self.confirm.pack(side="right")
        ttk.Button(actions, text="Cancel", command=self.cancel).pack(side="right", padx=8)
        self.bind("<Escape>", self.cancel)
        self.grab_set()

    def _selection_changed(self):
        ready = all(variable.get() in self.choices for variable in self.variables.values())
        self.confirm.state(["!disabled"] if ready else ["disabled"])

    def accept(self):
        if not all(variable.get() in self.choices for variable in self.variables.values()):
            return
        moves = {key: self.choices[variable.get()] for key, variable in self.variables.items()}
        try:
            self.draft.reassign(self.kind, moves)
        except AtlasError as exc:
            self.error.set(str(exc))
            return
        self.result = True
        self.destroy()

    def cancel(self, _event=None):
        self.destroy()
        return "break"


class EntryEditor(ttk.Frame):
    def __init__(self, parent, owner: DesignEditor, kind: str):
        super().__init__(parent, padding=14)
        self.owner, self.kind = owner, kind
        self.current = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        hint = "Top → bottom. Select a layer to rename, recolor, or move it." if kind == "layers" else "Select a protocol to rename it."
        ttk.Label(self, text=hint, wraplength=560).grid(row=0, column=0, sticky="w", pady=(0, 10))
        list_frame = ttk.Frame(self)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(list_frame, bg=theme.FIELD, fg=theme.TEXT, selectbackground="#285268",
                                 selectforeground=theme.TEXT, exportselection=False, relief="flat",
                                 highlightthickness=1, highlightbackground=theme.BORDER, height=10, activestyle="none")
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scroll.set)
        self.empty_label = ttk.Label(list_frame, text="No layers yet. Click Add layer." if kind == "layers"
                                     else "No protocols. Add protocol is optional.", wraplength=400)
        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, sticky="ew", pady=10)
        ttk.Button(actions, text="Add layer" if kind == "layers" else "Add protocol", command=self.add).pack(side="left")
        self.remove_button = ttk.Button(actions, text="Remove", command=self.remove)
        self.remove_button.pack(side="left", padx=6)
        self.clear_button = ttk.Button(actions, text="Remove list" if kind == "layers" else "Remove protocols",
                                       command=self.clear_list)
        self.clear_button.pack(side="left")
        if kind == "layers":
            self.higher = ttk.Button(actions, text="Higher ↑", command=lambda: self.move(1))
            self.higher.pack(side="right")
            self.lower = ttk.Button(actions, text="Lower ↓", command=lambda: self.move(-1))
            self.lower.pack(side="right", padx=6)
        fields = ttk.Frame(self)
        fields.grid(row=3, column=0, sticky="ew")
        fields.columnconfigure(1, weight=1)
        ttk.Label(fields, text="Name").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.name = tk.StringVar(self)
        self.name_entry = ttk.Entry(fields, textvariable=self.name)
        self.name_entry.grid(row=0, column=1, sticky="ew")
        self.color = tk.StringVar(self)
        if kind == "layers":
            ttk.Label(fields, text="Color").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0))
            color_row = ttk.Frame(fields)
            color_row.grid(row=1, column=1, sticky="ew", pady=(8, 0))
            self.swatch = tk.Label(color_row, width=3, bg=theme.ACCENT)
            self.swatch.pack(side="left", fill="y", padx=(0, 8))
            self.color_entry = ttk.Entry(color_row, textvariable=self.color, width=12)
            self.color_entry.pack(side="left")
            self.color_button = ttk.Button(color_row, text="Choose…", command=self.choose_color)
            self.color_button.pack(side="left", padx=8)
        self.update_button = ttk.Button(fields, text="Update entry", command=self.update_entry)
        self.update_button.grid(row=2, column=1, sticky="e", pady=(10, 0))
        pending = ttk.Frame(self)
        pending.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        pending.columnconfigure(0, weight=1)
        self.pending_label = ttk.Label(pending, wraplength=380)
        self.pending_label.grid(row=0, column=0, sticky="w")
        self.reassign_button = ttk.Button(pending, text="Reassign blocks…", command=self.reassign_blocks)
        self.reassign_button.grid(row=0, column=1, padx=(10, 0))
        self.listbox.bind("<<ListboxSelect>>", self.selected)
        self.refresh()

    @property
    def entries(self):
        return self.owner.draft.entries(self.kind)

    def refresh(self, selected_id=None):
        entries = self.entries
        self.displayed = tuple(reversed(entries)) if self.kind == "layers" else entries
        self.listbox.delete(0, "end")
        for entry in self.displayed:
            count = sum(getattr(n, "layer" if self.kind == "layers" else "protocol") == entry.id for n in self.owner.draft.nodes)
            prefix = f"L{entries.index(entry) + 1}   " if self.kind == "layers" else ""
            self.listbox.insert("end", f"{prefix}{entry.name}   ·   {count} block(s)")
        widgets = [self.remove_button, self.clear_button, self.update_button, self.name_entry]
        if self.kind == "layers":
            widgets += [self.higher, self.lower, self.color_entry, self.color_button]
        for widget in widgets:
            widget.state(["!disabled"] if entries else ["disabled"])
        pending = self.owner.draft.pending(self.kind)
        count = sum(entry.count for entry in pending)
        self.pending_label.configure(text=f"{count} block(s) need a new {self.kind[:-1]}." if pending else "All blocks are assigned.")
        self.reassign_button.state(["!disabled"] if pending and entries else ["disabled"])
        if entries:
            self.empty_label.grid_remove()
            entry = next((e for e in entries if e.id == selected_id), self.displayed[0])
            self.select(entry.id)
        else:
            self.current = None
            self.name.set("")
            self.color.set("")
            if self.kind == "layers":
                self.swatch.configure(bg=theme.FIELD)
            self.empty_label.grid(row=0, column=0, padx=12, pady=12)

    def select(self, entry_id):
        entry = next(e for e in self.entries if e.id == entry_id)
        self.current = entry_id
        index = self.displayed.index(entry)
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(index)
        self.listbox.see(index)
        self.name.set(entry.name)
        if self.kind == "layers":
            self.color.set(entry.color)
            self.swatch.configure(bg=entry.color)
            self.higher.state(["disabled"] if entry == self.entries[-1] else ["!disabled"])
            self.lower.state(["disabled"] if entry == self.entries[0] else ["!disabled"])

    def selected(self, _event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        target = self.displayed[selection[0]].id
        if target == self.current:
            return
        if self.update_entry():
            self.select(target)
        else:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(next(i for i, e in enumerate(self.displayed) if e.id == self.current))

    def update_entry(self) -> bool:
        if self.current is None:
            return True
        try:
            entries = tuple(replace(e, name=self.name.get().strip(), **({"color": self.color.get().strip()} if self.kind == "layers" else {}))
                            if e.id == self.current else e for e in self.entries)
            self.owner.draft.set_entries(self.kind, entries)
        except AtlasError as exc:
            self.owner.error.set(str(exc))
            return False
        self.refresh(self.current)
        self.owner.error.set("")
        self.owner.update_summary()
        return True

    def choose_color(self):
        color = colorchooser.askcolor(color=self.color.get(), parent=self.owner, title="Layer color")[1]
        if color:
            self.color.set(color)
            self.swatch.configure(bg=color)

    def add(self):
        if not self.update_entry():
            return
        stem = "New layer" if self.kind == "layers" else "New protocol"
        name, number = stem, 2
        while name.casefold() in {e.name.casefold() for e in self.entries}:
            name, number = f"{stem} {number}", number + 1
        entry = Layer(uuid4().hex, name, theme.ACCENT) if self.kind == "layers" else Protocol(uuid4().hex, name)
        try:
            self.owner.draft.set_entries(self.kind, self.entries + (entry,))
        except AtlasError as exc:
            self.owner.error.set(str(exc))
            return
        self.refresh(entry.id)
        self.owner.update_summary()
        self.name_entry.focus_set()
        self.name_entry.selection_range(0, "end")

    def move(self, direction):
        if self.current is None or not self.update_entry():
            return
        entries = list(self.entries)
        index = next(i for i, e in enumerate(entries) if e.id == self.current)
        target = index + direction
        if not 0 <= target < len(entries):
            return
        entries[index], entries[target] = entries[target], entries[index]
        self.owner.draft.set_entries("layers", tuple(entries))
        self.refresh(self.current)

    def remove(self, replacement_id=None) -> bool:
        if not self.entries:
            return False
        if len(self.entries) == 1:
            self.owner.error.set("Use Remove list to clear the final layer." if self.kind == "layers"
                                 else "Use Remove protocols to clear the final protocol.")
            return False
        if not self.update_entry():
            return False
        entry = next(e for e in self.entries if e.id == self.current)
        remaining = tuple(e for e in self.entries if e.id != entry.id)
        attribute = "layer" if self.kind == "layers" else "protocol"
        count = sum(getattr(n, attribute) == entry.id for n in self.owner.draft.nodes)
        if count and replacement_id is None:
            dialog = ReassignDialog(self.owner, entry, remaining, count)
            self.owner.wait_window(dialog)
            self.owner.grab_set()
            replacement_id = dialog.result
            if replacement_id is None:
                return False
        if count and replacement_id not in {e.id for e in remaining}:
            self.owner.error.set("Choose an existing replacement entry.")
            return False
        try:
            self.owner.draft.remove(self.kind, entry.id, replacement_id)
        except AtlasError as exc:
            self.owner.error.set(str(exc))
            return False
        self.refresh()
        self.owner.update_summary()
        self.owner.error.set("")
        return True

    def clear_list(self) -> bool:
        if not self.entries:
            return False
        question = f"Are you sure you want to remove all {self.kind}?"
        detail = f"This clears {len(self.entries)} entries from the design draft."
        if self.kind == "protocols":
            detail = ("This saves the empty protocol list immediately. Blocks keep their positions and notes, "
                      "and show No protocol. Other design changes are saved with Apply design.")
        elif self.owner.draft.nodes:
            detail += f"\n\nAll {len(self.owner.draft.nodes)} blocks and their notes will be kept. Add replacements and reassign those blocks before applying."
        else:
            detail += f"\n\nAdd at least one {self.kind[:-1]} before applying."
        if not messagebox.askyesno("Remove list?" if self.kind == "layers" else "Remove protocols?",
                                  f"{question}\n\n{detail}", parent=self.owner, default=messagebox.NO):
            return False
        if self.kind == "protocols":
            return self.owner.clear_protocols_now()
        self.owner.draft.clear(self.kind)
        self.refresh()
        self.owner.error.set("")
        self.owner.update_summary()
        return True

    def reassign_blocks(self) -> bool:
        if not self.entries or not self.owner.draft.pending(self.kind) or not self.update_entry():
            return False
        dialog = ReassignListDialog(self.owner, self.owner.draft, self.kind)
        self.owner.wait_window(dialog)
        self.owner.grab_set()
        self.refresh(self.current)
        self.owner.update_summary()
        return dialog.result


class DesignEditor(tk.Toplevel):
    def __init__(self, parent, document: Atlas, on_apply: Callable[[Atlas], bool]):
        super().__init__(parent)
        self.draft, self.on_apply = DesignDraft(document), on_apply
        self._saved_document = document
        self._protocols_saved = False
        self.title("Edit atlas design")
        self.configure(bg=theme.BG)
        self.transient(parent)
        self.geometry("720x690")
        self.minsize(650, 630)
        self.error = tk.StringVar(self)
        self.readiness = tk.StringVar(self)
        self.layer_caption = tk.StringVar(self, document.design.layer_caption)
        self.protocol_caption = tk.StringVar(self, document.design.protocol_caption)
        self.label_mode = tk.StringVar(self, LABEL_MODES[document.design.label_mode])
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        ttk.Label(frame, text="Atlas design", font=("Segoe UI", 17, "bold")).grid(row=0, column=0, sticky="w")
        self.summary = ttk.Label(frame)
        self.summary.grid(row=1, column=0, sticky="w", pady=(5, 12))
        self.notebook = ttk.Notebook(frame)
        self.notebook.grid(row=2, column=0, sticky="nsew")
        self.layers = EntryEditor(self.notebook, self, "layers")
        self.protocols = EntryEditor(self.notebook, self, "protocols")
        self.notebook.add(self.layers, text="Layers")
        self.notebook.add(self.protocols, text="Protocols")
        labels = ttk.Frame(self.notebook, padding=18)
        labels.columnconfigure(0, weight=1)
        self.notebook.add(labels, text="Field names & labels")
        for row, (caption, variable) in enumerate((("Layer field name", self.layer_caption), ("Protocol field name", self.protocol_caption))):
            ttk.Label(labels, text=caption).grid(row=row * 2, column=0, sticky="w", pady=(8, 4))
            ttk.Entry(labels, textvariable=variable).grid(row=row * 2 + 1, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(labels, text="Block labels").grid(row=4, column=0, sticky="w", pady=(8, 4))
        self.label_box = ttk.Combobox(labels, textvariable=self.label_mode, values=tuple(LABEL_MODES.values()), state="readonly")
        self.label_box.grid(row=5, column=0, sticky="ew")
        self.label_preview = ttk.Label(labels, wraplength=560)
        self.label_preview.grid(row=6, column=0, sticky="w", pady=16)
        self.label_mode.trace_add("write", lambda *_: self.update_summary())
        ttk.Label(labels, text="The OSI preset is the starting design. Your changes are saved with this atlas, including JSON exports. Empty atlas keeps this design.",
                  wraplength=560).grid(row=7, column=0, sticky="w", pady=8)
        ttk.Label(frame, textvariable=self.readiness, wraplength=650).grid(row=3, column=0, sticky="w", pady=(10, 0))
        tk.Label(frame, textvariable=self.error, bg=theme.BG, fg=theme.ERROR, anchor="w", justify="left",
                 wraplength=650).grid(row=4, column=0, sticky="ew", pady=(4, 4))
        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0, sticky="ew")
        self.apply_button = ttk.Button(actions, text="Apply design", style="Primary.TButton", command=self.apply)
        self.apply_button.pack(side="right")
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", self.cancel)
        self.update_summary()
        self.grab_set()

    def cancel(self, _event=None):
        self.destroy()
        return "break"

    @property
    def working(self) -> Atlas:
        """A validated snapshot, available whenever the draft is complete."""
        return self.draft.to_atlas()

    def clear_protocols_now(self) -> bool:
        # Commit only the protocol removal from the last saved document. Layer
        # edits (including an empty draft list) remain local until Apply.
        candidate = self._saved_document.without_protocols()
        if candidate != self._saved_document and not self.on_apply(candidate):
            self.error.set("The protocol list could not be saved. It has been kept.")
            return False
        self._saved_document = candidate
        self.draft.clear("protocols")
        self._protocols_saved = True
        self.protocols.refresh()
        self.error.set("")
        self.update_summary()
        return True

    def update_summary(self):
        draft = self.draft
        self.summary.configure(text=f"{len(draft.layers)} layers · {len(draft.protocols)} protocols · {len(draft.nodes)} blocks")
        notice = "Protocols removed and saved. " if self._protocols_saved else ""
        self.readiness.set(notice + draft.readiness_hint)
        self.apply_button.state(["!disabled"] if draft.ready else ["disabled"])
        if hasattr(self, "label_preview"):
            if not draft.layers:
                self.label_preview.configure(text="Add a layer to preview block labels.")
                return
            design = draft.design
            layer_ids = {entry.id for entry in draft.layers}
            protocol_ids = {None} | {entry.id for entry in draft.protocols}
            node = next((n for n in draft.nodes if n.layer in layer_ids and n.protocol in protocol_ids), None) or Node(
                "label-preview", "Block title", design.layers[0].id, design.protocols[0].id if design.protocols else None, 0)
            mode = next(key for key, text in LABEL_MODES.items() if text == self.label_mode.get())
            text = replace(design, label_mode=mode).block_label(node)
            self.label_preview.configure(text=f"Preview: {text}")

    def apply(self) -> bool:
        if not self.draft.ready:
            self.update_summary()
            return False
        if not self.layers.update_entry() or not self.protocols.update_entry():
            return False
        try:
            mode = next(key for key, value in LABEL_MODES.items() if value == self.label_mode.get())
            candidate = self.draft.to_atlas(layer_caption=self.layer_caption.get().strip(),
                                            protocol_caption=self.protocol_caption.get().strip(), label_mode=mode)
        except AtlasError as exc:
            self.error.set(str(exc))
            return False
        if not self.on_apply(candidate):
            self.error.set("The design could not be saved. Your draft is still open.")
            return False
        self.destroy()
        return True
