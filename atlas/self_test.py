"""An isolated check run by the packaged executable, using its bundled runtime."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time
import traceback

from .model import Atlas, Design, Layer, Node
from .runtime import LOGGER
from .storage import read_atlas, write_atlas


def run(app, report_path: Path) -> int:
    checks = []
    report = {"frozen": bool(getattr(sys, "frozen", False)), "executable": sys.executable,
              "python": sys.version.split()[0], "checks": checks}
    errors = []
    app.root.report_callback_exception = lambda *error: errors.append(str(error[1]))

    def pump():
        for _ in range(5):
            app.root.update()
            time.sleep(.03)

    def require(condition, message):
        if not condition:
            raise AssertionError(message)
        checks.append(message)

    try:
        pump()
        require(len(app.scene.actors) == len(app.document.nodes), "Startup renders every saved block")
        require(app._window_icon.width() == 256, "Bundled application icon loads")
        from . import updates
        require(not updates.UpdateSettings().automatic and not app.updates.settings.automatic,
                "Automatic update checks default to off in an isolated installation")
        app.updates.open(check=False)
        pump()
        require(app.updates.dialog is not None and not app.updates.busy,
                "Bundled Updates window opens without making a network request")
        app.updates.close_dialog()
        if sys.platform == "win32":
            require(Path(updates.__file__).with_name("update_helper.ps1").is_file(),
                    "Windows installer handoff helper is bundled")
        design = Design((Layer("test", "Packaged test", "#70cbd8"),), ())
        moving = Node("moving", "Bundled node", "test", None, 1, "Original notes", slot=1, span=2)
        blocker = Node("blocker", "Reserved slots", "test", None, 1, slot=7, span=2)
        fixture = Atlas((moving, blocker), design)
        require(app.apply_design(fixture), "Custom atlas saves with the bundled storage module")
        app._load_editor(moving)
        pump()
        require(app.scene.block_appearance == "outline"
                and app.scene.actors[moving.id][0].GetVisibility()
                and not app.scene.actors[blocker.id][0].GetVisibility(),
                "Outline renders the selected block solid and the other block as an outline")
        x, y, _ = app.scene.project(app.scene.meshes[blocker.id].label_anchor)
        require(app.scene.pick(x, y) == blocker.id,
                "Unfilled blocks remain selectable using bundled VTK picking")
        app.set_view_mode("nodes")
        pump()
        x, y, _ = app.scene.project(app.scene.node_anchor(moving))
        require(app.scene.pick(x, y) == moving.id, "VTK renders and picks a sphere using bundled native libraries")
        original = app.path.read_bytes()
        app.move_button.invoke()
        app.slot_var.set("07")
        require(not app.scene.preview_valid and app.save_button.instate(["disabled"]),
                "Move preview rejects overlapping footprints")
        app.depth_var.set(3)
        app.slot_var.set("15")
        app.notes.insert("end", "\nText survives cancelling a move.")
        pump()
        require(app.scene.preview_valid and app.scene.preview_actor is not None,
                "Move controls render a valid live preview")
        app._escape()
        require(app.depth_var.get() == moving.depth and app.slot_var.get() == "02"
                and app.notes.get("1.0", "end-1c").endswith("Text survives cancelling a move.")
                and app.path.read_bytes() == original, "Escape restores coordinates and keeps unsaved note text")
        app.move_button.invoke()
        app.depth_var.set(3)
        app.slot_var.set("15")
        require(app.save_node(), "Save move commits a valid position")
        saved = app.document.get(moving.id)
        require(saved.depth == 3 and saved.slot == 14 and saved.span == moving.span
                and read_atlas(app.path) == app.document,
                "Saved coordinates, identity, size and text roundtrip through JSON")
        app.set_view_mode("blocks")
        require(app.scene.meshes[saved.id].center == app.scene.node_anchor(saved),
                "Blocks uses the moved sphere's saved coordinates")
        require(read_atlas(app.path.with_suffix(".json.bak")) == fixture,
                "Saving preserves the previous atlas as a backup")
        export = app.path.with_name("export.json")
        write_atlas(export, app.document, backup=False)
        require(read_atlas(export) == app.document, "Portable JSON export reopens without Python on PATH")
        before = app.path.read_bytes()
        app.open_templates()
        pump()
        require(app._active_template is not None and app.scene.mode == "nodes" and not app.save_node(),
                "Built-in templates preview in read-only Nodes view")
        app.cancel_templates()
        require(app.path.read_bytes() == before and not app.dirty,
                "Template cancellation restores the atlas without writing")
        root = app.root
        root.geometry("1020x780")
        pump()
        require(app.notes.winfo_height() >= 80, "Editor fits the minimum window size")
        require(not errors, "No Tk callback errors")
        report["passed"] = True
    except Exception:
        report["passed"] = False
        report["error"] = traceback.format_exc()
        LOGGER.exception("Packaged self-test failed")
    finally:
        report["checks_passed"] = len(checks)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        app.shutdown()
    return 0 if report["passed"] else 1
