"""An isolated check run by the packaged executable, using its bundled runtime."""
from __future__ import annotations

from dataclasses import replace
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
        require(not app.scene.connections and not app.scene.connection_pairs,
                "Separated footprints have no spatial edges or automatic layer-marker spokes")
        app.scene.set_preview(replace(moving, id="preview", slot=5))
        adjacent_preview = app.scene.connection_pairs == (("blocker", "preview"),)
        app.scene.set_preview(None)
        require(adjacent_preview and not app.scene.connection_pairs,
                "Only edge-sharing move previews connect; cancellation restores the isolated graph")
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
        parent = app.document.get(app.selected)
        require(app.clusters.add(), "Bundled cluster editor opens for an existing parent")
        app.clusters.name.set("Bundled subconcept")
        app.clusters.notes.insert("1.0", "Independent bundled child notes")
        require(app.clusters.save() and read_atlas(app.path) == app.document
                and app.document.get(parent.id) == parent,
                "Orbital child notes save independently without changing the parent footprint")
        child = app.document.child(app.clusters.child_id)
        app.clusters.explore()
        pump()
        from .geometry import orbit_position
        x, y, _ = app.scene.project(orbit_position(parent, child.orbit_slot, app.document.design))
        require(app.scene.pick(x, y) == child.id and app.select_node(child.id),
                "Bundled VTK renders and selects an orbital child with its own editor")
        app.set_view_mode("blocks")
        app.clusters.parent_note()
        pump()
        require(not app.scene.orbit_actors and app.clusters.child_list.size() == 1,
                "Blocks retains its parent mesh and exposes the saved subconcept list")
        app.set_view_mode("nodes")
        manager = app.information
        require(manager.open() and app.scene.heat_metrics[parent.id].blended == 2
                and app.scene.heat_metrics[child.id].own == 1,
                "Existing main notes heat the parent and subconcept before any additional entry is created")
        manager.title.set("Bundled parent information")
        manager.body.insert("1.0", "One recorded explanation")
        if not manager.save() or not manager.close():
            raise AssertionError("Bundled parent entry could not save")
        app.clusters.select_child(child.id)
        if not manager.open():
            raise AssertionError("Bundled child entry editor could not open")
        manager.title.set("Bundled child information")
        manager.body.insert("1.0", "One supporting observation")
        require(manager.save() and app.scene.heat_metrics[parent.id].own == 2
                and app.scene.heat_metrics[parent.id].support == 2
                and app.scene.heat_metrics[child.id].own == 2
                and app.scene.heat_metrics[child.id].support == 0,
                "Main notes and additional entries heat each concept and its explicit parent")
        manager.body.insert("end", "\nAn edited observation")
        require(manager.save() and len(app.document.entries_for(child.id)) == 1,
                "Editing recorded information preserves its identity and entry count")
        manager.close()
        app.clusters.parent_note()
        app.scene.collapse_orbit()
        manager.color_mode.set("Information heat")
        manager.change_color()
        pump()
        from .heat import heat_color
        actor = app.scene.actors[parent.id][0]
        color = tuple(round(channel * 255) for channel in actor.GetProperty().GetColor())
        expected = heat_color(4)
        require(app.scene.heat_active and color == tuple(int(expected[i:i+2], 16) for i in (1, 3, 5))
                and actor.GetScale() == (1, 1, 1),
                "Bundled heat overview automatically counts main notes without resizing spheres")
        ticks = manager.legend.find_withtag("heat-tick")
        positions = [manager.legend.coords(item)[0] for item in ticks]
        gaps = [b-a for a, b in zip(positions, positions[1:])]
        require(app.scene.heat_ceiling == 16 and len(ticks) == 16 and max(gaps)-min(gaps) < 1e-6
                and app.canvas.find_withtag(f"suborbital-ring:{parent.id}"),
                "Balanced defaults to sixteen equally spaced counts; collapsed parents keep their suborbital ring")
        app.clusters.explore()
        pump()
        rings = app.canvas.find_withtag(f"suborbital-ring:{parent.id}")
        require(app.scene.focused_parent == parent.id and len(rings) == 1
                and app.scene.concept_color(parent.id, parent.layer) == heat_color(4),
                "Focused clusters retain total heat and a neutral parent ring with bundled VTK and Tk")
        saved_heat = app.path.read_bytes()
        write_atlas(export, app.document, backup=False)
        manager.color_mode.set("Layer colors")
        manager.change_color()
        app.set_view_mode("blocks")
        pump()
        reopened = read_atlas(export)
        require(reopened == app.document and len(reopened.information_entries) == 2
                and reopened.get(parent.id) == parent and reopened.child(child.id) == child
                and app.path.read_bytes() == saved_heat and not app.scene.heat_active,
                "Format-10 export preserves entries, notes and positions; color changes never write atlas data")
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
