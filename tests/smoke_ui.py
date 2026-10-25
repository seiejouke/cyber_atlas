"""Exercise the real GUI and renderer. Run from the project root.

A graphical desktop is required. On a headless Linux test machine:
    xvfb-run -a python tests/smoke_ui.py
"""
import argparse
from dataclasses import replace
import json
from math import pi
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from atlas.geometry import wedge_mesh
from atlas.model import Atlas, CENTER_DEPTH, Design, Layer, Node, Protocol, example_atlas
from atlas.design_editor import DesignEditor, ReassignDialog, ReassignListDialog
from atlas.storage import read_atlas, write_atlas
from atlas.ui import AtlasApp
from atlas.scene import NO_PROTOCOL_FILTER
from atlas.templates import find_template
from node_view_checks import check_node_moves, check_node_view
from template_view_checks import check_template_browser
from block_view_checks import check_block_view
from update_view_checks import check_updates
from cluster_view_checks import check_clusters
from connection_view_checks import check_connections
from information_view_checks import check_information


def pump(root, steps=5):
    for _ in range(steps):
        root.update()
        time.sleep(0.025)


def check_clear_lists(root, app, path, checks):
    original, original_bytes = app.document, path.read_bytes()
    dialog = DesignEditor(root, original, app.apply_design)
    try:
        for kind in ("layers", "protocols"):
            editor = getattr(dialog, kind)
            dialog.notebook.select(editor)
            pump(root)
            old_entries = editor.entries
            editor.name.set("Keep this uncommitted name")
            with patch("atlas.design_editor.messagebox.askyesno", return_value=False) as confirmation:
                editor.clear_button.invoke()
            assert "Are you sure" in confirmation.call_args.args[1]
            assert f"remove all {kind}" in confirmation.call_args.args[1]
            assert confirmation.call_args.kwargs["default"] == "no"
            assert editor.entries == old_entries and editor.name.get() == "Keep this uncommitted name"
            assert app.document == original and path.read_bytes() == original_bytes
            editor.name.set(old_entries[-1].name if kind == "layers" else old_entries[0].name)
        checks.append("both clear-list buttons ask for confirmation; No preserves list, pending text and saved atlas")

        for kind in ("layers",):
            editor = getattr(dialog, kind)
            dialog.notebook.select(editor)
            with patch("atlas.design_editor.messagebox.askyesno", return_value=True):
                editor.clear_button.invoke()
            pump(root)
            assert editor.entries == () and editor.listbox.size() == 0 and editor.current is None
            assert editor.empty_label.winfo_ismapped()
            assert editor.name_entry.instate(["disabled"]) and editor.remove_button.instate(["disabled"])
            assert editor.clear_button.instate(["disabled"]) and editor.update_button.instate(["disabled"])
            assert editor.reassign_button.instate(["disabled"])
            assert dialog.apply_button.instate(["disabled"]) and not dialog.apply()
            assert dialog.draft.nodes == original.nodes
            assert "Add at least one" in dialog.readiness.get()
            dialog.label_mode.set("Title + layer + protocol")
            assert "Add a layer" in dialog.label_preview.cget("text")
            assert path.read_bytes() == original_bytes
        checks.append("clearing layers shows an empty draft list, keeps every note, and disables Apply until assignments are complete")
    finally:
        dialog.cancel()
    assert app.document == original and path.read_bytes() == original_bytes
    checks.append("Cancel after clearing layers leaves the active atlas and saved file unchanged")

    candidates = []
    dialog = DesignEditor(root, Atlas().without_protocols(), lambda candidate: candidates.append(candidate) or True)
    try:
        with patch("atlas.design_editor.messagebox.askyesno", return_value=True):
            assert dialog.layers.clear_list()
        dialog.layers.add()
        dialog.layers.name.set("My layer")
        assert dialog.layers.update_entry()
        assert dialog.apply_button.instate(["!disabled"])
        assert not dialog.draft.pending("layers") and not dialog.draft.pending("protocols")
        assert dialog.apply()
    finally:
        if dialog.winfo_exists():
            dialog.cancel()
    assert len(candidates) == 1 and not candidates[0].nodes
    assert candidates[0].design.layers[0].name == "My layer"
    assert candidates[0].design.protocols == ()
    assert path.read_bytes() == original_bytes
    checks.append("an empty atlas can rebuild layers and apply with no protocols")

    fixture = read_atlas(Path(__file__).resolve().parents[1] / "examples" / "custom_design_atlas.json")
    assert app.apply_design(fixture)
    original_bytes = path.read_bytes()
    dialog = DesignEditor(root, app.document, app.apply_design)
    try:
        with patch("atlas.design_editor.messagebox.askyesno", return_value=True):
            assert dialog.layers.clear_list() and dialog.protocols.clear_list()
        cleared = fixture.without_protocols()
        assert app.document == read_atlas(path) == cleared
        original_bytes = path.read_bytes()
        destinations = {}
        for i, layer in enumerate(fixture.design.layers, 1):
            dialog.layers.add()
            dialog.layers.name.set(f"Replacement layer {i}")
            assert dialog.layers.update_entry()
            destinations[layer.id] = dialog.layers.name.get()
        dialog.protocols.add()
        dialog.protocols.name.set("Replacement protocol")
        assert dialog.protocols.update_entry()
        assert dialog.apply_button.instate(["disabled"])

        def run_assignments(editor, action):
            def operate():
                child = next(child for child in dialog.winfo_children() if isinstance(child, ReassignListDialog))
                try:
                    action(child)
                finally:
                    if child.winfo_exists():
                        child.cancel()
            dialog.after(60, operate)
            return editor.reassign_blocks()

        assert dialog.draft.pending("protocols") == ()
        assert dialog.apply_button.instate(["disabled"])
        before_assignment = dialog.draft.nodes
        assert not run_assignments(dialog.layers, lambda child: child.cancel())
        assert dialog.draft.nodes == before_assignment
        assert app.document == cleared and path.read_bytes() == original_bytes
        checks.append("cleared layers require explicit destinations; optional new protocols leave blocks unassigned")

        def assign_layers(child):
            for variable in child.variables.values():
                variable.set("Replacement layer 1")
            child.confirm.invoke()
            assert child.winfo_exists() and "overlaps" in child.error.get()
            assert dialog.draft.nodes == before_assignment
            for source, variable in child.variables.items():
                variable.set(destinations[source])
            child.confirm.invoke()

        assert run_assignments(dialog.layers, assign_layers)
        assert dialog.draft.ready and dialog.apply_button.instate(["!disabled"])
        for before, after in zip(fixture.nodes, dialog.draft.nodes):
            assert (before.id, before.name, before.notes, before.depth, before.slot, before.span) == (
                after.id, after.name, after.notes, after.depth, after.slot, after.span)
        assert app.document == cleared and path.read_bytes() == original_bytes
        checks.append("bulk layer reassignment rejects overlaps atomically, then accepts separate replacement layers without losing notes")

        dialog.geometry("650x630")
        dialog.notebook.select(dialog.layers)
        pump(root)
        assert dialog.layers.clear_button.winfo_rootx() >= dialog.layers.remove_button.winfo_rootx() + dialog.layers.remove_button.winfo_width()
        assert dialog.layers.higher.winfo_rootx() >= dialog.layers.clear_button.winfo_rootx() + dialog.layers.clear_button.winfo_width()
        assert dialog.layers.listbox.winfo_height() >= 60
        assert dialog.apply_button.winfo_rooty() + dialog.apply_button.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
        with patch("atlas.ui.write_atlas", side_effect=OSError("Simulated reset-design save failure")), \
             patch("atlas.ui.messagebox.showerror"):
            assert not dialog.apply()
        assert app.document == cleared and path.read_bytes() == original_bytes and dialog.draft.ready
        assert dialog.apply()
    finally:
        if dialog.winfo_exists():
            dialog.cancel()
    assert app.document == read_atlas(path)
    assert read_atlas(path.with_suffix(".json.bak")) == cleared
    assert len(app.document.nodes) == len(fixture.nodes) == 3
    assert all(p.name == "Replacement protocol" for p in app.document.design.protocols)
    assert all(layer.name.startswith("Replacement layer") for layer in app.document.design.layers)
    checks.append("rebuilt lists fit the minimum design window; failed Apply keeps the draft; successful Apply saves all notes and a backup")


def check_immediate_protocol_clear(root, app, path, checks):
    source = example_atlas()
    fixture = replace(source, design=replace(source.design, label_mode="combined"))
    assert app.apply_design(fixture)
    app.protocol_filter_var.set("SSH")
    app._filter_changed()
    pump(root)
    meshes = dict(app.scene.meshes)
    camera = (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target))
    original_bytes = path.read_bytes()
    dialog = DesignEditor(root, app.document, app.apply_design)
    try:
        dialog.layers.select(7)
        dialog.layers.name.set("Pending layer rename")
        assert dialog.layers.update_entry()
        dialog.protocol_caption.set("Pending caption")
        dialog.notebook.select(dialog.protocols)
        with patch("atlas.design_editor.messagebox.askyesno", return_value=True), \
             patch("atlas.ui.write_atlas", side_effect=OSError("Simulated immediate-clear save failure")), \
             patch("atlas.ui.messagebox.showerror") as error_box:
            assert not dialog.protocols.clear_list()
        assert error_box.called and app.document == fixture and path.read_bytes() == original_bytes
        assert dialog.draft.protocols == fixture.design.protocols and dialog.draft.nodes == fixture.nodes
        assert dialog.draft.layers[-1].name == "Pending layer rename"
        checks.append("failed immediate protocol removal preserves saved assignments, list and pending layer edits")

        with patch("atlas.design_editor.messagebox.askyesno", return_value=True) as confirmation:
            dialog.protocols.clear_button.invoke()
        pump(root)
        cleared = fixture.without_protocols()
        assert "immediately" in confirmation.call_args.args[1]
        assert app.document == read_atlas(path) == cleared
        assert read_atlas(path.with_suffix(".json.bak")) == fixture
        assert dialog.protocols.listbox.size() == 0 and dialog.apply_button.instate(["!disabled"])
        assert "removed and saved" in dialog.readiness.get()
        assert app.protocol_var.get() == "No protocol"
        assert app.protocol_filter_var.get() == "All protocols"
        assert tuple(app.protocol_box.cget("values")) == ("No protocol",)
        assert app.scene.meshes == meshes and len(app.scene.actors) == len(fixture.nodes)
        assert (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target)) == camera
        assert app.document.design.layers[-1].name == "Application"
        assert app.document.design.protocol_caption == "Protocol"
        assert dialog.draft.layers[-1].name == "Pending layer rename"
        checks.append("Remove protocols saves at confirmation, updates editor and filters, and keeps geometry, notes and camera")
    finally:
        dialog.cancel()
    assert app.document == read_atlas(path) == cleared
    assert app.document.design.layers[-1].name == "Application"
    checks.append("Cancel after immediate removal keeps the protocol list empty and discards unrelated design edits")

    # With an empty layer draft, removal must still save a valid atlas using
    # its saved layers, rather than accidentally committing an invalid draft.
    assert app.apply_design(fixture)
    dialog = DesignEditor(root, app.document, app.apply_design)
    try:
        with patch("atlas.design_editor.messagebox.askyesno", return_value=True):
            assert dialog.layers.clear_list()
            assert dialog.protocols.clear_list()
        assert dialog.draft.layers == () and dialog.draft.protocols == ()
        assert dialog.apply_button.instate(["disabled"])
        assert read_atlas(path) == cleared and app.document.design.layers == fixture.design.layers
        assert all(node.protocol is None for node in dialog.draft.nodes)
    finally:
        dialog.cancel()
    checks.append("protocol removal saves independently while an empty layer list remains a draft")

    backup = path.with_suffix(".json.bak").read_bytes()
    current_bytes = path.read_bytes()
    dialog = DesignEditor(root, app.document, app.apply_design)
    try:
        dialog.protocols.add()
        with patch("atlas.design_editor.messagebox.askyesno", return_value=True), \
             patch("atlas.ui.write_atlas") as writer:
            assert dialog.protocols.clear_list()
        assert not writer.called and path.read_bytes() == current_bytes
        assert path.with_suffix(".json.bak").read_bytes() == backup
        assert dialog.apply_button.instate(["!disabled"])
    finally:
        dialog.cancel()
    checks.append("clearing an unsaved protocol addition from an already empty list preserves the previous backup")

    dialog = DesignEditor(root, app.document, app.apply_design)
    dialog.protocols.add()
    protocol_id = dialog.protocols.current
    dialog.protocols.name.set("New optional protocol")
    assert dialog.protocols.update_entry() and dialog.apply()
    assert all(node.protocol is None for node in app.document.nodes)
    app.protocol_filter_var.set("No protocol")
    app._filter_changed()
    assert app.scene.protocol_filter is NO_PROTOCOL_FILTER
    assert all(app.scene.is_visible(node) for node in app.document.nodes)
    selected = app.selected
    app.protocol_var.set("New optional protocol")
    assert app.save_node()
    assert app.document.get(selected).protocol == protocol_id
    assert app.protocol_filter_var.get() == "All protocols"
    app.protocol_filter_var.set("No protocol")
    app._filter_changed()
    assert sum(app.scene.is_visible(node) for node in app.document.nodes) == len(fixture.nodes) - 1
    app.protocol_filter_var.set("New optional protocol")
    app._filter_changed()
    assert sum(app.scene.is_visible(node) for node in app.document.nodes) == 1
    app.protocol_var.set("No protocol")
    assert app.save_node() and app.document.get(selected).protocol is None
    checks.append("adding protocols stays optional; explicit assignment, unassignment and No protocol filtering work together")

    # A user protocol named No protocol remains distinct from the unassigned
    # state in both the editor and the filter.
    colliding_name = Protocol("named-no-protocol", "No protocol")
    candidate = app.document.with_design(replace(app.document.design, protocols=app.document.design.protocols + (colliding_name,)))
    assert app.apply_design(candidate)
    assert app._no_protocol != "No protocol"
    app.protocol_var.set("No protocol")
    assert app.save_node() and app.document.get(selected).protocol == colliding_name.id
    app.protocol_filter_var.set("No protocol")
    app._filter_changed()
    assert sum(app.scene.is_visible(node) for node in app.document.nodes) == 1
    app.protocol_filter_var.set(app._no_protocol)
    app._filter_changed()
    assert sum(app.scene.is_visible(node) for node in app.document.nodes) == len(fixture.nodes) - 1
    checks.append("a protocol named No protocol is distinct from the unassigned state")

    exported = path.parent / "optional-protocols.json"
    with patch("atlas.ui.filedialog.asksaveasfilename", return_value=str(exported)):
        app.export_json()
    saved = read_atlas(exported)
    assert saved == app.document and any(n.protocol is None for n in saved.nodes)
    dialog = DesignEditor(root, app.document, app.apply_design)
    with patch("atlas.design_editor.messagebox.askyesno", return_value=True):
        assert dialog.protocols.clear_list()
    dialog.cancel()
    app.new_node()
    assert app.placement_state == "placing" and app._protocol_id() is None
    app.name_var.set("Block without a protocol")
    assert app.place_at(app.depth_var.get(), int(app.slot_var.get()) - 1)
    assert app.save_node() and app.document.get(app.selected).protocol is None
    with patch("atlas.ui.messagebox.askyesno", return_value=True):
        assert app.new_empty_atlas()
    assert app.document.design.protocols == () and app.protocol_var.get() == "No protocol"
    app.name_var.set("First block with no protocols")
    assert app.save_node()
    assert read_atlas(path).nodes[0].protocol is None
    with patch("atlas.ui.filedialog.askopenfilename", return_value=str(exported)), \
         patch("atlas.ui.messagebox.askyesno", return_value=True):
        app.import_json()
    assert app.document == saved
    checks.append("optional protocol state survives JSON, new-block placement, Empty atlas and creating its first block")


def main(report_path=None):
    checks = []
    with TemporaryDirectory() as folder:
        path = Path(folder) / "atlas.json"
        doc = example_atlas()
        write_atlas(path, doc)
        root = tk.Tk()
        app = AtlasApp(root, path, doc)
        errors = []
        root.report_callback_exception = lambda *error: errors.append(error)
        try:
            pump(root, 12)
            assert not app.dirty
            assert len(app.scene.actors) == len(doc.nodes) == 14
            assert app.scene.block_appearance == "outline"
            assert sum(solid.GetVisibility() for solid, _ in app.scene.actors.values()) == 1
            app.set_block_appearance("solid")
            checks.append("initial render: 14 occupied meshes, no empty-cell actors")

            slider = app.scale_widget
            label_positions = [slider.coords(item) for item in slider.find_withtag("label")]
            for depth, (x, y) in zip(range(CENTER_DEPTH, 5), label_positions):
                slider.event_generate("<Button-1>", x=round(x), y=round(y))
                assert app.depth_var.get() == depth
                handle = slider.coords(slider.find_withtag("handle")[0])
                assert abs((handle[0] + handle[2]) / 2 - x) < .01
            slider.focus_force()
            pump(root)
            slider.event_generate("<Home>")
            assert app.depth_var.get() == CENTER_DEPTH
            slider.event_generate("<Right>")
            assert app.depth_var.get() == 0
            slider.event_generate("<End>")
            assert app.depth_var.get() == 4
            app._load_editor(doc.get("11"))
            checks.append("all six slider positions align with labels and support pointer/keyboard input")

            slot_slider = app.slot_slider
            with patch.object(slider, "focus_get", side_effect=KeyError("popdown")), \
                 patch.object(slot_slider, "focus_get", side_effect=KeyError("popdown")):
                slider.draw()
                slot_slider.draw()
            assert not errors
            checks.append("both sliders redraw safely while a combobox popdown owns transient focus")

            def slot_x(slot):
                left, right = slot_slider._track_bounds()
                return left + (right - left) * slot / 15

            def slide(slot):
                x = round(slot_x(slot))
                slot_slider.event_generate("<ButtonPress-1>", x=x, y=11)
                slot_slider.event_generate("<ButtonRelease-1>", x=x, y=11)

            saved_bytes = path.read_bytes()
            for slot in range(16):
                slide(slot)
                assert app.slot_var.get() == f"{slot + 1:02d}"
                handle = slot_slider.coords(slot_slider.find_withtag("handle")[0])
                assert abs((handle[0] + handle[2]) / 2 - slot_x(slot)) < .01
                valid = slot in doc.free_starts(7, 2, exclude_id="11")
                assert app.placement_state == ("locked" if valid else "placing")
            stops = [slot_slider.coords(item)[0] for item in slot_slider.find_withtag("stop")]
            assert len(stops) == 16
            for item in slot_slider.find_withtag("label"):
                assert abs(slot_slider.coords(item)[0] - stops[int(slot_slider.itemcget(item, "text")) - 1]) < .01
            assert app.document == doc and path.read_bytes() == saved_bytes
            app._load_editor(doc.get("11"))
            checks.append("all sixteen Start slot positions snap, align with their labels, and leave saved data unchanged")

            def point(slot, depth=2):
                node = Node("target", "Target", 7, "Other", depth, slot=slot)
                x, y, _ = app.scene.project(wedge_mesh(node).label_anchor)
                return round(x), round(y)

            def click(slot, depth=2, *, settle=True):
                x, y = point(slot, depth)
                app.canvas.event_generate("<ButtonPress-1>", x=x, y=y)
                app.canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
                if settle:
                    pump(root)

            app.new_node()
            app.size_var.set("1/8")
            app.size_box.event_generate("<<ComboboxSelected>>")
            app.name_var.set("Slider draft")
            app.notes.insert("1.0", "Keep these notes while sliding.")
            app._hover_at(*point(12))
            assert app._floating_position == (2, 12)
            slot_slider.event_generate("<ButtonPress-1>", x=round(slot_x(8)), y=11)
            assert app.scene.preview_node.slot == 8 and app._floating_position is None
            slot_slider.event_generate("<B1-Motion>", x=round(slot_x(9)), y=11)
            assert app.scene.preview_node.slot == 9 and app.placement_state == "placing"
            slot_slider.event_generate("<ButtonRelease-1>", x=round(slot_x(9)), y=11)
            assert app.placement_state == "locked" and app.slot_var.get() == "10"
            assert app.scene.preview_node.slot == 9 and app.scene.preview_node.span == 2
            assert "202.5°" in app.slot_label.cget("text") and "Slots 10–11" in app.slot_label.cget("text")
            app._hover_at(*point(12))
            assert app.scene.preview_node.slot == 9
            assert app.name_var.get() == "Slider draft" and app.notes.get("1.0", "end-1c") == "Keep these notes while sliding."
            assert app.document == doc and path.read_bytes() == saved_bytes
            checks.append("Start slot drag previews live, clears mouse following, and locks on release without losing draft text")

            app.layer_var.set("5  Session")
            app.depth_var.set(CENTER_DEPTH)
            slot_slider.focus_force()
            pump(root)
            slot_slider.event_generate("<End>")
            assert app.slot_var.get() == "16" and app.placement_state == "locked", (
                app.slot_var.get(), app.placement_state, app.slot_slider.enabled)
            assert "337.5°" in app.slot_label.cget("text") and "Slots 16 → 01" in app.slot_label.cget("text")
            footprint = slot_slider.find_withtag("footprint")
            assert len(footprint) == 2
            assert {tag for item in footprint for tag in slot_slider.gettags(item) if tag.startswith("slot-")} == {"slot-0", "slot-15"}
            slot_slider.event_generate("<Right>")
            assert app.slot_var.get() == "16"
            slot_slider.event_generate("<Left>")
            assert app.slot_var.get() == "15"
            slot_slider.event_generate("<Home>")
            slot_slider.event_generate("<Left>")
            assert app.slot_var.get() == "01"
            for size, span in (("1/16", 1), ("1/8", 2), ("1/4", 4), ("1/2", 8), ("Full", 16)):
                app.size_var.set(size)
                app.size_box.event_generate("<<ComboboxSelected>>")
                assert len(slot_slider.find_withtag("footprint")) == span
            assert "All slots" in app.slot_label.cget("text")
            checks.append("slot keyboard controls clamp at endpoints and show footprints for every size, including wrap-around")

            slot_slider.event_generate("<End>")
            slot_slider.event_generate("<ButtonPress-1>", x=round(slot_x(6)), y=11)
            slot_slider.event_generate("<B1-Motion>", x=round(slot_x(7)), y=11)
            assert app.placement_state == "placing" and app.slot_var.get() == "08"
            slot_slider.event_generate("<Escape>")
            slot_slider.event_generate("<ButtonRelease-1>", x=round(slot_x(7)), y=11)
            assert app.placement_state == "locked" and app.slot_var.get() == "16"
            assert app.name_var.get() == "Slider draft" and path.read_bytes() == saved_bytes
            checks.append("Escape cancels a slider drag and ignores its later release, preserving the prior lock and notes")

            app._load_editor(doc.get("11"))
            app.size_var.set("1/8")
            app.size_box.event_generate("<<ComboboxSelected>>")
            slide(5)
            assert app.placement_state == "locked" and app.slot_var.get() == "06"
            assert len(slot_slider.find_withtag("blocked")) == 6
            slide(3)
            assert app.placement_state == "placing" and not app.scene.preview_valid
            assert app.save_button.instate(["disabled"]) and not app.save_node()
            assert app.document == doc and path.read_bytes() == saved_bytes
            slot_slider.event_generate("<Escape>")
            assert app.placement_state == "locked" and app.slot_var.get() == "06"
            app._load_editor(doc.get("11"))
            app.size_var.set("1/16")
            app.size_box.event_generate("<<ComboboxSelected>>")
            checks.append("blocked slot marks account for block width and selected-block exclusion; invalid releases cannot lock or save")

            app.new_node()
            assert app.placement_state == "placing" and app.save_button.instate(["disabled"])
            app._hover_at(*point(8))
            assert app.scene.preview_node.slot == 8
            app.name_var.set("Placement lock test")
            app.notes.insert("1.0", "Keep these notes while moving.")
            assert app.scene.preview_node.slot == 8
            before_bytes = path.read_bytes()
            assert not app.save_node() and path.read_bytes() == before_bytes
            checks.append("Add here enters Placing; hover preserves text and Save waits for a locked location")

            app._hover(SimpleNamespace(x=point(12)[0], y=point(12)[1]))
            assert app._hover_job is not None
            click(8, settle=False)
            assert app.placement_state == "locked" and app._hover_job is None
            # A new physical mouse event can schedule a different hover job
            # during update(); check cancellation before processing those events.
            pump(root)
            assert app.slot_var.get() == "09" and app.scene.preview_node.slot == 8
            assert app.save_button.instate(["!disabled"])
            app._hover_at(*point(12))
            x, y = point(12)
            app.canvas.event_generate("<Motion>", x=x, y=y)
            pump(root)
            click(12)
            assert app.placement_state == "locked" and app.scene.preview_node.slot == 8
            assert app.slot_var.get() == "09" and "Locked" in app.editor_state.cget("text")
            checks.append("left-click locks the draft and cancels queued hover; further motion or empty clicks leave it fixed")

            assert app.scene.pick_preview(*point(8))
            click(8)
            assert app.placement_state == "placing"
            origin = app._placement_origin
            yaw = app.scene.yaw
            app.canvas.event_generate("<ButtonPress-1>", x=70, y=400)
            app.canvas.event_generate("<B1-Motion>", x=90, y=410)
            app.canvas.event_generate("<ButtonRelease-1>", x=90, y=410)
            pump(root)
            assert app.scene.yaw != yaw and app.placement_state == "placing"
            assert app._placement_origin == origin and path.read_bytes() == before_bytes
            checks.append("dragging while Placing rotates the camera without locking or saving the block")
            app._hover_at(*point(12))
            assert app.scene.preview_node.slot == 12
            click(0)
            assert app.placement_state == "placing" and app.selected is None
            assert app.scene.preview_node.slot == 0 and not app.scene.preview_valid
            assert path.read_bytes() == before_bytes and app.name_var.get() == "Placement lock test"
            checks.append("clicking the locked draft picks it up; occupied targets stay red and cannot lock")

            app.canvas.focus_force()
            pump(root)
            app.canvas.event_generate("<Escape>")
            pump(root)
            assert app.placement_state == "locked" and app.slot_var.get() == "09"
            assert app.scene.preview_node.slot == 8
            assert app.name_var.get() == "Placement lock test"
            assert app.notes.get("1.0", "end-1c") == "Keep these notes while moving."
            assert path.read_bytes() == before_bytes
            checks.append("Escape restores the last locked location while preserving title, notes, and saved data")

            click(8)
            assert app.placement_state == "placing"
            app._hover_at(*point(12))
            app._hover(SimpleNamespace(x=point(14)[0], y=point(14)[1]))
            click(12)
            assert app.placement_state == "locked" and app.slot_var.get() == "13"
            app._hover_at(*point(14))
            assert app.scene.preview_node.slot == 12
            assert app.save_node()
            locked_id = app.selected
            assert read_atlas(path).get(locked_id).slot == 12 and len(app.document.nodes) == 15
            checks.append("the next click locks the anticipated location; Save persists that exact slot")

            click(12)
            assert app.placement_state == "placing" and app.selected == locked_id
            app._hover_at(*point(8))
            click(8)
            assert app.placement_state == "locked" and app.selected == locked_id
            assert read_atlas(path).get(locked_id).slot == 12
            assert app.save_node()
            assert read_atlas(path).get(locked_id).slot == 8 and len(app.document.nodes) == 15
            saved_bytes = path.read_bytes()
            click(8)
            app._hover_at(*point(12))
            app.canvas.event_generate("<Escape>")
            pump(root)
            assert app.placement_state == "locked" and app.slot_var.get() == "09"
            assert path.read_bytes() == saved_bytes and not app.dirty
            with patch("atlas.ui.messagebox.askyesno", return_value=True):
                assert app.delete_node()
            assert app.document == doc
            app._load_editor(doc.get("11"))
            pump(root)
            checks.append("saved blocks can be picked up and relocked without changing identity; Escape leaves the file unchanged")

            before_meshes = dict(app.scene.meshes)
            target = Node("target", "Target", 7, "Other", 2, slot=8)
            x, y, _ = app.scene.project(wedge_mesh(target).label_anchor)
            assert app.scene.position_at(x, y, 7) == (2, 8)
            assert app.scene.pick(x, y) is None
            app.canvas.event_generate("<ButtonPress-1>", x=round(x), y=round(y))
            app.canvas.event_generate("<ButtonRelease-1>", x=round(x), y=round(y))
            pump(root)
            assert app.selected is None and app.depth_var.get() == 2 and app.slot_var.get() == "09"
            assert app.scene.preview_actor is not None and not app.scene.preview_actor.GetPickable()
            app.name_var.set("Placed by clicking empty space")
            app.notes.insert("1.0", "A placement finding.")
            assert app.save_node()
            placed = app.selected
            placed_mesh = app.scene.meshes[placed]
            assert app.document.get(placed).slot == 8 and app.document.get(placed).span == 1
            assert all(app.scene.meshes[key] == mesh for key, mesh in before_meshes.items())
            checks.append("empty-space click chooses a fixed slot, previews it, and saves only a 1/16 block")

            app.add_button.invoke()
            assert app.slot_var.get() == "10"
            app.size_var.set("1/8")
            app.size_box.event_generate("<<ComboboxSelected>>")
            app.name_var.set("Larger neighbor")
            assert app.place_at(app.depth_var.get(), int(app.slot_var.get()) - 1)
            assert app.save_node()
            larger = app.selected
            assert app.document.get(larger).span == 2 and app.document.get(larger).slot == 9
            assert app.scene.meshes[placed] == placed_mesh
            app.select_node(placed)
            app.size_var.set("1/8")
            app.size_box.event_generate("<<ComboboxSelected>>")
            before = read_atlas(path)
            assert not app.save_node() and read_atlas(path) == before
            assert app.scene.preview_actor is not None
            app._load_editor(app.document.get(larger))
            app.size_var.set("1/4")
            app.size_box.event_generate("<<ComboboxSelected>>")
            assert app.save_node() and app.document.get(larger).span == 4
            assert app.scene.meshes[placed] == placed_mesh
            app.new_node()
            assert app.selected == larger and "No room" in app.editor_state.cget("text")
            assert app.depth_var.get() == 2
            checks.append("mixed sizes, adjacent-space resize validation, and no automatic radial spill")

            app.size_var.set("1/8")
            app.size_box.event_generate("<<ComboboxSelected>>")
            assert app.save_node()
            app.select_node("11")
            assert app.size_var.get() == "1/16"
            app.new_node()
            assert app.size_var.get() == "1/8" and app.slot_var.get() == "06"
            app.name_var.set("Draft position")
            app.notes.insert("1.0", "Keep this draft while placing.")
            assert app.place_at(2, 14)
            assert app.slot_var.get() == "15" and app.name_var.get() == "Draft position"
            assert app.notes.get("1.0", "end-1c") == "Keep this draft while placing."
            with patch("atlas.ui.messagebox.askyesnocancel", return_value=False):
                assert app.select_node(larger)
            with patch("atlas.ui.messagebox.askyesno", return_value=True):
                assert app.delete_node()
            assert app.scene.meshes[placed] == placed_mesh
            app.select_node(placed)
            app.new_node()
            assert app.slot_var.get() == "10" and app.size_var.get() == "1/8"
            app.select_node(placed)
            with patch("atlas.ui.messagebox.askyesno", return_value=True):
                assert app.delete_node()
            assert app.document == doc
            app.select_node("11")
            app.size_var.set("1/16")
            app.size_box.event_generate("<<ComboboxSelected>>")
            checks.append("last chosen size survives selection changes; deleted gaps are reused; placement keeps draft text")

            x, y, _ = app.scene.project(app.scene.meshes["8"].label_anchor)
            assert app.scene.pick(x, y) == "8"
            app.canvas.event_generate("<ButtonPress-1>", x=int(x), y=int(y))
            app.canvas.event_generate("<ButtonRelease-1>", x=int(x), y=int(y))
            pump(root)
            assert app.selected == "8"
            checks.append("surface picking and click-to-edit")

            yaw = app.scene.yaw
            app.canvas.event_generate("<ButtonPress-1>", x=70, y=400)
            app.canvas.event_generate("<B1-Motion>", x=120, y=425)
            app.canvas.event_generate("<ButtonRelease-1>", x=120, y=425)
            pump(root)
            assert app.scene.yaw != yaw and app.selected == "8"
            scale = app.scene.scale
            app._zoom(1)
            pump(root)
            assert app.scene.scale < scale
            checks.append("drag rotation and zoom do not change coordinates or selection")

            app.filter_var.set("4  Transport")
            app.filter_box.event_generate("<<ComboboxSelected>>")
            pump(root)
            assert sum(a.GetVisibility() for a, _ in app.scene.actors.values()) == 2
            app._cycle_node(1)
            assert app.selected == "6"
            app._cycle_node(-1)
            assert app.selected == "7"
            checks.append("layer filter and keyboard note traversal")

            meshes = dict(app.scene.meshes)
            app.protocol_filter_var.set("TCP")
            app.protocol_filter_box.event_generate("<<ComboboxSelected>>")
            pump(root)
            assert sum(a.GetVisibility() for a, _ in app.scene.actors.values()) == 1
            assert app.scene.meshes == meshes
            app._cycle_node(1)
            assert app.selected == "6"
            app.protocol_filter_var.set("All protocols")
            app.protocol_filter_box.event_generate("<<ComboboxSelected>>")
            checks.append("combined layer/protocol filtering preserves block sizes, positions, and keyboard traversal")

            original = app.document.get(app.selected)
            before_mesh = app.scene.meshes[original.id]
            app.new_node()
            assert app.depth_var.get() == original.depth
            assert int(app.layer_var.get().split()[0]) == original.layer
            assert app.protocol_var.get() == original.protocol
            app.name_var.set("Smoke-test note")
            app.notes.insert("1.0", "A local test finding.")
            assert app.place_at(app.depth_var.get(), int(app.slot_var.get()) - 1)
            assert app.save_node()
            added = app.selected
            assert len(read_atlas(path).nodes) == 15
            assert app.document.get(added).coordinate == original.coordinate
            assert app.scene.meshes[original.id] == before_mesh
            assert app.document.get(added).span == 1 and app.document.get(added).slot == 2
            assert "Start slot 03 / 16" in app.slot_label.cget("text")
            checks.append("Add here retains layer/depth and adds its chosen size without changing neighbors")
            app.protocol_filter_var.set(original.protocol)
            app._filter_changed()
            app.layer_var.set("5  Session")
            app.protocol_var.set("Other")
            app.depth_var.set(0)
            assert app.save_node()
            assert read_atlas(path).get(added).coordinate == (5, "Other", 0)
            assert app.filter_var.get() == "All layers"
            assert app.protocol_filter_var.get() == "All protocols"
            assert app.scene.meshes[original.id] == before_mesh
            checks.append("create, edit, move and automatic local save")

            app.scale_widget.focus_force()
            pump(root)
            app.scale_widget.event_generate("<Home>")
            assert app.depth_var.get() == CENTER_DEPTH
            assert app.save_node()
            center = app.document.get(added)
            assert center.depth == CENTER_DEPTH and center.notes == "A local test finding."
            assert "CENTER" in app.coordinate_label.cget("text")
            first_center_mesh = app.scene.meshes[added]
            app.add_button.invoke()
            app.name_var.set("Second center block")
            assert app.place_at(app.depth_var.get(), int(app.slot_var.get()) - 1)
            assert app.save_node()
            second_center = app.selected
            assert app.document.get(second_center).position == center.position
            assert app.document.get(second_center).span == 1
            assert app.scene.meshes[added] == first_center_mesh
            with patch("atlas.ui.messagebox.askyesno", return_value=True):
                assert app.delete_node()
            assert app.scene.meshes[added] == first_center_mesh
            app.select_node(added)
            app.scale_widget.focus_force()
            pump(root)
            app.scale_widget.event_generate("<Right>")
            assert app.depth_var.get() == 0 and app.save_node()
            checks.append("center and radial positions use the slider alone, preserving fixed sizes and neighboring blocks")

            before = read_atlas(path)
            app.layer_var.set("7  Application")
            app.protocol_var.set("SSH")
            app.depth_var.set(2)
            app.name_var.set(" ")
            assert not app.save_node()
            assert read_atlas(path) == before
            app._load_editor(app.document.get(added))
            app.name_var.set("Uncommitted edit")
            with patch("atlas.ui.messagebox.askyesnocancel", return_value=None):
                assert not app.select_node("11")
            assert app.selected == added and app.dirty
            with patch("atlas.ui.messagebox.askyesnocancel", return_value=False):
                assert app.select_node("11")
            assert not app.dirty
            checks.append("invalid-note prevention and unsaved-edit cancel/discard")

            app.select_node(added)
            with patch("atlas.ui.messagebox.askyesno", return_value=True):
                assert app.delete_node()
            assert read_atlas(path).get(added) is None
            assert read_atlas(path.with_suffix(".json.bak")).get(added) is not None
            checks.append("delete with previous-version backup")

            export = Path(folder) / "export.json"
            with patch("atlas.ui.filedialog.asksaveasfilename", return_value=str(export)):
                app.export_json()
            assert read_atlas(export) == app.document
            assert json.loads(export.read_text())["version"] == 10
            legacy = Path(folder) / "legacy.json"
            legacy.write_text(json.dumps({"type": "cyber-knowledge-atlas", "version": 3,
                                         "nodes": [{**n.to_dict(), "id": int(n.id)} for n in doc.nodes]}))
            with patch("atlas.ui.filedialog.askopenfilename", return_value=str(legacy)), \
                 patch("atlas.ui.messagebox.askyesno", return_value=True):
                app.import_json()
            assert app.document == doc
            checks.append("JSON export and original HTML v3 import")

            full_path = Path(folder) / "full.json"
            full = Atlas(tuple(Node(str(i), str(i), 7, "Other", 2, slot=i) for i in range(16)))
            write_atlas(full_path, full)
            with patch("atlas.ui.filedialog.askopenfilename", return_value=str(full_path)), \
                 patch("atlas.ui.messagebox.askyesno", return_value=True):
                app.import_json()
            selected = app.selected
            app.new_node()
            assert app.selected == selected and app.document == full and app.depth_var.get() == 2
            assert "No room" in app.editor_state.cget("text")
            checks.append("a full ring reports no room and keeps all blocks at their saved positions")

            original_bytes = path.read_bytes()
            with patch("atlas.ui.messagebox.askyesno", return_value=False):
                app.empty_button.invoke()
            assert app.document == full and path.read_bytes() == original_bytes and app.selected == selected
            app.name_var.set("Keep this unsaved draft")
            with patch("atlas.ui.messagebox.askyesnocancel", return_value=None), \
                 patch("atlas.ui.messagebox.askyesno") as confirmation:
                assert not app.new_empty_atlas()
            assert not confirmation.called and app.dirty
            assert app.name_var.get() == "Keep this unsaved draft" and path.read_bytes() == original_bytes
            app._load_editor(app.document.get(selected))
            checks.append("Empty atlas button respects replacement cancellation and unsaved-draft cancellation")

            with patch("atlas.ui.messagebox.askyesno", return_value=True), \
                 patch("atlas.ui.write_atlas", side_effect=OSError("Simulated write failure")), \
                 patch("atlas.ui.messagebox.showerror") as error_box:
                assert not app.new_empty_atlas()
            assert error_box.called and app.document == full and path.read_bytes() == original_bytes
            assert app.selected == selected and len(app.scene.actors) == 16
            checks.append("failed Empty atlas save preserves the current atlas, file, and selection")

            app.name_var.set("Saved before starting fresh")
            app.filter_var.set("7  Application")
            app.protocol_filter_var.set("Other")
            app._filter_changed()
            with patch("atlas.ui.messagebox.askyesnocancel", return_value=True), \
                 patch("atlas.ui.messagebox.askyesno", return_value=True):
                assert app.new_empty_atlas()
            pump(root)
            assert app.document == read_atlas(path) == Atlas()
            assert not app.scene.actors and app.selected is None and not app.dirty
            assert app.filter_var.get() == "All layers" and app.protocol_filter_var.get() == "All protocols"
            assert app.name_var.get() == "" and app.notes.get("1.0", "end-1c") == ""
            assert app.size_var.get() == "1/16" and app.slot_var.get() == "01"
            backup_path = path.with_suffix(".json.bak")
            saved_previous = read_atlas(backup_path)
            assert len(saved_previous.nodes) == 16 and saved_previous.get(selected).name == "Saved before starting fresh"
            backup_bytes = backup_path.read_bytes()
            with patch("atlas.ui.messagebox.askyesno") as confirmation:
                assert app.new_empty_atlas()
            assert not confirmation.called and backup_path.read_bytes() == backup_bytes
            checks.append("Empty atlas saves drafts when requested, backs up the previous atlas, resets the editor, and preserves that backup on repeat")

            blank = Path(folder) / "blank.json"
            write_atlas(blank, Atlas())
            with patch("atlas.ui.filedialog.askopenfilename", return_value=str(blank)), \
                 patch("atlas.ui.messagebox.askyesno", return_value=True):
                app.import_json()
            pump(root)
            assert app.document == Atlas() and not app.scene.actors
            app.name_var.set("First block")
            assert app.save_node()
            assert len(app.document.nodes) == 1
            checks.append("empty atlas import and first-volume allocation")

            broken = Path(folder) / "invalid.json"
            broken.write_text("not json")
            with patch("atlas.ui.filedialog.askopenfilename", return_value=str(broken)), \
                 patch("atlas.ui.messagebox.showerror") as error_box:
                app.import_json()
            assert error_box.called and len(app.document.nodes) == 1
            checks.append("invalid imports leave the current document untouched")

            app._load_editor(app.document.nodes[0])
            original = app.document
            original_bytes = path.read_bytes()
            app.name_var.set("Unsaved before design")
            with patch("atlas.ui.messagebox.askyesnocancel", return_value=None), \
                 patch("atlas.ui.DesignEditor") as editor_factory:
                app.edit_design()
            assert not editor_factory.called and app.name_var.get() == "Unsaved before design"
            app._load_editor(original.nodes[0])
            checks.append("Edit design respects unsaved-note cancellation")

            opened = []

            def cancel_design():
                dialogs = [child for child in root.winfo_children() if isinstance(child, DesignEditor)]
                assert len(dialogs) == 1
                dialog = dialogs[0]
                try:
                    dialog.layers.name.set("Cancelled layer rename")
                    assert dialog.layers.update_entry()
                    opened.append(True)
                finally:
                    dialog.cancel()

            root.after(80, cancel_design)
            app.design_button.invoke()
            assert opened and app.document == original and path.read_bytes() == original_bytes
            checks.append("top-bar design button opens a modal draft; Cancel leaves atlas and disk unchanged")

            dialog = DesignEditor(root, app.document, app.apply_design)
            pump(root)
            dialog.layers.select(7)
            dialog.layers.name.set("User services")
            dialog.layers.color.set("#d87799")
            assert dialog.layers.update_entry()
            dialog.layers.move(-1)
            assert dialog.working.design.layer_index(7) == 5
            assert dialog.working.nodes == original.nodes
            dialog.layers.add()
            custom_layer = dialog.layers.current
            dialog.layers.name.set("Operations")
            dialog.layers.color.set("#68cdb0")
            assert dialog.layers.update_entry()
            dialog.notebook.select(dialog.protocols)
            dialog.protocols.add()
            custom_protocol = dialog.protocols.current
            dialog.protocols.name.set("Lab protocol")
            assert dialog.protocols.update_entry()
            dialog.protocols.select("SSH")
            dialog.protocols.name.set("Remote shell")
            assert dialog.protocols.update_entry()
            dialog.layer_caption.set("Tier")
            dialog.protocol_caption.set("Category")
            dialog.label_mode.set("Title + layer + protocol")
            dialog.notebook.select(2)
            assert "User services" in dialog.label_preview.cget("text")
            assert app.document == original and path.read_bytes() == original_bytes
            checks.append("design draft adds, renames, recolors and reorders entries without changing saved blocks")

            dialog.protocols.name.set("DNS")
            assert not dialog.apply()
            assert "distinct" in dialog.error.get() and path.read_bytes() == original_bytes
            dialog.protocols.name.set("Remote shell")
            with patch("atlas.ui.write_atlas", side_effect=OSError("Simulated design save failure")), \
                 patch("atlas.ui.messagebox.showerror") as error_box:
                assert not dialog.apply()
            assert error_box.called and dialog.winfo_exists() and app.document == original
            assert path.read_bytes() == original_bytes
            checks.append("invalid design and failed Apply preserve the saved document and keep the draft open")

            assert dialog.apply()
            pump(root)
            assert app.document == read_atlas(path)
            assert len(app.document.design.layers) == 8 and len(app.document.design.protocols) == 18
            assert app.document.nodes == original.nodes
            assert app.layer_var.get() == "6  User services"
            assert app.layer_caption.cget("text") == "Tier" and app.protocol_caption.cget("text") == "Category"
            assert app.scene.design == app.document.design and len(app.scene._axis_actors) == 10
            assert app.scene.scale >= len(app.document.design.layers) / 2
            assert app.document.design.layer(7).color == "#d87799"
            checks.append("Apply saves custom design, updates controls/colors/axis/camera, and retains block identities")

            app._load_editor(None, (custom_layer, custom_protocol, 0), slot=8)
            app.name_var.set("Custom block")
            app.notes.insert("1.0", "Custom design notes")
            assert app.save_node()
            custom_node = app.document.get(app.selected)
            assert custom_node.layer == custom_layer and custom_node.protocol == custom_protocol
            app.filter_var.set("8  Operations")
            app.protocol_filter_var.set("Lab protocol")
            app._filter_changed()
            pump(root)
            assert sum(app.scene.is_visible(n) for n in app.document.nodes) == 1
            anchor = app.scene.meshes[custom_node.id].label_anchor
            x, y, _ = app.scene.project(anchor)
            assert app.scene.position_at(x, y, custom_layer) == (0, 8)
            assert app.scene.pick(x, y) == custom_node.id
            assert app.document.design.block_label(custom_node) == "Custom block · Operations · Lab protocol"
            label_texts = [app.canvas.itemcget(item, "text") for item in app.canvas.find_withtag("overlay")
                           if app.canvas.type(item) == "text"]
            assert "Custom block\nOperations · Lab protocol" in label_texts
            assert app.place_at(1, 8)  # A new draft from a selected saved block.
            assert app._preview_candidate().protocol == custom_protocol
            app._load_editor(custom_node)
            checks.append("custom layer/protocol entries support saving, filters, picking and placement with stable IDs")

            dialog = DesignEditor(root, app.document, app.apply_design)
            dialog.protocols.select(custom_protocol)

            def cancel_reassignment():
                for child in dialog.winfo_children():
                    if isinstance(child, ReassignDialog):
                        assert child.confirm.instate(["disabled"])
                        child.destroy()

            dialog.after(80, cancel_reassignment)
            assert not dialog.protocols.remove()
            assert dialog.working == app.document

            def confirm_reassignment():
                for child in dialog.winfo_children():
                    if isinstance(child, ReassignDialog):
                        child.choice.set("Remote shell")
                        child.confirm.invoke()

            dialog.after(80, confirm_reassignment)
            assert dialog.protocols.remove()
            assert dialog.working.get(custom_node.id).protocol == "SSH"
            dialog.layers.select(custom_layer)
            assert dialog.layers.remove(7)
            assert dialog.working.get(custom_node.id).layer == 7
            assert app.document.get(custom_node.id) == custom_node
            assert dialog.apply()
            pump(root)
            assert app.document.get(custom_node.id).coordinate == (7, "SSH", 0)
            assert app.filter_var.get() == "All layers" and app.protocol_filter_var.get() == "All protocols"
            assert app.protocol_var.get() == "Remote shell"
            checks.append("removing used entries requires explicit reassignment; cancelling and applying preserve all notes")

            # The two blocks overlap only if the upper layer is removed into the lower one.
            conflicting = Atlas((Node("a", "A", 1, "Other", 0), Node("b", "B", 2, "Other", 0)))
            dialog = DesignEditor(root, conflicting, app.apply_design)
            dialog.layers.select(2)
            assert not dialog.layers.remove(1)
            assert "overlaps" in dialog.error.get() and dialog.working == conflicting
            dialog.cancel()
            checks.append("layer-removal collision is rejected atomically in the design editor")

            custom_export = Path(folder) / "custom-export.json"
            with patch("atlas.ui.filedialog.asksaveasfilename", return_value=str(custom_export)):
                app.export_json()
            exported = read_atlas(custom_export)
            assert exported == app.document
            with patch("atlas.ui.messagebox.askyesno", return_value=True):
                assert app.new_empty_atlas()
            assert app.document == Atlas(design=exported.design)
            assert read_atlas(path.with_suffix(".json.bak")) == exported
            with patch("atlas.ui.filedialog.askopenfilename", return_value=str(custom_export)), \
                 patch("atlas.ui.messagebox.askyesno", return_value=True):
                app.import_json()
            assert app.document == exported
            checks.append("JSON export/import retains the design; Empty atlas preserves it and backs up every block")

            minimal_design = Design((Layer("custom-only", "My layer", "#65b6a1"),),
                                    (Protocol("custom-only", "My protocol"),), "Layer", "Group", "coordinates")
            minimal = Path(folder) / "minimal.json"
            write_atlas(minimal, Atlas(design=minimal_design))
            with patch("atlas.ui.filedialog.askopenfilename", return_value=str(minimal)), \
                 patch("atlas.ui.messagebox.askyesno", return_value=True):
                app.import_json()
            assert app.layer_var.get() == "1  My layer" and app.protocol_var.get() == "My protocol"
            app.name_var.set("First custom-only block")
            assert app.save_node()
            assert app.document.nodes[0].coordinate == ("custom-only", "custom-only", 2)
            pump(root)
            assert app.scene.design == minimal_design and len(app.scene._axis_actors) == 3, (app.scene.design, app.scene.mode, len(app.scene._axis_actors))
            checks.append("a single custom layer and protocol work without any OSI preset entries")

            check_clear_lists(root, app, path, checks)
            check_immediate_protocol_clear(root, app, path, checks)
            check_node_view(root, app, path, checks)
            check_node_moves(root, app, path, checks)
            check_connections(root, app, path, pump, checks)
            check_template_browser(root, app, path, pump, checks)
            check_block_view(root, app, path, pump, checks)
            check_updates(root, app, path, pump, checks)
            check_clusters(root, app, path, pump, checks)
            check_information(root, app, path, pump, checks)

            root.geometry("1020x780")
            pump(root)
            assert app.notes.winfo_height() >= 80, f"Notes area is only {app.notes.winfo_height()}px high"
            assert app.save_button.winfo_rootx() + app.save_button.winfo_width() < root.winfo_rootx() + root.winfo_width()
            assert app.protocol_filter_box.winfo_rootx() + app.protocol_filter_box.winfo_width() < app.canvas.winfo_rootx() + app.canvas.winfo_width()
            assert app.empty_button.winfo_ismapped()
            assert app.empty_button.winfo_rootx() + app.empty_button.winfo_width() < root.winfo_rootx() + root.winfo_width()
            label_x = [app.scale_widget.coords(item)[0] for item in app.scale_widget.find_withtag("label")]
            assert max(b - a for a, b in zip(label_x, label_x[1:])) - min(b - a for a, b in zip(label_x, label_x[1:])) < .01
            checks.append("minimum-window layout remains usable")
            assert not errors, errors
            checks.append("no Tk callback errors")
            closing_node = app.selected
            app.name_var.set("Saved on close")
            with patch("atlas.ui.messagebox.askyesnocancel", return_value=None):
                assert not app.close()
            with patch("atlas.ui.messagebox.askyesnocancel", return_value=True):
                assert app.close()
            assert read_atlas(path).get(closing_node).name == "Saved on close"
            checks.append("close cancel and save-on-close")
        finally:
            if not app._closed:
                app.shutdown()
    report = json.dumps({"passed": len(checks), "checks": checks}, indent=2) + "\n"
    if report_path:
        report_path.write_text(report, encoding="utf-8")
    print(report)


def capture_preview(destination, *, design_editor=False, nodes_view=False):
    """Optional screenshot of the actual UI; Pillow is only needed for capture."""
    from PIL import ImageGrab

    example = "custom_design_atlas.json" if design_editor else "nodes_view_atlas.json" if nodes_view else "architecture_atlas.json"
    doc = read_atlas(Path(__file__).resolve().parents[1] / "examples" / example)
    with TemporaryDirectory() as folder:
        root = tk.Tk()
        app = AtlasApp(root, Path(folder) / "preview.json", doc)
        try:
            root.geometry("1300x860+30+30")
            if nodes_view:
                app.set_view_mode("nodes")
            app.scene.elevation = pi / 7 if nodes_view else pi / 4 if design_editor else 24 * pi / 180
            app.scene.target = [0.0, 0.0, 0.0] if design_editor or nodes_view else [-.196, .196, -.621]
            app.scene.scale = 5.5 if nodes_view else 3.0 if design_editor else 4.56
            app.scene._apply_camera()
            app.select_node("control" if design_editor else "orbit-2-3" if nodes_view else "authentication")
            app._set_status("Nodes view / 42 editable example notes" if nodes_view else "Web application architecture / 5 layers / 15 editable concepts")
            app.request_render()
            pump(root, 12)
            capture_widget = root
            if design_editor:
                dialog = DesignEditor(root, doc, app.apply_design)
                dialog.geometry("720x690+180+70")
                dialog.notebook.select(0)
                pump(root, 8)
                capture_widget = dialog
            if sys.platform == "win32":
                # Capture only this window, even when another app covers it.
                ImageGrab.grab(window=capture_widget.winfo_id()).save(destination)
            else:
                x, y = capture_widget.winfo_rootx(), capture_widget.winfo_rooty()
                ImageGrab.grab(bbox=(x, y, x + capture_widget.winfo_width(), y + capture_widget.winfo_height())).save(destination)
        finally:
            app.shutdown()


def capture_template(destination, key, *, library=False):
    """Capture a built-in template using the application's real renderer."""
    from PIL import ImageGrab

    template = find_template(key)
    document = example_atlas() if library else template.atlas
    with TemporaryDirectory() as folder:
        root = tk.Tk()
        app = AtlasApp(root, Path(folder) / "template-preview.json", document)
        try:
            root.geometry("1300x860+30+30")
            pump(root, 4)
            if library:
                app.open_templates()
                app._show_template(template)
            else:
                app.set_view_mode("nodes")
                app.labels_var.set(True)
                app.connections_var.set(True)
                app._connections_changed()
                selected = template.atlas.nodes[min(len(template.atlas.nodes) - 1, len(template.atlas.nodes) // 2)]
                app.select_node(selected.id)
                app._set_status(f"Template  /  {template.name}  /  fully editable")
            app.scene.yaw = 135 * pi / 180
            app.scene.elevation = 19 * pi / 180
            app.scene.scale = max(4.8, len(template.atlas.design.layers) * .62)
            app.scene.target = [0.0, 0.0, 0.0]
            app.scene._apply_camera()
            app.request_render()
            pump(root, 12)
            destination.parent.mkdir(parents=True, exist_ok=True)
            x, y = root.winfo_rootx(), root.winfo_rooty()
            ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height())).save(destination)
        finally:
            app.shutdown()


def capture_template_gallery(directory):
    capture_template(directory / "template-library.png", "python", library=True)
    capture_template(directory / "python-template.png", "python")
    capture_template(directory / "solar-system-template.png", "solar-system")


def check_templates_only():
    """Run the template workflow without the focus-sensitive placement checks."""
    with TemporaryDirectory() as folder:
        path = Path(folder) / "atlas.json"
        document = example_atlas()
        write_atlas(path, document, backup=False)
        root = tk.Tk()
        app = AtlasApp(root, path, document)
        checks = []
        errors = []
        root.report_callback_exception = lambda *error: errors.append(error)
        try:
            pump(root, 12)
            check_template_browser(root, app, path, pump, checks)
            assert not errors, errors
        finally:
            if not app._closed:
                app.shutdown()
    print(json.dumps({"passed": len(checks), "checks": checks}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Save the JSON test report.")
    parser.add_argument("--preview", type=Path, help="Capture an example UI screenshot (requires Pillow).")
    parser.add_argument("--design-preview", type=Path, help="Capture the design editor (requires Pillow).")
    parser.add_argument("--nodes-preview", type=Path, help="Capture the actual Nodes view (requires Pillow).")
    parser.add_argument("--templates-only", action="store_true", help="Run only the template browser workflow checks.")
    parser.add_argument("--template-gallery", type=Path, help="Capture the template library, Python and Solar System views into a directory.")
    parser.add_argument("--screenshots-only", action="store_true", help="Capture the requested previews without running workflow checks.")
    args = parser.parse_args()
    if args.screenshots_only and not any((args.preview, args.design_preview, args.nodes_preview, args.template_gallery)):
        parser.error("--screenshots-only requires a preview or template gallery destination")
    if not args.screenshots_only:
        if args.templates_only:
            check_templates_only()
        else:
            main(args.report)
    if args.preview:
        capture_preview(args.preview)
    if args.design_preview:
        capture_preview(args.design_preview, design_editor=True)
    if args.nodes_preview:
        capture_preview(args.nodes_preview, nodes_view=True)
    if args.template_gallery:
        capture_template_gallery(args.template_gallery)
