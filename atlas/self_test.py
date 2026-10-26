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
        from .orientation import aligned_view, DEFAULT_YAW, DEFAULT_ELEVATION
        from .view_settings import navigation_collapsed
        from .label_layout import overlaps

        def settle_view():
            deadline = time.monotonic() + 4
            while app.compass._job is not None and time.monotonic() < deadline:
                pump()
            if app.compass._job is not None:
                raise AssertionError("Bundled compass animation did not finish")
            for _ in range(4):
                pump()

        unchanged = app.path.read_bytes(), app.history.store.revisions()
        view = app.scene.scale, tuple(app.scene.target), app.scene.focused_parent
        for axis in "XYZ":
            for sign in (1, -1):
                app.compass.activate(axis)
                settle_view()
                if aligned_view(app.scene.yaw, app.scene.elevation) != (axis, sign):
                    raise AssertionError(f"Bundled compass failed {axis} / {sign}")
        require((app.scene.scale, tuple(app.scene.target), app.scene.focused_parent) == view,
                "Bundled compass reaches all six signed axis views while preserving zoom, pan and cluster focus")
        app.compass.activate("home")
        settle_view()
        require((app.scene.yaw, app.scene.elevation) == (DEFAULT_YAW, DEFAULT_ELEVATION)
                and (app.path.read_bytes(), app.history.store.revisions()) == unchanged,
                "Compass Home restores the angled view without writing atlas data or revisions")
        nav = app.navigation
        was_collapsed = nav.collapsed
        nav.toggle()
        pump()
        require(navigation_collapsed(nav.settings_path) == nav.collapsed != was_collapsed
                and (app.scene.scale, tuple(app.scene.target), app.scene.focused_parent) == view,
                "Navigation retracts and saves its preference separately without changing the focused camera")
        if nav.collapsed:
            nav.toggle()
        nav.slider._choose(0)
        pump()
        require(nav.slider.selected == app.scene.layer_filter == parent.layer
                and app.filter_var.get() == app._layer_displays[parent.layer],
                "Bundled layer slider filters the atlas and synchronizes the dropdown")
        nav.all_button.invoke()
        settle_view()
        app.clusters.select_child(child.id)
        settle_view()
        child_box = app.label_manager.placements.get(f"nodes:{child.id}")
        require(child_box is not None and not overlaps(child_box, nav.reserved_box)
                and app._pick_at(round((child_box[0]+child_box[2])/2),
                                 round((child_box[1]+child_box[3])/2)) == child.id,
                "Bundled stable labels give the selected suborbital a clickable label outside the navigation panel")
        app.clusters.parent_note()
        if nav.collapsed != was_collapsed:
            nav.toggle()
        require(app.scene.layer_filter is None
                and (app.path.read_bytes(), app.history.store.revisions()) == unchanged,
                "Navigation and label interactions leave notes, suborbitals, information and history unchanged")
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
                "Format-11 export preserves entries, notes and positions; color changes never write atlas data")
        flows = app.flows
        app._load_editor(parent)
        original_metrics = app.scene.heat_metrics.copy()
        require(flows.open() and flows.add_step(parent) and flows.add_step(child) and flows.add_step(parent),
                "Flow editor adds existing nodes and suborbitals with separate identities for repeated concepts")
        flows.title.set("Bundled process guide")
        first, second, repeated = flows.draft.steps
        flows.select_step(first.id)
        flows.explanation.insert("1.0", "## Mechanism\nUse **the existing concept**.")
        flows.edge_label.set("Blocked")
        flows.edge_target.set("End flow")
        require(flows.connect() and flows.save() and read_atlas(app.path) == app.document
                and app.scene.heat_metrics == original_metrics,
                "Bundled flow saves labelled branches in format 11 without adding heat or duplicating concept notes")
        flows.set_mode("study")
        pump()
        require(app.scene.flow_actors and child.id in app.scene.flow_child_actors
                and all(not actor.GetPickable() for actors in app.scene.flow_actors.values() for actor in actors),
                "Bundled native flow arrows and referenced suborbitals render separately from spatial adjacency")
        flow_bytes, flow_revisions = app.path.read_bytes(), app.history.store.revisions()
        require(flows.next_button.instate(["disabled"]) and flows.reader.cget("state") == "disabled",
                "Structured study content is read-only and branch steps require a learner choice")
        edge = next(edge for edge in flows.run.choices if edge.target_id == second.id)
        flows.choice.set(edge.id)
        flows.choose_branch()
        require(flows.next() and flows.run.current == second.id
                and child.notes in flows.reader.get("1.0", "end"),
                "Manual flow traversal selects the original subconcept and reads its canonical note")
        flows.previous()
        require(flows.close() and app.scene.mode == "blocks" and not app.scene.flow_actors
                and app.path.read_bytes() == flow_bytes and app.history.store.revisions() == flow_revisions,
                "Leaving a bundled flow restores the atlas view without changing content or recording navigation history")
        history = app.history
        revisions = history.store.revisions()
        require(len(revisions) > 1 and history.store.load(revisions[0].id) == app.document,
                "Local SQLite history records full atlas revisions with the bundled runtime")
        saved_history_atlas = app.path.read_bytes()
        require(history.open(), "Read-only history browser opens with its own bundled 3D scene")
        pump()
        history.step(1)
        pump()
        require(history.notes.cget("state") == "disabled" and app.path.read_bytes() == saved_history_atlas
                and history.store.revisions() == revisions,
                "Browsing earlier saved states preserves the current atlas and creates no revisions")
        history.close()
        archive = app.path.parent / "history-self-test.zip"
        history.store.export(archive)
        import zipfile
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read("history.json"))
            require(len(manifest["revisions"]) == len(revisions) and "atlas.json" in bundle.namelist(),
                    "History ZIP export contains every revision and the current portable atlas")
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
