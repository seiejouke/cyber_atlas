"""Cluster controls and independent child notes in both atlas views."""
from dataclasses import replace
import tkinter as tk
from tkinter import messagebox, ttk

from . import theme
from .model import AtlasError, ORBIT_SLOTS, Subconcept
from .orbit_scene import orbit_position


class ClusterManager:
    def __init__(self, app):
        self.app, self.root = app, app.root
        self.editing = False
        self.child_id = self.parent_id = None
        self.moving = False
        self._loading = False
        self._loaded = None
        self._list_state = None
        self._coordinate_rows = [widget for widget in app.editor_form.grid_slaves()
                                 if int(widget.grid_info()["row"]) in (4, 5, 6, 7)]
        self.name = tk.StringVar()
        self.slot = tk.StringVar(value="01")
        left = app.canvas.master
        left.rowconfigure(2, weight=0)
        left.rowconfigure(3, weight=1)
        app.canvas.grid_configure(row=3)
        self.bar = ttk.Frame(left, style="Panel.TFrame", padding=(10, 5))
        self.bar.columnconfigure(0, weight=1)
        self.summary = ttk.Label(self.bar, style="Muted.TLabel")
        self.summary.grid(row=0, column=0, sticky="w")
        self.expand_button = ttk.Button(self.bar, text="Expand", style="Inline.TButton", command=self.toggle_expand)
        self.expand_button.grid(row=0, column=1, padx=3)
        self.focus_button = ttk.Button(self.bar, text="Focus cluster", style="Inline.TButton", command=self.toggle_focus)
        self.focus_button.grid(row=0, column=2, padx=3)
        self.add_button = ttk.Button(self.bar, text="+ Subconcept", style="Inline.TButton", command=self.add)
        self.add_button.grid(row=0, column=3)

        self.list_frame = ttk.Frame(app.editor_form, style="Panel.TFrame")
        self.list_frame.columnconfigure(0, weight=1)
        self.list_title = ttk.Label(self.list_frame, style="Muted.TLabel")
        self.list_title.grid(row=0, column=0, sticky="w", pady=(7, 3))
        ttk.Button(self.list_frame, text="Explore in Nodes", style="Inline.TButton", command=self.explore).grid(row=0, column=1)
        self.child_list = tk.Listbox(self.list_frame, height=4, exportselection=False, bg=theme.FIELD, fg=theme.TEXT,
                                    selectbackground="#29556a", relief="flat", font=(app.family, 9))
        self.child_list.grid(row=1, column=0, columnspan=2, sticky="ew")
        list_scroll = ttk.Scrollbar(self.list_frame, command=self.child_list.yview)
        list_scroll.grid(row=1, column=2, sticky="ns")
        self.child_list.configure(yscrollcommand=list_scroll.set)
        self.child_list.bind("<<ListboxSelect>>", self._list_selected)

        self.form = ttk.Frame(app.right_panel, style="Panel.TFrame", padding=10)
        self.form.columnconfigure(0, weight=1)
        self.form.rowconfigure(7, weight=1)
        header = ttk.Frame(self.form, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.heading = ttk.Label(header, text="EDIT SUBCONCEPT", style="Muted.TLabel", font=(app.mono, 9))
        self.heading.grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Parent note", style="Inline.TButton", command=self.parent_note).grid(row=0, column=1)
        self.context = ttk.Label(self.form, wraplength=310, style="Muted.TLabel")
        self.context.grid(row=1, column=0, sticky="ew", pady=(10, 12))
        ttk.Label(self.form, text="Subconcept", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        self.name_entry = ttk.Entry(self.form, textvariable=self.name)
        self.name_entry.grid(row=3, column=0, sticky="ew", pady=(4, 12))
        orbit = ttk.Frame(self.form, style="Panel.TFrame")
        orbit.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(orbit, text="Orbit position", style="Muted.TLabel").pack(side="left")
        self.slot_box = ttk.Combobox(orbit, textvariable=self.slot, values=tuple(f"{i+1:02d}" for i in range(ORBIT_SLOTS)), width=4)
        self.slot_box.pack(side="right")
        self.move_button = ttk.Button(self.form, text="Move in orbit", command=self.move)
        self.move_button.grid(row=5, column=0, sticky="w", pady=(0, 12))
        ttk.Label(self.form, text="Personal notes", style="Muted.TLabel").grid(row=6, column=0, sticky="w")
        field = ttk.Frame(self.form, style="Panel.TFrame")
        field.grid(row=7, column=0, sticky="nsew", pady=(4, 8))
        field.columnconfigure(0, weight=1)
        field.rowconfigure(0, weight=1)
        self.notes = tk.Text(field, wrap="word", width=31, height=10, undo=True, bg=theme.FIELD, fg=theme.TEXT,
                             insertbackground=theme.TEXT, selectbackground="#29556a", relief="flat", padx=11, pady=10,
                             highlightthickness=1, highlightbackground=theme.BORDER, font=(app.family, 10))
        self.notes.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(field, command=self.notes.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.notes.configure(yscrollcommand=scroll.set)
        self.status = ttk.Label(self.form, wraplength=305, style="Muted.TLabel")
        self.status.grid(row=8, column=0, sticky="ew", pady=(0, 8))
        buttons = ttk.Frame(self.form, style="Panel.TFrame")
        buttons.grid(row=9, column=0, sticky="ew")
        self.save_button = ttk.Button(buttons, text="Save note", style="Primary.TButton", command=self.save)
        self.save_button.pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text="Cancel", command=self.parent_note).pack(side="left", padx=5)
        self.delete_button = ttk.Button(buttons, text="Delete", command=self.delete)
        self.delete_button.pack(side="left")
        ttk.Separator(self.form).grid(row=10, column=0, sticky="ew", pady=12)
        files = ttk.Frame(self.form, style="Panel.TFrame")
        files.grid(row=11, column=0, sticky="ew")
        ttk.Button(files, text="Export JSON", command=app.export_json).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(files, text="Import JSON", command=app.import_json).pack(side="left", expand=True, fill="x")
        for var in (self.name, self.slot):
            var.trace_add("write", lambda *_: self.changed())
        self.notes.bind("<<Modified>>", lambda _: self.changed())

    def state(self):
        return self.name.get(), self.notes.get("1.0", "end-1c"), self.slot.get()

    @property
    def dirty(self):
        return self.editing and self.state() != self._loaded

    def allow_leave(self):
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved subconcept", "Save this subconcept before continuing?", parent=self.root)
        return self.save() if answer is True else answer is False

    def close_editor(self):
        self.editing = False
        self.child_id = self.parent_id = None
        self.moving = False
        self.form.pack_forget()
        self.app.scene.selected_child = None
        self.app.scene.set_subconcepts(self.app.document.subconcepts)
        if self.app._template_origin is None:
            self.app.editor_form.pack(fill="both", expand=True)

    def _open(self, parent, child=None, slot=0):
        self.app._load_editor(parent)
        self.editing = True
        self.parent_id, self.child_id = parent.id, child.id if child else None
        self.moving = child is None
        self._loading = True
        self.name.set(child.name if child else "")
        self.slot.set(f"{(child.orbit_slot if child else slot)+1:02d}")
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", child.notes if child else "")
        self.notes.edit_reset()
        self.notes.edit_modified(False)
        self._loaded = self.state()
        self._loading = False
        self.app.editor_form.pack_forget()
        self.form.pack(fill="both", expand=True)
        self.heading.configure(text="EDIT SUBCONCEPT" if child else "CREATE SUBCONCEPT")
        self.context.configure(text=f"Parent: {parent.name}\nRelationship: Is a type of\nLayer: {self.app.document.design.layer(parent.layer).name}")
        self.delete_button.state(["!disabled"] if child else ["disabled"])
        self.app.scene.expand_orbit(parent.id)
        if self.app.scene.mode == "nodes" and self.app.scene.focused_parent is None:
            self.app.scene.focus_orbit()
        self.changed()
        self.name_entry.focus_set()

    def add(self):
        if self.app._template_origin is not None or not self.app._allow_leave():
            return False
        parent = self.app.document.get(self.app.selected)
        if parent is None:
            return False
        used = {child.orbit_slot for child in self.app.document.children(parent.id)}
        slot = next((index for index in (0, 2, 4, 6, 1, 3, 5, 7) if index not in used), None)
        if slot is None:
            messagebox.showinfo("Orbit is full", "This version supports eight subconcepts per parent.", parent=self.root)
            return False
        self._open(parent, slot=slot)
        return True

    def select_child(self, child_id):
        if self.app._template_origin is not None:
            return False
        if self.editing and self.child_id == child_id:
            return True
        child = self.app.document.child(child_id)
        if child is None or not self.app._allow_leave():
            return False
        self._open(self.app.document.get(child.parent_id), child)
        return True

    def parent_note(self):
        if not self.app._allow_leave():
            return False
        parent = self.app.document.get(self.parent_id or self.app.selected)
        self.app._load_editor(parent)
        return True

    def changed(self):
        if self._loading or not self.editing:
            return
        self.notes.edit_modified(False)
        self.slot_box.configure(state="readonly" if self.moving else "disabled")
        self.move_button.configure(text="Cancel move" if self.moving and self.child_id else "Move in orbit")
        self.move_button.state(["!disabled"] if self.child_id else ["disabled"])
        try:
            slot = int(self.slot.get()) - 1
            if not 0 <= slot < ORBIT_SLOTS:
                raise ValueError
            if any(child.orbit_slot == slot and child.id != self.child_id for child in self.app.document.children(self.parent_id)):
                raise AtlasError("That orbit position is occupied. Choose another position.")
            self.save_button.state(["!disabled"])
            self.status.configure(text="Unsaved changes" if self.dirty else "Saved / Is a type of")
            child = Subconcept(self.child_id or "orbit-preview", self.parent_id, self.name.get().strip() or "New subconcept", orbit_slot=slot)
            others = tuple(entry for entry in self.app.document.subconcepts if entry.id != self.child_id)
            self.app.scene.selected_child = child.id
            self.app.scene.set_subconcepts(others + (child,))
        except (ValueError, AtlasError) as exc:
            self.save_button.state(["disabled"])
            self.status.configure(text=str(exc) or "Choose an orbit position from 1 to 8.")
        self.app.request_render()

    def move(self):
        if not self.editing or self.child_id is None:
            return
        self.moving = not self.moving
        if not self.moving:
            self.slot.set(f"{self.app.document.child(self.child_id).orbit_slot+1:02d}")
        self.changed()

    def save(self):
        if not self.editing:
            return False
        try:
            slot = int(self.slot.get()) - 1
            child = Subconcept(self.child_id, self.parent_id, self.name.get().strip(), self.notes.get("1.0", "end-1c"), slot) if self.child_id else Subconcept.create(
                self.parent_id, self.name.get(), self.notes.get("1.0", "end-1c"), orbit_slot=slot)
            candidate = self.app.document.with_child(child)
        except (ValueError, AtlasError) as exc:
            self.status.configure(text=str(exc))
            return False
        if not self.app._commit(candidate):
            return False
        self.child_id = child.id
        self.moving = False
        self._loaded = self.state()
        self.heading.configure(text="EDIT SUBCONCEPT")
        self.delete_button.state(["!disabled"])
        self.changed()
        return True

    def delete(self):
        child = self.app.document.child(self.child_id)
        if child is None or not messagebox.askyesno("Delete subconcept", f"Delete '{child.name}' and its notes?\n\nThe parent and other children will be kept.", parent=self.root):
            return False
        if not self.app._commit(self.app.document.without_child(child.id)):
            return False
        self.app._load_editor(self.app.document.get(child.parent_id))
        return True

    def toggle_expand(self):
        if not self.app._allow_leave():
            return
        parent = self.app.document.get(self.app.selected)
        if parent is None:
            return
        if self.app.scene.mode != "nodes":
            self.explore()
            return
        expanded = self.app.scene.expanded_parent == parent.id
        self.app._load_editor(parent)
        if expanded:
            self.app.scene.collapse_orbit()
        else:
            self.app.scene.expand_orbit(parent.id)
            self.app.scene.focus_orbit()
        self.app.request_render()

    def toggle_focus(self):
        scene = self.app.scene
        if scene.focused_parent is not None:
            scene.clear_orbit_focus()
        else:
            scene.expand_orbit(self.app.selected)
            scene.focus_orbit()
        self.app.request_render()

    def explore(self):
        self.app.set_view_mode("nodes")
        self.app.scene.expand_orbit(self.app.selected)
        self.app.scene.focus_orbit()
        self.app.request_render()

    def _list_selected(self, _event=None):
        selection = self.child_list.curselection()
        if selection:
            children = self.app.document.children(self.app.selected)
            if selection[0] < len(children):
                self.select_child(children[selection[0]].id)

    def sync(self):
        parent = self.app.document.get(self.app.selected)
        compact = (parent is not None and bool(self.app.document.children(parent.id)) and not self.editing
                   and self.app._node_move_origin is None and self.app.placement_state != "placing")
        for widget in self._coordinate_rows:
            widget.grid_remove() if compact else widget.grid()
        if self.app._template_origin is not None or parent is None:
            self.bar.grid_remove()
            self.list_frame.grid_remove()
            return
        self.bar.grid(row=2, column=0, sticky="ew")
        children = self.app.document.children(parent.id)
        expanded = self.app.scene.mode == "nodes" and self.app.scene.expanded_parent == parent.id
        name = parent.name if len(parent.name) < 18 else parent.name[:15] + "..."
        self.summary.configure(text=f"{name} / {len(children)} subconcepts")
        self.expand_button.configure(text="Collapse" if expanded else "Expand" if self.app.scene.mode == "nodes" else "Explore")
        self.expand_button.state(["!disabled"] if children else ["disabled"])
        self.add_button.state(["disabled"] if len(children) == ORBIT_SLOTS else ["!disabled"])
        self.focus_button.configure(text="Show atlas" if self.app.scene.focused_parent else "Focus cluster")
        self.focus_button.state(["!disabled"] if expanded else ["disabled"])
        if self.app.scene.orbit_collision:
            self.summary.configure(text="Crowded: Focus cluster")
        if children and not self.editing:
            self.list_frame.grid(row=15, column=0, sticky="ew")
            self.list_title.configure(text=f"Subconcepts ({len(children)})")
            state = tuple((child.id, child.name) for child in children)
            if state != self._list_state:
                self.child_list.delete(0, "end")
                for child in children:
                    self.child_list.insert("end", child.name)
                self._list_state = state
        else:
            self.list_frame.grid_remove()

    def draw(self):
        if self.app._template_origin is not None:
            return
        scene, canvas = self.app.scene, self.app.canvas
        parent = scene.orbit_parent()
        if scene.mode == "nodes" and parent is not None:
            boxes = [box for _, box in self.app._label_hits] + list(self.app._axis_label_boxes)
            for child in sorted(scene.subconcepts, key=lambda child: child.id != scene.selected_child):
                actor = scene.orbit_actors.get(child.id)
                if actor is None or not actor.GetVisibility():
                    continue
                x, y, depth = scene.project(orbit_position(parent, child.orbit_slot, scene.design))
                if not (0 <= depth <= 1 and 0 < x < scene.width and 0 < y < scene.height):
                    continue
                selected = child.id == scene.selected_child
                if scene.pick(x, y) != child.id:
                    continue
                if selected:
                    canvas.create_oval(x-11, y-11, x+11, y+11, outline=theme.ACCENT, width=2, tags="overlay")
                label = child.name if len(child.name) <= 31 else child.name[:28] + "..."
                width = self.app.label_font.measure(label) + 12
                for dx, dy in ((12, -23), (12, 8), (-width-12, -23), (-width-12, 8), (12, -47), (-width-12, 32)):
                    box = x+dx, y+dy, x+dx+width, y+dy+23
                    if box[0] < 5 or box[2] > scene.width-5 or box[1] < 30 or box[3] > scene.height-72:
                        continue
                    if any(not (box[2]+3 < old[0] or box[0]-3 > old[2] or box[3]+3 < old[1] or box[1]-3 > old[3]) for old in boxes):
                        continue
                    boxes.append(box)
                    canvas.create_rectangle(*box, fill=theme.PANEL, outline=theme.ACCENT if selected else theme.BORDER, tags="overlay")
                    canvas.create_text(box[0]+6, box[1]+11, text=label, anchor="w", fill=theme.ACCENT if selected else theme.TEXT,
                                       font=self.app.label_font, tags="overlay")
                    self.app._label_hits.append((child.id, box))
                    break
        root = self.app.document.get(self.app.selected)
        if root is not None and self.app.document.children(root.id) and scene.is_visible(root):
            point = scene.node_anchor(root) if scene.mode == "nodes" else scene.meshes[root.id].label_anchor
            x, y, _ = scene.project(point)
            canvas.create_text(x, y+22, text=f"{len(self.app.document.children(root.id))} subconcepts", fill=theme.MUTED,
                               font=(self.app.family, 8), tags="overlay")
