"""Saved process guides sharing the atlas's concepts, camera and native scene."""
from dataclasses import replace
import tkinter as tk
from tkinter import messagebox, ttk

from . import theme
from .flow import FlowRun
from .label_layout import inside, overlaps
from .model import AtlasError, FlowNote, FlowStep, FlowConnection
from .orientation import camera_basis
from .study_text import concept_link
from .study_ui import ConceptPicker, FlowConceptEditor, ScrollPanel, StudyText, set_text, text_field


class FlowManager:
    def __init__(self, app):
        self.app = app
        self.active = False
        self.draft = self.run = self.snapshot = None
        self.concept_editor = self.picker = None
        self.edited_concepts = set()
        self.linked_concept = None
        self._committing = False
        self._loading = False
        self.badge_boxes, self.badge_hits = [], []
        self.mode = tk.StringVar(value='edit')
        self.library = tk.StringVar()
        self.title = tk.StringVar()
        self.step_title = tk.StringVar()
        self.choice = tk.StringVar()
        self.edge_label = tk.StringVar()
        self.edge_target = tk.StringVar(value='End flow')
        self.edge_id = None
        self.panel = ttk.Frame(app.right_panel, style='Panel.TFrame', padding=10)
        self.panel.columnconfigure(0, weight=1)
        self.panel.rowconfigure(2, weight=1)
        header = ttk.Frame(self.panel, style='Panel.TFrame')
        header.grid(row=0, column=0, sticky='ew')
        header.columnconfigure(0, weight=1)
        self.library_box = ttk.Combobox(header, textvariable=self.library, state='readonly', width=20)
        self.library_box.grid(row=0, column=0, sticky='ew')
        self.library_box.bind('<<ComboboxSelected>>', self.choose_flow)
        ttk.Button(header, text='New', style='Compact.TButton', command=self.new_flow).grid(row=0, column=1, padx=(5, 3))
        ttk.Button(header, text='Delete', style='Compact.TButton', command=self.delete_flow).grid(row=0, column=2)
        self.heading = ttk.Label(self.panel, style='Muted.TLabel')
        self.heading.grid(row=1, column=0, sticky='w', pady=(8, 5))
        self.edit_scroll = ScrollPanel(self.panel)
        self.study_scroll = ScrollPanel(self.panel)
        self._build_editor(self.edit_scroll.body)
        self._build_study(self.study_scroll.body)
        self.study_scroll.canvas.bind('<Configure>', lambda _: self._fit_study(), add='+')
        self.status = ttk.Label(self.panel, style='Muted.TLabel', wraplength=315, justify='left')
        self.status.grid(row=3, column=0, sticky='ew', pady=(6, 5))
        self.edit_footer = ttk.Frame(self.panel, style='Panel.TFrame')
        self.edit_footer.columnconfigure(0, weight=1)
        ttk.Button(self.edit_footer, text='Save flow', style='Primary.TButton', command=self.save).grid(row=0, column=0, sticky='ew')
        self.study_footer = ttk.Frame(self.panel, style='Panel.TFrame')
        for column in (0, 1):
            self.study_footer.columnconfigure(column, weight=1)
        self.previous_button = ttk.Button(self.study_footer, text='Previous', command=self.previous)
        self.previous_button.grid(row=0, column=0, sticky='ew', padx=(0, 4))
        self.next_button = ttk.Button(self.study_footer, text='Next', style='Primary.TButton', command=self.next)
        self.next_button.grid(row=0, column=1, sticky='ew')
        self.focus_button = ttk.Button(self.study_footer, text='Focus step', command=self.focus_step)
        self.focus_button.grid(row=1, column=0, sticky='ew', padx=(0, 4), pady=(5, 0))
        self.edit_concept_button = ttk.Button(self.study_footer, text='Edit concept note', command=self.edit_concept)
        self.edit_concept_button.grid(row=1, column=1, sticky='ew', pady=(5, 0))
        self.bar = ttk.Frame(app.canvas.master, style='Panel.TFrame', padding=(10, 4))
        self.bar.columnconfigure(0, weight=1)
        self.summary = ttk.Label(self.bar, style='Muted.TLabel')
        self.summary.grid(row=0, column=0, sticky='w')
        for column, (label, mode) in enumerate((('Study', 'study'), ('Edit', 'edit')), 1):
            ttk.Radiobutton(self.bar, text=label, value=mode, variable=self.mode, style='View.Toolbutton',
                            command=lambda m=mode: self.set_mode(m)).grid(row=0, column=column)
        ttk.Button(self.bar, text='Return to atlas', style='Compact.TButton', command=self.close).grid(row=0, column=3, padx=(6, 0))
        actions = ttk.Frame(self.bar, style='Panel.TFrame')
        actions.grid(row=1, column=0, columnspan=4, sticky='w', pady=(3, 0))
        ttk.Button(actions, text='Show entire flow', style='Inline.TButton', command=self.show_entire_flow).pack(side='left', padx=(0, 6))
        ttk.Button(actions, text='Show flow layers', style='Inline.TButton', command=self.show_flow_layers).pack(side='left')

    def _build_editor(self, parent):
        def caption(text, row):
            ttk.Label(parent, text=text, style='Muted.TLabel').grid(row=row, column=0, sticky='w', pady=(7, 3))
        caption('Flow title', 0)
        ttk.Entry(parent, textvariable=self.title).grid(row=1, column=0, sticky='ew')
        caption('Introduction', 2)
        frame, self.introduction = text_field(parent, self.app, height=3)
        frame.grid(row=3, column=0, sticky='ew')
        caption('Steps · select to edit', 4)
        frame = ttk.Frame(parent, style='Panel.TFrame')
        frame.columnconfigure(0, weight=1)
        frame.grid(row=5, column=0, sticky='ew')
        self.step_list = tk.Listbox(frame, height=6, exportselection=False, bg=theme.FIELD, fg=theme.TEXT,
                                    selectbackground='#29556a', relief='flat', font=(self.app.family, 9))
        self.step_list.grid(row=0, column=0, sticky='ew')
        scrollbar = ttk.Scrollbar(frame, command=self.step_list.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.step_list.configure(yscrollcommand=scrollbar.set)
        self.step_list.bind('<<ListboxSelect>>', self._step_selected)
        buttons = ttk.Frame(parent, style='Panel.TFrame')
        buttons.grid(row=6, column=0, sticky='ew', pady=4)
        ttk.Button(buttons, text='+ Add concept', style='Compact.TButton', command=lambda: self.pick(self.add_step)).pack(side='left')
        ttk.Button(buttons, text='Remove step', style='Compact.TButton', command=self.remove_step).pack(side='right')
        buttons = ttk.Frame(parent, style='Panel.TFrame')
        buttons.grid(row=7, column=0, sticky='ew')
        for label, callback in (('Up', lambda: self.move_step(-1)), ('Down', lambda: self.move_step(1)), ('Start here', self.start_here)):
            ttk.Button(buttons, text=label, style='Compact.TButton', command=callback).pack(side='left', padx=(0, 4))
        caption('Referenced concept', 8)
        frame = ttk.Frame(parent, style='Panel.TFrame')
        frame.grid(row=9, column=0, sticky='ew')
        frame.columnconfigure(0, weight=1)
        self.concept_caption = ttk.Label(frame, style='Muted.TLabel', wraplength=225)
        self.concept_caption.grid(row=0, column=0, sticky='w')
        ttk.Button(frame, text='Relink', style='Compact.TButton', command=lambda: self.pick(self.relink)).grid(row=0, column=1)
        caption('Step title', 10)
        self.step_entry = ttk.Entry(parent, textvariable=self.step_title)
        self.step_entry.grid(row=11, column=0, sticky='ew')
        caption('In this process', 12)
        frame, self.explanation = text_field(parent, self.app, height=5)
        frame.grid(row=13, column=0, sticky='ew')
        ttk.Button(parent, text='Insert concept link', style='Inline.TButton', command=lambda: self.pick(self.insert_link)).grid(row=14, column=0, sticky='w', pady=3)
        caption('Recall prompt (optional)', 15)
        frame, self.question = text_field(parent, self.app, height=2)
        frame.grid(row=16, column=0, sticky='ew')
        caption('Outgoing connections', 17)
        self.connection_list = tk.Listbox(parent, height=3, exportselection=False, bg=theme.FIELD, fg=theme.TEXT,
                                          selectbackground='#29556a', relief='flat', font=(self.app.family, 9))
        self.connection_list.grid(row=18, column=0, sticky='ew')
        self.connection_list.bind('<<ListboxSelect>>', self._edge_selected)
        caption('Label / condition', 19)
        ttk.Entry(parent, textvariable=self.edge_label).grid(row=20, column=0, sticky='ew')
        caption('Destination', 21)
        self.target_box = ttk.Combobox(parent, textvariable=self.edge_target, state='readonly', width=26)
        self.target_box.grid(row=22, column=0, sticky='ew')
        buttons = ttk.Frame(parent, style='Panel.TFrame')
        buttons.grid(row=23, column=0, sticky='ew', pady=(5, 10))
        ttk.Button(buttons, text='Add / update', style='Compact.TButton', command=self.connect).pack(side='left')
        ttk.Button(buttons, text='New', style='Compact.TButton', command=self.new_connection).pack(side='left', padx=4)
        ttk.Button(buttons, text='Remove', style='Compact.TButton', command=self.remove_connection).pack(side='right')
        ttk.Label(parent, text='Headings: ## Title · emphasis: **text**\nConnections determine the path. Reordering changes numbering.',
                  style='Muted.TLabel', wraplength=295).grid(row=24, column=0, sticky='w')

    def _build_study(self, parent):
        self.progress = tk.Canvas(parent, height=36, width=290, bg=theme.PANEL, highlightthickness=0)
        self.progress.grid(row=0, column=0, sticky='ew')
        self.progress.bind('<Configure>', lambda _: self._draw_progress())
        self.progress.bind('<Button-1>', self._progress_selected)
        self.step_heading = ttk.Label(parent, style='Panel.TLabel', font=(self.app.family, 15, 'bold'), wraplength=300)
        self.step_heading.grid(row=1, column=0, sticky='w', pady=(5, 7))
        self.read_concept = ttk.Label(parent, style='Muted.TLabel', wraplength=300)
        self.read_concept.grid(row=2, column=0, sticky='w', pady=(0, 7))
        self.reader = StudyText(parent, self.app, self.highlight_concept)
        self.reader.grid(row=3, column=0, sticky='ew')
        scrollbar = ttk.Scrollbar(parent, command=self.reader.yview)
        scrollbar.grid(row=3, column=1, sticky='ns')
        self.reader.configure(yscrollcommand=scrollbar.set)
        self.choices_frame = ttk.Frame(parent, style='Panel.TFrame')
        self.choices_frame.grid(row=4, column=0, sticky='ew', pady=(8, 0))
        self.link_return = ttk.Button(parent, text='Return to current step', style='Compact.TButton', command=self.return_to_step)

    def _status(self, text):
        self.status.configure(text=text)

    def _candidate(self):
        if self.draft is None:
            return None
        steps = self.draft.steps
        if self.run and self.draft.step(self.run.current) is not None:
            old = self.draft.step(self.run.current)
            updated = replace(old, title=self.step_title.get().strip(), explanation=self.explanation.get('1.0', 'end-1c'),
                              question=self.question.get('1.0', 'end-1c'))
            steps = tuple(updated if s.id == old.id else s for s in steps)
        return replace(self.draft, title=self.title.get().strip(), introduction=self.introduction.get('1.0', 'end-1c'), steps=steps)

    def capture(self, *, apply_connection=True):
        try:
            self.draft = self._candidate()
            self.run.flow = self.draft
            if apply_connection and self._pending_connection():
                return self.connect()
            return True
        except AtlasError as error:
            self._status(str(error))
            return False

    @property
    def dirty(self):
        if not self.active:
            return False
        try:
            return self._candidate() != (self.app.document.flow(self.draft.id) or self._baseline) or self._pending_connection()
        except AtlasError:
            return True

    def _allow_flow_change(self):
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel('Unsaved flow', 'Save this flow before continuing?', parent=self.app.root)
        return self.save() if answer is True else answer is False

    def open(self):
        if self.active:
            return self.close()
        app, scene = self.app, self.app.scene
        if app._template_origin is not None:
            return False
        if app._node_move_origin is not None or app.placement_state == 'placing' or app.clusters.moving:
            app._set_status('Finish or cancel the current move before opening Flows.')
            return False
        if not app.information.close():
            return False
        self.snapshot = dict(mode=scene.mode, yaw=scene.yaw, elevation=scene.elevation, scale=scene.scale,
                             target=tuple(scene.target), layer=scene.layer_filter, protocol=scene.protocol_filter,
                             layer_display=app.filter_var.get(), protocol_display=app.protocol_filter_var.get(),
                             selected=scene.selected, child=scene.selected_child, expanded=scene.expanded_parent,
                             focused=scene.focused_parent, orbit_camera=scene._orbit_camera,
                             preview=scene.preview_node, valid=scene.preview_valid)
        self.inspector_id = app.clusters.child_id if app.clusters.editing else app.selected
        self.edited_concepts.clear()
        self.active = True
        app.compass.cancel_animation()
        scene.focused_parent = scene.expanded_parent = scene.selected_child = scene._orbit_camera = None
        scene.set_preview(None)
        scene.set_mode('nodes')
        scene.set_layer_filter(scene.layer_filter)
        app.view_mode_var.set('Nodes')
        app.connections_check.state(['!disabled'])
        for widget in (app.design_button, app.empty_button, app.templates_button, app.blocks_button, app.nodes_button):
            widget.state(['disabled'])
        app.editor_form.pack_forget()
        app.clusters.form.pack_forget()
        self.panel.pack(fill='both', expand=True)
        self.load(app.document.flows[0] if app.document.flows else FlowNote.create(), mode='study' if app.document.flows else 'edit')
        app.request_render()
        return True

    def _refresh_library(self):
        flows = list(self.app.document.flows)
        if self.draft and not any(f.id == self.draft.id for f in flows):
            flows.append(self.draft)
        self._library_ids = {f'{i+1} · {f.title}': f.id for i, f in enumerate(flows)}
        self.library_box.configure(values=tuple(self._library_ids))
        self.library.set(next((label for label, identity in self._library_ids.items() if identity == self.draft.id), ''))

    def load(self, flow, *, mode=None):
        self.draft = self._baseline = flow
        self.run = FlowRun(flow)
        self.linked_concept = None
        self.title.set(flow.title)
        set_text(self.introduction, flow.introduction)
        self._refresh_library()
        self._load_step()
        self.mode.set(mode or self.mode.get())
        self._show_mode()
        self._status('Changes stay in the draft until Save flow.' if self.mode.get() == 'edit' else 'Select a step or follow the connections. Focus step adjusts the camera.')
        self.update_scene()

    def choose_flow(self, _event=None):
        identity = self._library_ids.get(self.library.get())
        if identity == self.draft.id:
            return
        if not self._allow_flow_change():
            self._refresh_library()
            return
        flow = self.app.document.flow(identity)
        if flow:
            self.load(flow, mode='study')

    def new_flow(self):
        if self.active and self._allow_flow_change():
            self.load(FlowNote.create(), mode='edit')

    def delete_flow(self):
        flow = self.app.document.flow(self.draft.id)
        if not messagebox.askyesno('Delete flow', f"Delete '{self.draft.title}' and discard its draft changes?\n\nAtlas concepts and their notes will be kept.", parent=self.app.root):
            return False
        if flow:
            self._committing = True
            try:
                if not self.app._commit(self.app.document.without_flow(flow.id)):
                    return False
            finally:
                self._committing = False
        self.load(self.app.document.flows[0] if self.app.document.flows else FlowNote.create(), mode='edit')
        return True

    def save(self):
        if not self.active or not self.capture():
            return False
        self._committing = True
        try:
            if not self.app._commit(self.app.document.with_flow(self.draft)):
                return False
        except AtlasError as error:
            self._status(str(error))
            return False
        finally:
            self._committing = False
        self._baseline = self.draft
        self._refresh_library()
        self._refresh_steps()
        self._status('Flow saved. Concept notes and positions are shared with the atlas.')
        self.update_scene()
        return True

    def set_mode(self, mode):
        if not self.capture():
            self.mode.set('edit')
            return False
        self.mode.set(mode)
        self._show_mode()
        self.update_scene()
        return True

    def _show_mode(self):
        edit = self.mode.get() == 'edit'
        self.heading.configure(text='EDIT FLOW' if edit else 'STUDY FLOW')
        for widget in (self.edit_scroll, self.study_scroll, self.edit_footer, self.study_footer):
            widget.grid_remove()
        (self.edit_scroll if edit else self.study_scroll).grid(row=2, column=0, sticky='nsew')
        (self.edit_footer if edit else self.study_footer).grid(row=4, column=0, sticky='ew')
        if not edit:
            self.refresh_study()

    def pick(self, callback):
        if self.picker is not None and self.picker.winfo_exists():
            self.picker.lift()
        else:
            self.picker = ConceptPicker(self, callback)

    def add_step(self, concept):
        if not self.capture():
            return False
        if self.app.document.concept(concept.id) is None:
            return False
        step = FlowStep.create(concept.id, concept.name, concept.name)
        edges = self.draft.connections
        if self.draft.steps and not self.draft.outgoing(self.draft.steps[-1].id):
            edges += (FlowConnection.create(self.draft.steps[-1].id, step.id, 'Next'),)
        try:
            self.draft = replace(self.draft, steps=self.draft.steps+(step,), connections=edges)
        except AtlasError as error:
            self._status(str(error))
            return False
        self.run = FlowRun(self.draft, step.id)
        self._load_step()
        self.update_scene()
        self._status('Step added to the draft. Reusing a concept keeps one shared note.')
        return True

    def relink(self, concept):
        if not self.capture() or self.run.current is None or self.app.document.concept(concept.id) is None:
            return False
        self.draft = replace(self.draft, steps=tuple(replace(s, concept_id=concept.id, concept_name=concept.name)
                             if s.id == self.run.current else s for s in self.draft.steps))
        self.run.flow = self.draft
        self._load_step()
        self.update_scene()
        return True

    def insert_link(self, concept):
        self.explanation.insert('insert', concept_link(concept.id, concept.name))

    def remove_step(self):
        if not self.capture() or self.run.current is None:
            return False
        current = self.run.current
        index = next(i for i, s in enumerate(self.draft.steps) if s.id == current)
        steps = tuple(s for s in self.draft.steps if s.id != current)
        self.draft = replace(self.draft, steps=steps,
                             connections=tuple(e for e in self.draft.connections if current not in (e.source_id, e.target_id)),
                             start_step_id=steps[0].id if steps and self.draft.start_step_id == current else None if not steps else self.draft.start_step_id)
        self.run = FlowRun(self.draft, steps[min(index, len(steps)-1)].id if steps else None)
        self._load_step()
        self.update_scene()
        return True

    def move_step(self, direction):
        if not self.capture() or self.run.current is None:
            return
        steps = list(self.draft.steps)
        index = next(i for i, s in enumerate(steps) if s.id == self.run.current)
        destination = max(0, min(len(steps)-1, index+direction))
        steps[index], steps[destination] = steps[destination], steps[index]
        self.draft = replace(self.draft, steps=tuple(steps))
        self.run.flow = self.draft
        self._load_step()
        self.update_scene()

    def start_here(self):
        if self.capture() and self.run.current:
            self.draft = replace(self.draft, start_step_id=self.run.current)
            self.run.flow = self.draft
            self._refresh_steps()

    def _refresh_steps(self):
        self.step_list.delete(0, 'end')
        self._step_ids = []
        for i, step in enumerate(self.draft.steps):
            name = self.app.document.concept(step.concept_id)
            self.step_list.insert('end', f'{i+1}. {step.title}' + (' [missing]' if name is None else '') + (' · start' if step.id == self.draft.start_step_id else ''))
            self._step_ids.append(step.id)
            if step.id == self.run.current:
                self.step_list.selection_set(i)
                self.step_list.see(i)

    def _load_step(self):
        self._loading = True
        step = self.draft.step(self.run.current)
        concept = self.app.document.concept(step.concept_id) if step else None
        self.step_title.set(step.title if step else '')
        set_text(self.explanation, step.explanation if step else '')
        set_text(self.question, step.question if step else '')
        self.concept_caption.configure(text=concept.name if concept else f'Missing: {step.concept_name or step.concept_id}' if step else 'Add an existing concept to begin.')
        self.step_entry.configure(state='normal' if step else 'disabled')
        self.edge_id = None
        self.edge_label.set('')
        self._refresh_steps()
        self._refresh_edges()
        self._edge_loaded = self._edge_state()
        choices = self.run.choices
        self.choice.set(choices[0].id if len(choices) == 1 else '')
        self._loading = False

    def _step_selected(self, _event=None):
        if self._loading:
            return
        selection = self.step_list.curselection()
        if selection and selection[0] < len(self._step_ids):
            self.select_step(self._step_ids[selection[0]])

    def select_step(self, identity):
        if not self.capture():
            return False
        if self.draft.step(identity) is None:
            return False
        self.run.jump(identity)
        self.linked_concept = None
        self._load_step()
        self.refresh_study()
        self.update_scene()
        return True

    def _refresh_edges(self):
        self._target_ids = {'End flow': None}
        self._target_ids.update({f'{i+1}. {s.title}': s.id for i, s in enumerate(self.draft.steps)})
        self.target_box.configure(values=tuple(self._target_ids))
        self.edge_target.set('End flow')
        self.connection_list.delete(0, 'end')
        self._edge_ids = []
        for edge in self.draft.outgoing(self.run.current):
            destination = next((label for label, identity in self._target_ids.items() if identity == edge.target_id), 'End flow')
            self.connection_list.insert('end', f'{edge.label or "Continue"} → {destination}')
            self._edge_ids.append(edge.id)

    def _edge_selected(self, _event=None):
        selected = self.connection_list.curselection()
        if not selected or selected[0] >= len(self._edge_ids):
            return
        requested = self._edge_ids[selected[0]]
        if self._pending_connection() and not self.capture():
            return
        self.edge_id = requested
        edge = next(e for e in self.draft.connections if e.id == self.edge_id)
        self.edge_label.set(edge.label)
        self.edge_target.set(next(label for label, identity in self._target_ids.items() if identity == edge.target_id))
        self._edge_loaded = self._edge_state()
        self.update_scene()

    def _edge_state(self):
        return self.edge_id, self.edge_label.get(), self.edge_target.get()

    def _pending_connection(self):
        return hasattr(self, '_edge_loaded') and self._edge_state() != self._edge_loaded

    def new_connection(self):
        if self._pending_connection() and not self.capture():
            return
        self.edge_id = None
        self.connection_list.selection_clear(0, 'end')
        self.edge_label.set('')
        self.edge_target.set('End flow')
        self._edge_loaded = self._edge_state()

    def connect(self):
        if not self.capture(apply_connection=False) or self.run.current is None:
            return False
        if self.edge_target.get() not in self._target_ids:
            self._status('Choose an existing destination step or End flow.')
            return False
        try:
            edge = FlowConnection(self.edge_id, self.run.current, self._target_ids[self.edge_target.get()], self.edge_label.get().strip()) if self.edge_id else FlowConnection.create(self.run.current, self._target_ids[self.edge_target.get()], self.edge_label.get())
            connections = tuple(edge if old.id == edge.id else old for old in self.draft.connections) if self.edge_id else self.draft.connections+(edge,)
            self.draft = replace(self.draft, connections=connections)
        except AtlasError as error:
            self._status(str(error))
            return False
        self.run.flow = self.draft
        self._load_step()
        self.update_scene()
        self._status('Connection updated in the draft. Save flow to keep it.')
        return True

    def remove_connection(self):
        identity = self.edge_id
        if self.capture(apply_connection=False) and identity is not None:
            self.draft = replace(self.draft, connections=tuple(e for e in self.draft.connections if e.id != identity))
            self.run.flow = self.draft
            self._load_step()
            self.update_scene()

    def next(self):
        if not self.capture():
            return False
        try:
            self.run.next(self.choice.get() or None)
        except AtlasError as error:
            self._status(str(error))
            return False
        self.linked_concept = None
        self._load_step()
        self.refresh_study()
        self.update_scene()
        return True

    def previous(self):
        if self.capture():
            self.run.previous()
            self.linked_concept = None
            self._load_step()
            self.refresh_study()
            self.update_scene()

    def _draw_progress(self):
        self.progress.delete('all')
        self._progress_hits = []
        if not self.run or not self.draft.steps:
            return
        index = next((i for i, s in enumerate(self.draft.steps) if s.id == self.run.current), 0)
        start = max(0, min(index-3, len(self.draft.steps)-7))
        shown = self.draft.steps[start:start+7]
        width = max(220, self.progress.winfo_width())
        for i, step in enumerate(shown):
            x = (i+.5)*width/len(shown)
            selected = step.id == self.run.current
            self.progress.create_oval(x-12, 6, x+12, 30, fill=theme.FIELD,
                                     outline=theme.ACCENT if selected else theme.BORDER, width=2 if selected else 1)
            self.progress.create_text(x, 18, text=str(start+i+1), fill=theme.ACCENT if selected else theme.TEXT,
                                      font=(self.app.family, 9))
            self._progress_hits.append((x, step.id))

    def _progress_selected(self, event):
        hit = next((identity for x, identity in self._progress_hits if abs(event.x-x) <= 15), None)
        if hit:
            self.select_step(hit)

    def refresh_study(self):
        if not self.active or self.mode.get() != 'study':
            return
        step = self.draft.step(self.run.current)
        concept = self.app.document.concept(self.linked_concept or step.concept_id) if step else None
        self._draw_progress()
        self.step_heading.configure(text='Flow complete' if self.run.finished else step.title if step else 'Add a step to begin')
        if step:
            number = next(i for i, item in enumerate(self.draft.steps, 1) if item.id == step.id)
            name = concept.name if concept else f'Missing concept: {step.concept_name or step.concept_id}'
            if concept is not None and not self.app.scene.concept_visible(concept.id):
                name += ' · hidden by filters'
            self.read_concept.configure(text=f'Step {number} of {len(self.draft.steps)} · {name}')
        else:
            self.read_concept.configure(text='Use Edit to add existing concepts.')
        sections = [('Introduction', self.draft.introduction)] if step is None or step.id == self.draft.start_step_id else []
        if step:
            sections += [('From concept note', concept.notes if concept else 'This reference is missing. Use Edit → Relink to repair it.'),
                         ('In this process', step.explanation), ('Recall prompt', step.question)]
            if concept:
                sections += [('Additional information · '+entry.title, entry.body)
                             for entry in self.app.document.entries_for(concept.id)]
        self.reader.show(sections)
        for child in self.choices_frame.winfo_children():
            child.destroy()
        if len(self.run.choices) > 1:
            ttk.Label(self.choices_frame, text='Choose a path', style='Muted.TLabel').pack(anchor='w', pady=(0, 4))
        for edge in self.run.choices:
            target = self.draft.step(edge.target_id)
            label = (edge.label or 'Continue') + ' → ' + (target.title if target else 'End flow')
            if len(self.run.choices) == 1:
                ttk.Label(self.choices_frame, text=label, style='Muted.TLabel', wraplength=290).pack(anchor='w')
                continue
            tk.Radiobutton(self.choices_frame, text=label, value=edge.id, variable=self.choice,
                           command=self.choose_branch, bg=theme.FIELD, fg=theme.TEXT,
                           activebackground=theme.FIELD, activeforeground=theme.ACCENT,
                           selectcolor=theme.PANEL, anchor='w', justify='left', wraplength=270,
                           padx=7, pady=7, font=(self.app.family, 9), highlightthickness=1,
                           highlightbackground=theme.BORDER).pack(fill='x', pady=3)
        self.previous_button.state(['!disabled'] if self.run.trail else ['disabled'])
        next_ready = step is not None and not self.run.finished and (len(self.run.choices) <= 1 or bool(self.choice.get()))
        self.next_button.state(['!disabled'] if next_ready else ['disabled'])
        self.next_button.configure(text='Finished' if self.run.finished else 'Finish' if not self.run.choices else 'Next')
        for button in (self.focus_button, self.edit_concept_button):
            button.state(['!disabled'] if concept is not None else ['disabled'])
        self.link_return.grid(row=5, column=0, sticky='w', pady=6) if self.linked_concept else self.link_return.grid_remove()
        self._fit_study()

    def _fit_study(self):
        if not self.active or self.mode.get() != 'study' or self.run is None:
            return
        viewport = self.study_scroll.canvas.winfo_height()
        if viewport < 100:
            return
        header = max(100, self.reader.winfo_y())
        choices = 26 if len(self.run.choices) <= 1 else 30 + 48*len(self.run.choices)
        pitch = self.reader.line_height + int(self.reader.cget('spacing3'))
        self.reader.max_lines = max(3, min(32, (viewport-header-choices-30)//max(1, pitch)))
        self.reader.fit_content()

    def choose_branch(self):
        valid = not self.run.finished and any(edge.id == self.choice.get() for edge in self.run.choices)
        self.next_button.state(['!disabled'] if valid else ['disabled'])
        if valid:
            edge = next(edge for edge in self.run.choices if edge.id == self.choice.get())
            self._status('Chosen path: ' + (edge.label or 'Continue'))
        for widget in self.choices_frame.winfo_children():
            if isinstance(widget, tk.Radiobutton):
                selected = str(widget.cget('value')) == self.choice.get()
                widget.configure(bg='#163c49' if selected else theme.FIELD,
                                 highlightbackground=theme.ACCENT if selected else theme.BORDER)
        self.update_scene()

    def highlight_concept(self, identity):
        if self.app.document.concept(identity) is None:
            self._status('That linked concept is missing. Repair its link in Edit.')
            return
        step = next((s for s in self.draft.steps if s.concept_id == identity), None)
        if step:
            self.select_step(step.id)
        else:
            self.linked_concept = identity
            self.refresh_study()
            self.update_scene()

    def return_to_step(self):
        self.linked_concept = None
        self.refresh_study()
        self.update_scene()

    def edit_concept(self):
        step = self.draft.step(self.run.current)
        identity = self.linked_concept or (step.concept_id if step else None)
        concept = self.app.document.concept(identity)
        if concept is None:
            return False
        if identity == self.inspector_id and (self.app.dirty or self.app.clusters.dirty):
            self._status('Return to the atlas and finish its unsaved note edits before editing this shared concept.')
            return False
        if self.concept_editor is not None and self.concept_editor.winfo_exists():
            self.concept_editor.lift()
        else:
            self.concept_editor = FlowConceptEditor(self, concept)
        return True

    def update_scene(self):
        self.app.scene.set_flow(self.draft, current=self.run.current, chosen=self.edge_id if self.mode.get() == 'edit' and self.edge_id else self.choice.get() or None,
                                arrival=self.run.arrival, linked=self.linked_concept)
        self.app.request_render()

    def document_changed(self):
        if self.active and not self._committing:
            self.refresh_study()
            self.update_scene()

    def show_flow_layers(self):
        self.app.filter_var.set('All layers')
        self.app.protocol_filter_var.set(self.app._all_protocols)
        self.app._filter_changed()
        self._status('Flow concepts are visible across layers. Previous filters return when you leave the flow.')

    def focus_step(self):
        scene = self.app.scene
        identity = scene.flow_concept_id
        point = scene.concept_point(identity)
        if point is None:
            return False
        if not scene.concept_visible(identity):
            self._status('This concept is filtered out. Choose Show flow layers to reveal it.')
            return False
        self.app.compass.cancel_animation()
        scene.target = list(point)
        scene.scale = min(scene.scale, 1.4)
        scene._apply_camera()
        self.app.request_render()
        return True

    def show_entire_flow(self):
        scene = self.app.scene
        points = [p for identity in scene.flow_concepts if (p := scene.concept_point(identity)) is not None]
        if not points:
            self._status('Add an existing concept or repair a missing reference first.')
            return
        self.app.compass.cancel_animation()
        center = tuple((min(p[i] for p in points)+max(p[i] for p in points))/2 for i in range(3))
        right, up, _ = camera_basis(scene.yaw, scene.elevation)
        extents = [max(abs(sum((p[i]-center[i])*basis[i] for i in range(3))) for p in points)+.25 for basis in (right, up)]
        scene.target = list(center)
        scene.scale = max(.8, extents[1]*1.3, extents[0]*scene.height/max(1, scene.width-160)*1.3)
        scene._apply_camera()
        self.app.request_render()

    def select_concept(self, identity):
        current = self.draft.step(self.run.current)
        if current and current.concept_id == identity:
            return True
        step = next((s for s in self.draft.steps if s.concept_id == identity), None)
        if step:
            return self.select_step(step.id)
        self._status('This concept is outside the flow. Use Edit → Add concept to include it.')
        return False

    def sync(self):
        if self.active:
            self.app.clusters.bar.grid_remove()
            self.bar.grid(row=2, column=0, sticky='ew')
            title = self.draft.title
            unsaved = self.dirty
            self.summary.configure(text='Flow: '+(title if len(title) <= 28 else title[:25]+'…') + (' · draft' if unsaved else ''))
            self.heading.configure(text=('EDIT FLOW' if self.mode.get() == 'edit' else 'STUDY FLOW') + (' · DRAFT' if unsaved else ''))

    def prepare_badges(self):
        self.badge_boxes, self.badge_hits = [], []
        if not self.active:
            return
        scene, canvas = self.app.scene, self.app.canvas
        groups = {}
        for i, step in enumerate(self.draft.steps, 1):
            groups.setdefault(step.concept_id, []).append(i)
        if self.linked_concept:
            groups.setdefault(self.linked_concept, [])
        for identity, numbers in groups.items():
            point = scene.concept_point(identity)
            if point is None or not scene.concept_visible(identity):
                continue
            x, y, depth = scene.project(point)
            if not 0 <= depth <= 1:
                continue
            color = theme.ACCENT if identity == scene.flow_concept_id else theme.MUTED
            if identity == scene.flow_concept_id and 0 < x < scene.width and 0 < y < scene.height:
                radius = max(9, .065*scene.height/(2*scene.scale)+5)
                canvas.create_oval(x-radius, y-radius, x+radius, y+radius, outline=theme.ACCENT, width=2, tags=('overlay', 'flow-current-ring'))
            text = ('Link' if not numbers else ','.join(map(str, numbers))) if len(numbers) <= 3 else f'{numbers[0]},+{len(numbers)-1}'
            width = max(20, self.app.label_font.measure(text)+10)
            box = (x-width/2, y-29, x+width/2, y-10)
            if not inside(box, (8, 65, scene.width-8, scene.height-112)) or overlaps(box, self.app.navigation.reserved_box):
                continue
            canvas.create_rectangle(*box, fill=theme.FIELD, outline=color, tags='overlay')
            canvas.create_text(x, y-19, text=text, fill=color, font=(self.app.family, 8), tags='overlay')
            self.badge_boxes.append(box)
            self.badge_hits.append((identity, box))

    def draw(self):
        if not self.active:
            return
        scene, canvas = self.app.scene, self.app.canvas
        obstacles = [self.app.navigation.reserved_box, *self.badge_boxes, *self.app.label_manager.placements.values()]
        for edge in self.draft.connections:
            if edge.id not in (scene.flow_edge_id, self.run.arrival) or edge.id not in scene.flow_paths:
                continue
            text = edge.label + (' · End flow' if edge.target_id is None else '')
            if not text:
                continue
            text = text if len(text) <= 32 else text[:29]+'…'
            width = self.app.label_font.measure(text)+12
            path = scene.flow_paths[edge.id]
            for index in (16, 12, 20, 8, 24):
                x, y, depth = scene.project(path[index])
                box = x-width/2, y-12, x+width/2, y+10
                if 0 <= depth <= 1 and inside(box, (8, 65, scene.width-8, scene.height-112)) and not any(overlaps(box, other) for other in obstacles):
                    canvas.create_rectangle(*box, fill=theme.PANEL, outline=theme.BORDER, tags='overlay')
                    canvas.create_text(x, y-1, text=text, fill=theme.ACCENT, font=(self.app.family, 9), tags='overlay')
                    obstacles.append(box)
                    break

    def close(self):
        if not self.active:
            return True
        if self.concept_editor is not None and self.concept_editor.winfo_exists() and not self.concept_editor.ask_close():
            return False
        if not self._allow_flow_change():
            return False
        self.shutdown()
        app, scene, saved = self.app, self.app.scene, self.snapshot
        self.active = False
        scene.set_flow()
        scene.focused_parent = scene._orbit_camera = None
        scene.set_mode(saved['mode'])
        app.view_mode_var.set(saved['mode'].title())
        app.connections_check.state(['!disabled'] if saved['mode'] == 'nodes' else ['disabled'])
        app.filter_var.set(saved['layer_display'])
        app.protocol_filter_var.set(saved['protocol_display'])
        scene.set_protocol_filter(saved['protocol'])
        scene.set_layer_filter(saved['layer'])
        scene.expanded_parent, scene.focused_parent, scene._orbit_camera = saved['expanded'], saved['focused'], saved['orbit_camera']
        scene.selected_child = saved['child']
        scene.set_selected(saved['selected'])
        scene.set_preview(saved['preview'], saved['valid'])
        scene.yaw, scene.elevation, scene.scale, scene.target = saved['yaw'], saved['elevation'], saved['scale'], list(saved['target'])
        scene._apply_camera()
        for widget in (app.design_button, app.empty_button, app.templates_button, app.blocks_button, app.nodes_button):
            widget.state(['!disabled'])
        if self.inspector_id in self.edited_concepts:
            concept = app.document.concept(self.inspector_id)
            if hasattr(concept, 'parent_id'):
                app.clusters._open(app.document.get(concept.parent_id), concept)
            else:
                app._load_editor(concept)
        (app.clusters.form if app.clusters.editing else app.editor_form).pack(fill='both', expand=True)
        app._set_status('Returned to atlas · previous camera and filters restored.')
        app.request_render()
        return True

    def shutdown(self):
        for window in (self.picker, self.concept_editor):
            if window is not None and window.winfo_exists():
                window.destroy()
        self.picker = self.concept_editor = None
        self.panel.pack_forget()
        self.bar.grid_remove()
