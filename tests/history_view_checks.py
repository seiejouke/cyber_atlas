"""Read-only history scenes, restoration, drafts, exports and minimum layout."""
from dataclasses import replace
import json
from unittest.mock import patch
import zipfile

from atlas.model import Atlas, Node, Subconcept


def check_history(root, app, path, pump, checks):
    original = app.document
    history = app.history
    parent = Node("history-parent", "Multiplexing", 1, None, 0, "Earlier main note", slot=4)
    child = Subconcept("history-child", parent.id, "Time division", "Earlier independent suborbital note", 1)
    fixture = Atlas((parent,), subconcepts=(child,))
    app._load_editor(None)
    assert app._commit(fixture)
    earlier = history.store.revisions()[0]
    current_parent = replace(parent, notes="Latest main note", slot=7)
    current = fixture.without_child(child.id).with_node(current_parent)
    assert app._commit(current)
    app._load_editor(current_parent)
    app.set_view_mode("nodes")
    app.scene.collapse_orbit()
    pump(root)
    saved = path.read_bytes()
    backup = path.with_suffix(".json.bak").read_bytes()
    recorded = history.store.revisions()
    camera = (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target))
    try:
        assert history.open()
        pump(root)
        assert history.dialog is not None and history.scene is not app.scene
        assert history.document == current and history.notes.cget("state") == "disabled"
        assert history.change_text.cget("state") == "disabled"
        checks.append("History opens a separate read-only 3D scene with saved dates, summaries and inspectable notes")

        history.tree.selection_set(earlier.id)
        assert history.show_revision(earlier.id)
        pump(root)
        assert history.document == fixture and app.document == current
        child_index = next(i for i, c in enumerate(history.concepts) if c.id == child.id)
        history.concept_list.selection_clear(0, "end")
        history.concept_list.selection_set(child_index)
        history._selected_concept()
        assert child.notes in history.notes.get("1.0", "end")
        assert history.scene.expanded_parent == parent.id
        checks.append("Earlier revisions retain deleted suborbitals and their independent saved notes")

        history.heat_var.set(True)
        history.change_view()
        history.scene.rotate(5, 3)
        history._zoom(1)
        history.reset_button.invoke()
        history.step(-1)
        history.step(1)
        pump(root)
        assert path.read_bytes() == saved and path.with_suffix(".json.bak").read_bytes() == backup
        assert history.store.revisions() == recorded and app.document == current
        assert camera == (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target))
        assert history.scene.heat_ceiling == app.scene.heat_ceiling
        checks.append("Browsing, heat, camera controls and revision stepping never save, alter backups or change the active camera")

        archive = path.parent / "gui-history.zip"
        with patch("atlas.history_ui.filedialog.asksaveasfilename", return_value=str(archive)):
            assert history.export()
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read("history.json"))
            assert len(manifest["revisions"]) == len(recorded)
            assert json.loads(bundle.read("atlas.json")) == current.to_dict()
        assert history.store.revisions() == recorded
        checks.append("Export with history includes the current JSON, all saved JSON states and timestamped change metadata without creating a revision")

        with patch("atlas.history_ui.messagebox.askyesno", return_value=False):
            assert not history.restore()
        assert path.read_bytes() == saved and history.store.revisions() == recorded
        checks.append("Cancelling a restoration leaves the active atlas, browser and complete history unchanged")

        with patch("atlas.history_ui.messagebox.askyesno", return_value=True), \
                patch("atlas.ui.write_atlas", side_effect=OSError("Simulated restore write failure")), \
                patch("atlas.ui.messagebox.showerror"):
            assert not history.restore()
        assert history.dialog is not None and history.document == fixture and app.document == current
        assert path.read_bytes() == saved and history.store.revisions() == recorded
        checks.append("A failed restoration preserves the preview, current notes and recorded history")

        history.dialog.geometry("1020x700")
        pump(root)
        assert history.canvas.winfo_width() >= 150 and history.notes.winfo_width() >= 150
        assert history.notes.winfo_height() >= 150
        assert history.restore_button.winfo_rootx() + history.restore_button.winfo_width() < history.dialog.winfo_rootx() + history.dialog.winfo_width()
        assert history.export_button.winfo_rootx() + history.export_button.winfo_width() < history.dialog.winfo_rootx() + history.dialog.winfo_width()
        checks.append("History navigation, restoration, export, 3D preview and notes fit the minimum browser window")

        with patch("atlas.history_ui.messagebox.askyesno", return_value=True):
            assert history.restore()
        assert history.dialog is None and app.document == fixture
        restored = history.store.revisions()
        assert len(restored) == len(recorded) + 1 and restored[0].kind == "restore"
        assert {r.id for r in recorded} <= {r.id for r in restored}
        assert restored[0].parent_id == recorded[0].id
        checks.append("Restore appends a new revision and retains every later saved state, including deleted concepts")

        app.notes.insert("end", "\nUnsaved historical-browser draft")
        draft = app.notes.get("1.0", "end-1c")
        with patch("atlas.ui.messagebox.askyesnocancel", return_value=None):
            assert not history.open()
        assert history.dialog is None and app.notes.get("1.0", "end-1c") == draft
        assert history.store.revisions() == restored
        checks.append("Cancel before opening History preserves the complete unsaved main-note draft")

        with patch("atlas.ui.messagebox.askyesnocancel", return_value=False):
            assert history.open()
        pump(root)
        assert history.document == fixture and history.store.revisions() == restored
        history.close()
        assert not app.dirty and app.notes.get("1.0", "end-1c") == parent.notes
        checks.append("Discard opens the saved state without recording a draft; Return to present leaves the active file untouched")

        app.notes.insert("end", "\nSaved before browsing")
        with patch("atlas.ui.messagebox.askyesnocancel", return_value=True):
            assert history.open()
        pump(root)
        assert len(history.store.revisions()) == len(restored) + 1
        assert "Saved before browsing" in history.document.get(parent.id).notes
        history.close()
        checks.append("Save before opening History records the note once and exposes it in the newest revision")
    finally:
        history.close()
        app._load_editor(None)
        assert app._commit(original)
        app._load_editor(original.nodes[0] if original.nodes else None)
        app.request_render()
        pump(root)
