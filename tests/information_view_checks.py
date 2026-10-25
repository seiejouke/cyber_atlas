"""Real editor, color, support rim and persistence workflows."""
from dataclasses import replace
from unittest.mock import patch

from atlas.heat import heat_color
from atlas.model import Atlas, InformationEntry, Node, Subconcept
from atlas.storage import read_atlas


def check_information(root, app, path, pump, checks):
    parent = Node("heat-parent", "Firewall", 3, None, 1, "Original parent notes", slot=2, span=4)
    neighbor = Node("heat-neighbor", "Adjacent spatial note", 3, None, 1, slot=6)
    children = tuple(Subconcept(f"heat-child-{i}", parent.id, name, f"Original {name} notes", i*2)
                     for i, name in enumerate(("Next-generation firewall", "Packet filtering", "Stateful inspection", "Application proxy")))

    def entries(identity, count):
        return tuple(InformationEntry(f"{identity}-{i}", identity, f"Entry {i}", f"Explanation {i}") for i in range(count))

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
        hex_color = heat_color(value)
        return tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5))

    assert scene.heat_active and scene.heat_metrics[parent.id].support == 2.5
    assert color(parent.id) == expected(10.5) and color(neighbor.id) == expected(32)
    assert scene.actors[parent.id][0].GetScale() == (1, 1, 1)
    assert scene.connection_pairs == ((neighbor.id, parent.id),)
    assert path.read_bytes() == saved
    checks.append("Heat overview uses own entries plus capped direct-child support; adjacent spatial notes do not add heat or change node sizes")

    app.filter_var.set(app._layer_displays[1])
    app._filter_changed()
    pump(root)
    assert scene.heat_metrics[parent.id].blended == 10.5
    app.filter_var.set("All layers")
    app._filter_changed()
    app.clusters.explore()
    pump(root)
    assert scene.focused_parent == parent.id and color(parent.id) == expected(8)
    assert color(children[1].id) == expected(2)
    arcs = app.canvas.find_withtag("support-arc")
    assert len(arcs) == 1 and float(app.canvas.itemcget(arcs[0], "extent")) == -225
    x, y, _ = scene.project(scene.node_anchor(parent))
    radius = .065 * scene.height / (2 * scene.scale) + 3
    for identity, box in app._label_hits:
        if identity == parent.id:
            assert box[2] < x-radius or box[0] > x+radius
    assert scene.orbit_actors[children[1].id].GetScale() == (.7, .7, .7)
    assert path.read_bytes() == saved
    scene.clear_orbit_focus()
    app.request_render()
    pump(root)
    assert color(parent.id) == expected(10.5) and not app.canvas.find_withtag("support-arc")
    checks.append("Cluster focus switches to own-information fills and the exact support arc; filtering and Show atlas retain fixed counts and colors")

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
    assert scene.heat_metrics[children[1].id].own == 3 and scene.heat_metrics[parent.id].support == 2.75
    assert app.document.child(children[1].id) == children[1]
    assert app.clusters.notes.get("1.0", "end-1c") == notes_draft and app.clusters.dirty
    assert read_atlas(path).information_entries == app.document.information_entries
    checks.append("Child entries save independently, update bounded parent support and preserve unsaved personal-note drafts")

    manager.body.insert("end", "\nAn edited explanation")
    assert manager.save() and manager.entry_id == entry_id
    assert scene.heat_metrics[children[1].id].own == 3
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
    assert manager.open() and manager.use_notes()
    assert manager.save()
    assert app.document.child(children[3].id) == children[3]
    assert len(app.document.entries_for(children[3].id)) == 1
    assert manager.use_notes() and not manager.save()
    assert len(app.document.entries_for(children[3].id)) == 1
    with patch("atlas.information_ui.messagebox.askyesnocancel", return_value=False):
        assert manager.close()
    assert app.clusters.parent_note()
    checks.append("Existing notes can explicitly become one recorded entry without changing their original text; identical copies cannot inflate counts")

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
    assert not any(metric.own for metric in scene.heat_metrics.values())
    app.cancel_templates()
    pump(root)
    assert app.document == original and path.read_bytes() == before_bytes and scene.heat_active
    assert scene.heat_metrics[parent.id].own == 8
    checks.append("Read-only templates cannot edit entries; cancellation restores the original atlas and information metrics without writing")

    app.set_view_mode("blocks")
    pump(root)
    assert not scene.heat_active and scene.meshes[parent.id].center == scene.node_anchor(parent)
    app.set_view_mode("nodes")
    app.clusters.explore()
    root.geometry("1020x780")
    pump(root)
    assert app.notes.winfo_height() >= 80, app.notes.winfo_height()
    assert app.information._headers[0][0].winfo_rootx() + app.information._headers[0][0].winfo_width() <= root.winfo_rootx() + root.winfo_width()
    assert manager.open()
    manager.dialog.geometry("640x480")
    pump(root)
    assert manager.body.winfo_height() >= 100
    assert manager.close()
    app.move_node()
    pump(root)
    assert app.notes.winfo_height() >= 80 and not manager._headers[0][1].winfo_ismapped()
    app.move_node()
    manager.color_mode.set("Layer colors")
    manager.change_color()
    scene.collapse_orbit()
    app.request_render()
    pump(root)
    assert not scene.heat_active and not manager.legend.winfo_manager()
    assert path.read_bytes() == before_bytes
    checks.append("Heat controls and information editors fit minimum windows; Blocks and layer colors preserve the existing geometry and saved entries")
