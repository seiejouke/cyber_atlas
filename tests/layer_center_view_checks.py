"""Real desktop checks for selecting, creating and preserving layer concepts."""
from pathlib import Path
import sys
from unittest.mock import patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.design_editor import DesignEditor
from atlas.model import Atlas, CENTER_DEPTH, Design, Layer, Node, Protocol
from atlas.storage import read_atlas


def check_layer_centers(root, app, path, pump, checks):
    design = Design((Layer("layer-base", "Foundations", "#65b6a1"),
                     Layer("layer-top", "Applications", "#edbb69")),
                    (Protocol("tagged", "Tagged"),))
    fresh = Atlas(design=design).with_layer_centers()
    app._load_editor(app.document.get(app.selected))
    assert app.apply_design(fresh)
    app.set_view_mode("nodes")
    app.reset_view()
    root.geometry("1300x860")
    pump(root)

    def click(x, y):
        app.canvas.event_generate("<ButtonPress-1>", x=round(x), y=round(y))
        app.canvas.event_generate("<ButtonRelease-1>", x=round(x), y=round(y))
        pump(root)

    def click_label(layer_id):
        boxes = [box for identity, box in app._axis_hits if identity == layer_id]
        assert boxes, (layer_id, app._axis_hits)
        x0, y0, x1, y1 = boxes[-1]
        click((x0 + x1) / 2, (y0 + y1) / 2)

    top = fresh.layer_center("layer-top")
    saved_bytes = path.read_bytes()
    click_label(top.layer)
    assert app.selected == top.id and app.name_var.get() == top.name and not app.dirty
    assert not app.scale_widget.enabled and not app.slot_slider.enabled
    assert app.move_button.cget("text") == "Edit layer" and path.read_bytes() == saved_bytes
    app.name_var.set("My application overview")
    app.notes.insert("1.0", "An editable overview of this layer.")
    with patch("atlas.ui.write_atlas", side_effect=OSError("simulated disk failure")), \
         patch("atlas.ui.messagebox.showerror"):
        assert not app.save_node()
    assert app.document == fresh and path.read_bytes() == saved_bytes and app.dirty
    assert app.save_node()
    top = app.document.get(top.id)
    assert top.notes and read_atlas(path).get(top.id) == top
    revisions = app.history.store.revisions()
    assert app.history.store.load(revisions[0].id).get(top.id) == top
    checks.append("layer labels select ordinary saved concepts; edits survive failed writes and save with the same identity into JSON and history")

    app.set_view_mode("blocks")
    pump(root)
    click_label(top.layer)
    assert app.selected == top.id and app.placement_state == "locked"
    app.begin_placement()
    assert app.placement_state == "locked"
    assert app.layer_box.instate(["disabled"]) and app.size_box.instate(["disabled"])

    def arrange_layer(dialog):
        assert dialog.layers.current == top.layer
        dialog.layers.name.set("Renamed category")
        assert dialog.layers.update_entry()
        dialog.layers.move(-1)
        assert dialog.apply()

    with patch.object(root, "wait_window", side_effect=arrange_layer):
        app.move_button.invoke()
    assert app.document.get(top.id) == top
    assert app.document.design.layers[0].id == top.layer
    assert app.document.design.layer(top.layer).name == "Renamed category"
    app.new_node()
    assert app.selected is None and app._layer_id() == top.layer and app.depth_var.get() == 0
    app._load_editor(top)
    checks.append("central concepts stay anchored in both views; Edit layer targets their category without changing their title or notes, and Add creates an outward concept")

    dialog = DesignEditor(root, app.document, app.apply_design)
    try:
        dialog.layers.add()
        new_id = dialog.layers.current
        dialog.layers.name.set("New subject")
        assert dialog.apply()
    finally:
        if dialog.winfo_exists():
            dialog.cancel()
    new_center = app.document.layer_center(new_id)
    assert new_center is not None and new_center.name == "New subject"
    assert new_center.id not in {node.id for node in fresh.nodes}
    assert app.document.get(top.id) == top
    saved_bytes = path.read_bytes()
    assert app.select_layer(new_id) and app.selected == new_center.id
    assert path.read_bytes() == saved_bytes
    checks.append("applying a newly named layer creates one saved, independently editable center and preserves existing center content")

    for apply in (False, True):
        dialog = DesignEditor(root, app.document, app.apply_design)
        try:
            dialog.layers.select(new_id)
            with patch.object(dialog, "wait_window") as reassignment:
                assert dialog.layers.remove()
            reassignment.assert_not_called()
            if apply:
                assert dialog.apply()
            else:
                dialog.cancel()
                assert path.read_bytes() == saved_bytes and app.document.get(new_center.id) == new_center
        finally:
            if dialog.winfo_exists():
                dialog.cancel()
    assert app.document.get(new_center.id) is None and app.document.get(top.id) == top
    checks.append("unused central placeholders leave with removed layers; Cancel preserves them and no user notes or references are discarded")

    with patch("atlas.ui.messagebox.askyesno", return_value=True):
        assert app.new_empty_atlas()
    assert not app.document.has_content and len(app.document.nodes) == len(app.document.design.layers)
    backup_bytes = path.with_suffix(".json.bak").read_bytes()
    revisions = app.history.store.revisions()
    with patch("atlas.ui.messagebox.askyesno") as confirmation:
        assert app.new_empty_atlas()
    confirmation.assert_not_called()
    assert path.with_suffix(".json.bak").read_bytes() == backup_bytes
    assert app.history.store.revisions() == revisions
    checks.append("empty-atlas reset retains editable centers, backs up user content, and preserves the backup and history when repeated")

    outer = Node("legacy-outer", "Existing radial note", "layer-base", "tagged", 0, "Keep me")
    legacy = Atlas((outer,), design)
    assert app.apply_design(legacy)
    app.set_view_mode("nodes")
    app.reset_view()
    pump(root)
    saved_bytes = path.read_bytes()
    revisions = app.history.store.revisions()
    x, y, _ = app.scene.project(app.scene.layer_anchor("layer-top"))
    click(x, y)
    assert app._layer_draft == "layer-top" and app.selected is None
    assert app.name_var.get() == "Applications" and not app.dirty
    assert path.read_bytes() == saved_bytes and app.history.store.revisions() == revisions
    app.open_templates()
    pump(root)
    assert not app.select_layer("layer-top") and not app.save_node()
    app.cancel_templates()
    assert app._layer_draft == "layer-top" and not app.dirty and not app.scale_widget.enabled
    app.notes.insert("1.0", "This older atlas now has a central explanation.")
    with patch("atlas.ui.messagebox.askyesnocancel", return_value=None):
        assert not app.select_layer("layer-base")
    assert app._layer_draft == "layer-top" and app.dirty
    app.set_view_mode("blocks")
    with patch("atlas.ui.write_atlas", side_effect=OSError("simulated disk failure")), \
         patch("atlas.ui.messagebox.showerror"):
        assert not app.save_node()
    assert app._layer_draft == "layer-top" and path.read_bytes() == saved_bytes
    assert app.save_node()
    top = app.document.layer_center("layer-top")
    assert top.notes and app.document.get(outer.id) == outer
    assert len(app.document.nodes) == 2 and read_atlas(path) == app.document
    assert read_atlas(path.with_suffix(".json.bak")) == legacy
    assert app.select_layer(top.layer) and app.document.layer_center(top.layer).id == top.id
    checks.append("legacy spine markers open named drafts without writes; template cancellation, view switches, unsaved-note cancellation and failed saves preserve the draft, and Save creates only one center")

    app.set_view_mode("nodes")
    app.protocol_filter_var.set("Tagged")
    app._filter_changed()
    pump(root)
    assert not app.scene.is_visible(top)
    click_label(top.layer)
    assert app.selected == top.id and app.scene.is_visible(top)
    checks.append("selecting a layer label reveals its central concept when a protocol filter hid it")

    partial = Node("partial", "Old split center", "layer-base", None, CENTER_DEPTH, "Original", span=2)
    assert app.apply_design(Atlas((partial,), design))
    saved_bytes = path.read_bytes()
    assert app.select_layer("layer-base") and app.selected == partial.id
    assert app.document.nodes == (partial,) and path.read_bytes() == saved_bytes
    checks.append("legacy split-center layouts remain intact and their layer labels open the existing note")

    assert app.apply_design(Atlas(design=design))
    app.new_node()
    app.depth_var.set(CENTER_DEPTH)
    app.name_var.set("A center created through the regular form")
    assert app.dirty
    with patch("atlas.ui.messagebox.askyesnocancel", return_value=True):
        assert app.select_layer("layer-top")
    center = app.document.layer_center("layer-top")
    assert center is not None and app.selected == center.id and app._layer_draft is None
    assert len(app.document.nodes) == 1 and not app.dirty
    checks.append("saving a regular center draft during a layer click selects the saved note instead of opening a duplicate draft")


if __name__ == "__main__":
    import argparse
    import json
    from tempfile import TemporaryDirectory
    import time
    import traceback
    import tkinter as tk

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    from atlas.storage import write_atlas
    from atlas.ui import AtlasApp

    checks, errors = [], []

    def pump(root, steps=6):
        for _ in range(steps):
            root.update()
            time.sleep(.025)

    with TemporaryDirectory() as folder:
        path = Path(folder) / "atlas.json"
        document = Atlas().with_layer_centers()
        write_atlas(path, document, backup=False)
        root = tk.Tk()
        def callback_error(*error):
            errors.append(str(error[1]))
            traceback.print_exception(*error)

        root.report_callback_exception = callback_error
        app = AtlasApp(root, path, document, automatic_updates=False)
        try:
            pump(root)
            check_layer_centers(root, app, path, pump, checks)
            assert not errors, errors
        finally:
            app.shutdown()
    result = {"passed": len(checks), "checks": checks}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
