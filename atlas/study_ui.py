"""Reusable scrollable study content, concept lookup and canonical-note editing."""
from dataclasses import replace
import tkinter as tk
from tkinter import font, messagebox, ttk

from . import theme
from .model import AtlasError
from .study_text import study_spans


class ScrollPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, style='Panel.TFrame')
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg=theme.PANEL, highlightthickness=0, width=310, height=200)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(self, command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.body = ttk.Frame(self.canvas, style='Panel.TFrame')
        self.body.columnconfigure(0, weight=1)
        self.item = self.canvas.create_window(0, 0, anchor='nw', window=self.body)
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.item, width=e.width))
        self.body.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<MouseWheel>', lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units'))
        self.canvas.bind('<Button-4>', lambda _: self.canvas.yview_scroll(-1, 'units'))
        self.canvas.bind('<Button-5>', lambda _: self.canvas.yview_scroll(1, 'units'))


def text_field(parent, app, *, height=4):
    frame = ttk.Frame(parent, style='Panel.TFrame')
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    text = tk.Text(frame, height=height, width=28, wrap='word', undo=True, bg=theme.FIELD,
                   fg=theme.TEXT, insertbackground=theme.TEXT, relief='flat', padx=8, pady=7,
                   font=(app.family, 10), highlightthickness=1, highlightbackground=theme.BORDER)
    text.grid(row=0, column=0, sticky='nsew')
    ttk.Scrollbar(frame, command=text.yview).grid(row=0, column=1, sticky='ns')
    text.configure(yscrollcommand=frame.winfo_children()[-1].set)
    return frame, text


def set_text(widget, value):
    widget.delete('1.0', 'end')
    widget.insert('1.0', value)
    widget.edit_modified(False)


class StudyText(tk.Text):
    def __init__(self, parent, app, on_concept):
        super().__init__(parent, wrap='word', width=29, height=10, bg=theme.FIELD, fg=theme.TEXT,
                         relief='flat', padx=11, pady=10, font=(app.family, 10), spacing3=6,
                         highlightthickness=1, highlightbackground=theme.BORDER, cursor='arrow')
        self.on_concept = on_concept
        for name, size in (('h1', 15), ('h2', 12), ('h3', 11)):
            self.tag_configure(name, font=(app.family, size, 'bold'), spacing1=10, spacing3=5)
        self.tag_configure('bold', font=(app.family, 10, 'bold'))
        self.tag_configure('italic', font=(app.family, 10, 'italic'))
        self.tag_configure('code', font=(app.mono, 9), background=theme.PANEL)
        self.tag_configure('link', foreground=theme.ACCENT, underline=True)
        self._links = []
        self.max_lines = 32
        self.line_height = font.Font(self, font=self.cget('font')).metrics('linespace')
        self.bind('<Configure>', lambda _: self.fit_content())

    def fit_content(self):
        count = self.count('1.0', 'end-1c', 'displaylines')
        lines = count[0] if count else 0
        headings = sum(len(self.tag_ranges(tag))//2 for tag in ('h1', 'h2', 'h3'))
        height = max(3, min(self.max_lines, lines+headings+2))
        if int(self.cget('height')) != height:
            self.configure(height=height)

    def show(self, sections):
        self.configure(state='normal')
        self.delete('1.0', 'end')
        for tag in self._links:
            self.tag_delete(tag)
        self._links.clear()
        for heading, content in sections:
            if not content:
                continue
            if heading:
                self.insert('end', heading + '\n', ('h2',))
            for span in study_spans(content + '\n\n'):
                tags = span.tags
                if span.concept_id:
                    tag = f'concept-link-{len(self._links)}'
                    self._links.append(tag)
                    self.tag_bind(tag, '<Button-1>', lambda _, identity=span.concept_id: self.on_concept(identity))
                    self.tag_bind(tag, '<Enter>', lambda _: self.configure(cursor='hand2'))
                    self.tag_bind(tag, '<Leave>', lambda _: self.configure(cursor='arrow'))
                    tags += (tag,)
                self.insert('end', span.text, tags)
        self.configure(state='disabled')
        self.fit_content()
        self.yview_moveto(0)


class ConceptPicker(tk.Toplevel):
    def __init__(self, manager, callback):
        super().__init__(manager.app.root)
        self.manager, self.callback = manager, callback
        self.title('Choose an existing concept')
        self.configure(bg=theme.PANEL)
        self.geometry('540x440')
        self.minsize(400, 280)
        self.transient(manager.app.root)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.query = tk.StringVar()
        ttk.Label(self, text='Search nodes and suborbitals', style='Muted.TLabel').grid(row=0, column=0, sticky='w', padx=12, pady=(12, 4))
        search = ttk.Entry(self, textvariable=self.query)
        search.grid(row=1, column=0, sticky='ew', padx=12)
        frame = ttk.Frame(self, style='Panel.TFrame')
        frame.grid(row=2, column=0, sticky='nsew', padx=12, pady=8)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.list = tk.Listbox(frame, bg=theme.FIELD, fg=theme.TEXT, selectbackground='#29556a',
                               exportselection=False, relief='flat', font=(manager.app.family, 10))
        self.list.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(frame, command=self.list.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.list.configure(yscrollcommand=scrollbar.set)
        self.hint = ttk.Label(self, style='Muted.TLabel')
        self.hint.grid(row=3, column=0, sticky='w', padx=12)
        ttk.Button(self, text='Use concept', style='Primary.TButton', command=self.accept).grid(row=4, column=0, sticky='e', padx=12, pady=12)
        self.query.trace_add('write', lambda *_: self.filter())
        self.list.bind('<Double-Button-1>', lambda _: self.accept())
        self.list.bind('<Return>', lambda _: self.accept())
        self.bind('<Escape>', lambda _: self.destroy())
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.filter()
        self.grab_set()
        search.focus_set()

    def filter(self):
        document = self.manager.app.document
        query = self.query.get().strip().casefold()
        self.matches = []
        self.list.delete(0, 'end')
        for concept in (*document.nodes, *document.subconcepts):
            parent = document.get(getattr(concept, 'parent_id', concept.id))
            location = document.design.layer(parent.layer).name
            if hasattr(concept, 'parent_id'):
                location += ' / ' + parent.name
            else:
                location += f' / {concept.depth:02d}:{concept.slot+1:02d}'
            label = f'{concept.name} — {location}'
            if query and query not in label.casefold():
                continue
            self.matches.append(concept)
            self.list.insert('end', label)
            if len(self.matches) == 200:
                break
        self.hint.configure(text=f'{len(self.matches)} matches' + (' · narrow the search for more' if len(self.matches) == 200 else ''))
        if self.matches:
            self.list.selection_set(0)

    def accept(self):
        selected = self.list.curselection()
        if selected and selected[0] < len(self.matches):
            concept = self.matches[selected[0]]
            self.destroy()
            self.callback(concept)


class FlowConceptEditor(tk.Toplevel):
    def __init__(self, manager, concept):
        super().__init__(manager.app.root)
        self.manager, self.identity = manager, concept.id
        self.title('Edit concept note')
        self.configure(bg=theme.PANEL)
        self.geometry('560x520')
        self.minsize(430, 350)
        self.transient(manager.app.root)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.name = tk.StringVar(value=concept.name)
        ttk.Label(self, text='Shared concept note', style='Muted.TLabel').grid(row=0, column=0, sticky='w', padx=12, pady=(12, 4))
        ttk.Entry(self, textvariable=self.name).grid(row=1, column=0, sticky='ew', padx=12)
        frame, self.notes = text_field(self, manager.app, height=12)
        frame.grid(row=2, column=0, sticky='nsew', padx=12, pady=10)
        set_text(self.notes, concept.notes)
        self.original = self.state_values()
        self.status = ttk.Label(self, style='Muted.TLabel', wraplength=450)
        self.status.grid(row=3, column=0, sticky='ew', padx=12)
        ttk.Button(self, text='Save concept note', style='Primary.TButton', command=self.save).grid(row=4, column=0, sticky='e', padx=12, pady=12)
        self.protocol('WM_DELETE_WINDOW', self.ask_close)
        self.bind('<Escape>', lambda _: self.ask_close())

    def state_values(self):
        return self.name.get(), self.notes.get('1.0', 'end-1c')

    def save(self):
        app = self.manager.app
        concept = app.document.concept(self.identity)
        if concept is None:
            self.status.configure(text='This concept no longer exists.')
            return False
        try:
            updated = replace(concept, name=self.name.get().strip(), notes=self.notes.get('1.0', 'end-1c'))
            document = app.document.with_child(updated) if hasattr(concept, 'parent_id') else app.document.with_node(updated)
        except AtlasError as error:
            self.status.configure(text=str(error))
            return False
        if not app._commit(document, error_parent=self):
            return False
        self.manager.edited_concepts.add(self.identity)
        self.destroy()
        self.manager.concept_editor = None
        self.manager.refresh_study()
        return True

    def ask_close(self):
        if self.state_values() != self.original:
            answer = messagebox.askyesnocancel('Unsaved concept note', 'Save this concept note before continuing?', parent=self)
            if answer is None:
                return False
            if answer:
                return self.save()
        self.destroy()
        self.manager.concept_editor = None
        return True
