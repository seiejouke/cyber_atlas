"""Exercise the real GUI and renderer. Run from the project root.

A graphical desktop is required. On a headless Linux test machine:
    xvfb-run -a python tests/smoke_ui.py
"""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from atlas.model import Atlas, example_atlas
from atlas.storage import read_atlas, write_atlas
from atlas.ui import AtlasApp


def pump(root, steps=5):
    for _ in range(steps):
        root.update()
        time.sleep(0.025)


def main():
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
            checks.append("initial render: 14 occupied meshes, no empty-cell actors")
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

            app.new_node()
            app.name_var.set("Smoke-test note")
            app.notes.insert("1.0", "A local test finding.")
            assert app.save_node()
            added = app.selected
            assert len(read_atlas(path).nodes) == 15
            app.layer_var.set("5  Session")
            app.protocol_var.set("Other")
            app.depth_var.set(0)
            assert app.save_node()
            assert read_atlas(path).get(added).coordinate == (5, "Other", 0)
            assert app.filter_var.get() == "All layers"
            checks.append("create, edit, move and automatic local save")

            before = read_atlas(path)
            app.layer_var.set("7  Application")
            app.protocol_var.set("SSH")
            app.depth_var.set(2)
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
            checks.append("coordinate collision prevention and unsaved-edit cancel/discard")

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
            legacy = Path(folder) / "legacy.json"
            legacy.write_text(json.dumps({"type": "cyber-knowledge-atlas", "version": 3,
                                         "nodes": [{**n.to_dict(), "id": int(n.id)} for n in doc.nodes]}))
            with patch("atlas.ui.filedialog.askopenfilename", return_value=str(legacy)), \
                 patch("atlas.ui.messagebox.askyesno", return_value=True):
                app.import_json()
            assert app.document == doc
            checks.append("JSON export and original HTML v3 import")

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

            root.geometry("1020x780")
            pump(root)
            assert app.notes.winfo_height() >= 50
            assert app.save_button.winfo_rootx() + app.save_button.winfo_width() < root.winfo_rootx() + root.winfo_width()
            checks.append("minimum-window layout remains usable")
            assert not errors, errors
            checks.append("no Tk callback errors")
            app.name_var.set("Saved on close")
            with patch("atlas.ui.messagebox.askyesnocancel", return_value=None):
                assert not app.close()
            with patch("atlas.ui.messagebox.askyesnocancel", return_value=True):
                assert app.close()
            assert read_atlas(path).nodes[0].name == "Saved on close"
            checks.append("close cancel and save-on-close")
        finally:
            if not app._closed:
                app.shutdown()
    print(json.dumps({"passed": len(checks), "checks": checks}, indent=2))


if __name__ == "__main__":
    main()
