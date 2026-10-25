"""Main-note heat, linear presets, persistent parent indicators and saved drafts."""
from dataclasses import replace
from unittest.mock import patch

from atlas.heat import DEFAULT_HEAT_PRESET, HEAT_PRESETS, heat_color
from atlas.model import Atlas, InformationEntry, Node, Subconcept
from atlas.storage import read_atlas


def check_information(root, app, path, pump, checks):
    parent = Node("heat-parent", "Firewall", 3, None, 1, "Original parent notes", slot=2, span=4)
    neighbor = Node("heat-neighbor", "Adjacent spatial note", 3, None, 1, slot=6)
    children = tuple(Subconcept(f"heat-child-{i}", parent.id, name, f"Original {name} notes", i*2)
                     for i, name in enumerate(("Next-generation firewall", "Packet filtering", "Stateful inspection", "Application proxy")))

    def entries(identity, count):
        return tuple(InformationEntry(f"{identity}-{i}", identity, f"Entry {i}", f"Explanation {i}") for i in range(count))

    manager, scene = app.information, app.scene
    assert manager.heat_range.get() == DEFAULT_HEAT_PRESET and scene.heat_ceiling == 16
    app._load_editor(None)
    legacy = Atlas((parent, neighbor), subconcepts=children[:3])
    assert app.apply_design(legacy)
    app.set_view_mode("nodes")
    app._load_editor(parent)
    manager.color_mode.set("Information heat")
    manager.change_color()
    pump(root)
    legacy_bytes = path.read_bytes()
    assert scene.heat_metrics[parent.id].blended == 4
    assert all(scene.heat_metrics[child.id].own == 1 for child in children[:3])
    assert not app.document.information_entries
    assert path.read_bytes() == legacy_bytes
    app.clusters.add()
    app.clusters.name.set("A new orbital")
    assert app.clusters.save()
    pump(root)
    assert scene.heat_metrics[parent.id].blended == 5
    assert scene.concept_color(parent.id, parent.layer) == heat_color(5)
    assert scene.heat_metrics[app.clusters.child_id].own == 1
    assert app.clusters.parent_note()
    checks.append("Existing notes count automatically; adding a saved subconcept warms itself and its parent without creating extra entry records")

    copy = InformationEntry("legacy-main-copy", parent.id, parent.name, parent.notes)
    assert app.apply_design(app.document.with_entry(copy))
    before_copy = path.read_bytes()
    assert manager.open() and scene.heat_metrics[parent.id].own == 1
    assert "1 main note + 0 additional entries" in manager.dialog_summary.cget("text")
    assert "[main-note copy]" in manager.listbox.get(0)
    assert path.read_bytes() == before_copy
    manager.listbox.selection_set(0)
    assert manager.select_entry()
    manager.body.insert("end", "\nA different observation")
    assert manager.save() and manager.close()
    assert scene.heat_metrics[parent.id].own == 2 and app.document.get(parent.id).notes == parent.notes
    checks.append("Old main-note copies stay saved and count once; the editor labels them and distinct edited information adds heat without rewriting the main note")

    information = entries(parent.id, 8) + entries(neighbor.id, 32)
    for child, count in zip(children, (4, 2, 10, 0)):
        information += entries(child.id, count)
    fixture = Atlas((parent, neighbor), subconcepts=children, information_entries=information)
    app._load_editor(None)
    assert app.apply_design(fixture)
    app.set_view_mode("nodes")
    app._load_editor(parent)
    app.information.color_mode.set("Information heat")
    app.information.color_box.event_generate("<<ComboboxSelected>>")
    pump(root)
    saved = path.read_bytes()
    scene = app.scene

    def color(identity):
        actor = scene.orbit_actors.get(identity) or scene.actors[identity][0]
        return tuple(round(channel * 255) for channel in actor.GetProperty().GetColor())

    def expected(value):
        hex_color = heat_color(value, scene.heat_ceiling)
        return tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5))

    assert scene.heat_active and scene.heat_metrics[parent.id].support == 20
    assert color(parent.id) == expected(29) and color(neighbor.id) == expected(33)
    assert scene.actors[parent.id][0].GetScale() == (1, 1, 1)
    assert scene.connection_pairs == ((neighbor.id, parent.id),)
    assert path.read_bytes() == saved
    checks.append("Heat totals include one main note, additional entries and direct-child information; spatial neighbors do not add heat or change sphere sizes")

    for label, ceiling in HEAT_PRESETS.items():
        manager.heat_range.set(label)
        manager.range_box.event_generate("<<ComboboxSelected>>")
        pump(root)
        assert scene.heat_ceiling == ceiling and color(parent.id) == expected(29)
        ticks = manager.legend.find_withtag("heat-tick")
        labels = manager.legend.find_withtag("heat-count")
        assert len(ticks) == ceiling
        assert [manager.legend.itemcget(item, "text") for item in labels] == list(map(str, range(1, ceiling+1)))
        positions = [manager.legend.coords(item)[0] for item in ticks]
        gaps = [b-a for a, b in zip(positions, positions[1:])]
        assert max(gaps) - min(gaps) < 1e-6
        assert path.read_bytes() == saved
    manager.heat_range.set(DEFAULT_HEAT_PRESET)
    manager.change_range()
    app._load_editor(neighbor)
    pump(root)
    assert app.canvas.find_withtag(f"suborbital-ring:{parent.id}")
    assert not app.canvas.find_withtag(f"suborbital-ring:{neighbor.id}")
    assert app.selected == neighbor.id
    assert app.canvas.type(app.canvas.find_withtag("node-halo")[0]) == "line"
    app._load_editor(parent)
    checks.append("Balanced is the default; all three presets have every integer count equally spaced and never modify saved atlas data")
    checks.append("Unselected parents retain neutral rings and child-count badges while childless nodes use distinct selection corner marks")

    app.filter_var.set(app._layer_displays[1])
    app._filter_changed()
    pump(root)
    assert scene.heat_metrics[parent.id].blended == 29
    assert not app.canvas.find_withtag(f"suborbital-ring:{parent.id}")
    app.filter_var.set("All layers")
    app._filter_changed()
    app.clusters.explore()
    pump(root)
    assert scene.focused_parent == parent.id and color(parent.id) == expected(29)
    assert color(children[1].id) == expected(3)
    assert len(app.canvas.find_withtag(f"suborbital-ring:{parent.id}")) == 1
    badges = app.canvas.find_withtag(f"suborbital-badge:{parent.id}")
    assert app.canvas.itemcget(badges[-1], "text") == "4"
    assert not app.canvas.find_withtag("support-arc")
    x, y, _ = scene.project(scene.node_anchor(parent))
    radius = .065 * scene.height / (2 * scene.scale) + 3
    for identity, box in app._label_hits:
        if identity == parent.id and box not in manager.indicator_boxes:
            assert box[2] < x-radius or box[0] > x+radius
    assert scene.orbit_actors[children[1].id].GetScale() == (.7, .7, .7)
    assert path.read_bytes() == saved
    scene.clear_orbit_focus()
    app.request_render()
    pump(root)
    assert color(parent.id) == expected(29)
    scene.collapse_orbit()
    app.request_render()
    pump(root)
    assert app.canvas.find_withtag(f"suborbital-ring:{parent.id}") and not scene.orbit_actors
    checks.append("Overview, focus and collapsed clusters retain total heat and the parent indicator; filters hide rings without changing counts")

    app.clusters.select_child(children[1].id)
    app.clusters.notes.insert("end", "\nUnsaved personal note")
    notes_draft = app.clusters.notes.get("1.0", "end-1c")
    manager = app.information
    assert manager.open() and manager.owner_id == children[1].id
    manager.title.set("A third observation")
    manager.body.insert("1.0", "Independent recorded information")
    assert manager.save()
    entry_id = manager.entry_id
    pump(root)
    assert scene.heat_metrics[children[1].id].own == 4 and scene.heat_metrics[parent.id].support == 21
    assert app.document.child(children[1].id) == children[1]
    assert app.clusters.notes.get("1.0", "end-1c") == notes_draft and app.clusters.dirty
    assert read_atlas(path).information_entries == app.document.information_entries
    checks.append("Child entries save independently, warm their parent by one and preserve unsaved main-note drafts")

    manager.body.insert("end", "\nAn edited explanation")
    assert manager.save() and manager.entry_id == entry_id
    assert scene.heat_metrics[children[1].id].own == 4
    manager.title.set("")
    assert not manager.save() and manager.dirty
    manager.title.set("Edited observation")
    before = app.document
    before_bytes = path.read_bytes()
    with patch("atlas.ui.write_atlas", side_effect=OSError("Simulated entry save failure")), patch("atlas.ui.messagebox.showerror"):
        assert not manager.save()
    assert app.document == before and path.read_bytes() == before_bytes and manager.dirty
    with patch("atlas.information_ui.messagebox.askyesnocancel", return_value=None):
        assert not manager.close() and not app.close()
        assert not app.select_node(neighbor.id)
    assert manager.dialog is not None and manager.title.get() == "Edited observation"
    with patch("atlas.information_ui.messagebox.askyesnocancel", return_value=False):
        assert manager.close()
    with patch("atlas.cluster_ui.messagebox.askyesnocancel", return_value=False):
        assert app.clusters.parent_note()
    assert app.document.child(children[1].id) == children[1]
    checks.append("Editing an entry keeps its count; validation, failed writes and Cancel preserve the complete information draft and saved atlas")

    app.clusters.select_child(children[3].id)
    assert manager.open()
    assert scene.heat_metrics[children[3].id].own == 1
    assert "1 main note + 0 additional entries" in manager.dialog_summary.cget("text")
    assert not hasattr(manager, "copy_button")
    manager.title.set("An extra observation")
    manager.body.insert("1.0", "An additional worked example")
    assert manager.save()
    assert app.document.child(children[3].id) == children[3]
    assert len(app.document.entries_for(children[3].id)) == 1
    assert manager.new()
    manager.title.set("An extra observation")
    manager.body.insert("1.0", "An additional worked example")
    assert not manager.save()
    assert len(app.document.entries_for(children[3].id)) == 1
    with patch("atlas.information_ui.messagebox.askyesnocancel", return_value=False):
        assert manager.close()
    assert app.clusters.parent_note()
    checks.append("Main notes count automatically and need no copy step; optional additional entries remain independent and reject duplicates")

    app.clusters.select_child(children[1].id)
    assert manager.open()
    manager.listbox.selection_set(manager.entry_ids.index(entry_id))
    assert manager.select_entry()
    with patch("atlas.information_ui.messagebox.askyesno", return_value=True):
        assert manager.delete()
    assert len(app.document.entries_for(children[1].id)) == 2
    assert manager.close() and app.clusters.parent_note()
    exported = path.with_name("information-export.json")
    before = app.document
    with patch("atlas.ui.filedialog.asksaveasfilename", return_value=str(exported)):
        app.export_json()
    assert read_atlas(exported) == before
    with patch("atlas.ui.filedialog.askopenfilename", return_value=str(exported)), patch("atlas.ui.messagebox.askyesno", return_value=True):
        app.import_json()
    assert app.document == before
    checks.append("Entry deletion updates counts without removing notes; JSON export and import preserve every entry ID, owner and body")

    app._load_editor(app.document.get(parent.id))
    app.clusters.explore()
    pump(root)
    original = app.document
    before_bytes = path.read_bytes()
    app.open_templates()
    pump(root)
    assert not manager.open()
    assert all(metric.own == 1 and metric.support == 0 for metric in scene.heat_metrics.values())
    assert not app.canvas.find_withtag("suborbital-ring")
    app.cancel_templates()
    pump(root)
    assert app.document == original and path.read_bytes() == before_bytes and scene.heat_active
    assert scene.heat_metrics[parent.id].own == 9
    checks.append("Read-only templates cannot edit entries; cancellation restores the original atlas and information metrics without writing")

    app.set_view_mode("blocks")
    pump(root)
    assert not scene.heat_active and scene.meshes[parent.id].center == scene.node_anchor(parent)
    app.set_view_mode("nodes")
    app.clusters.explore()
    root.geometry("1020x780")
    pump(root)
    assert app.notes.winfo_ismapped() and app.notes.winfo_height() >= 80, app.notes.winfo_height()
    assert manager.range_box.winfo_rootx() + manager.range_box.winfo_width() <= app.canvas.winfo_rootx() + app.canvas.winfo_width()
    manager.heat_range.set("C - Extended (1-32)")
    manager.change_range()
    pump(root)
    boxes = [manager.legend.bbox(item) for item in manager.legend.find_withtag("heat-count")]
    assert all(a[2] <= b[0] + 1 for a, b in zip(boxes, boxes[1:])), boxes
    manager.heat_range.set(DEFAULT_HEAT_PRESET)
    manager.change_range()
    assert app.information._headers[0][0].winfo_rootx() + app.information._headers[0][0].winfo_width() <= root.winfo_rootx() + root.winfo_width()
    assert manager.open()
    manager.dialog.geometry("640x480")
    pump(root)
    assert manager.body.winfo_height() >= 100
    assert manager.close()
    app.move_node()
    pump(root)
    assert app.notes.winfo_ismapped() and app.notes.winfo_height() >= 80
    assert not manager._headers[0][1].winfo_ismapped()
    app.move_node()
    manager.color_mode.set("Layer colors")
    manager.change_color()
    scene.collapse_orbit()
    app.request_render()
    pump(root)
    assert not scene.heat_active and not manager.legend.winfo_manager()
    assert path.read_bytes() == before_bytes
    checks.append("Heat controls and information editors fit minimum windows; Blocks and layer colors preserve the existing geometry and saved entries")

    single = Atlas((parent, neighbor), subconcepts=(children[0],))
    app._load_editor(None)
    assert app.apply_design(single)
    app.set_view_mode("nodes")
    app._load_editor(parent)
    pump(root)
    assert app.canvas.find_withtag(f"suborbital-ring:{parent.id}")
    assert app.clusters.select_child(children[0].id)
    with patch("atlas.cluster_ui.messagebox.askyesno", return_value=True):
        assert app.clusters.delete()
    pump(root)
    assert not app.canvas.find_withtag("suborbital-ring")
    assert scene.heat_metrics[parent.id].blended == 1
    assert app.apply_design(single)
    pump(root)
    assert app.canvas.find_withtag(f"suborbital-ring:{parent.id}")
    app.set_view_mode("blocks")
    pump(root)
    assert not app.canvas.find_withtag("suborbital-ring")
    checks.append("Adding and removing the last subconcept immediately updates the parent ring and heat; Blocks never receives sphere overlays")
