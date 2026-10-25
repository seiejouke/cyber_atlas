"""Actual Tk controls, VTK picking and persistence for local clusters."""
from dataclasses import replace
from unittest.mock import patch

from atlas.geometry import node_position
from atlas.model import Atlas, Node, Subconcept
from atlas.orbit_scene import orbit_position
from atlas.storage import read_atlas


def check_clusters(root, app, path, pump, checks):
    parent = Node('cluster-parent', 'Firewall', 3, 'IPv4', 0, 'Parent notes', slot=0)
    neighbor = Node('cluster-neighbor', 'Neighbor', 3, None, 0, slot=1)
    above = Node('cluster-above', 'Another layer', 4, None, 0)
    fixture = Atlas((parent, neighbor, above))
    app._load_editor(app.document.nodes[0] if app.document.nodes else None)
    assert app.apply_design(fixture)
    app._load_editor(parent)
    app.set_view_mode('nodes')
    manager = app.clusters
    root.geometry('1300x860')
    pump(root)
    original = path.read_bytes()
    assert manager.add() and manager.editing and manager.child_id is None
    assert app.document == fixture and path.read_bytes() == original
    assert app.scene.focused_parent == parent.id
    manager.name.set('Stateful inspection')
    manager.notes.insert('1.0', 'Independent child notes.')
    assert manager.save()
    first = app.document.child(manager.child_id)
    assert first.parent_id == parent.id and first.orbit_slot == 0
    assert app.document.get(parent.id) == parent and read_atlas(path) == app.document
    first_position = orbit_position(parent, first.orbit_slot, app.document.design)
    assert manager.add()
    manager.name.set('Packet filtering')
    manager.notes.insert('1.0', 'Different notes for another type.')
    assert manager.save()
    second = app.document.child(manager.child_id)
    assert second.orbit_slot == 2 and app.document.child(first.id) == first
    assert orbit_position(parent, first.orbit_slot, app.document.design) == first_position
    checks.append('Orbital children have independent notes and stable free local slots; adding them preserves every grid node and reservation')

    assert manager.parent_note()
    pump(root)
    x, y, _ = app.scene.project(first_position)
    assert app.scene.pick(x, y) == first.id
    app.canvas.event_generate('<ButtonPress-1>', x=round(x), y=round(y))
    app.canvas.event_generate('<ButtonRelease-1>', x=round(x), y=round(y))
    pump(root)
    assert manager.child_id == first.id and manager.notes.get('1.0', 'end-1c') == first.notes
    manager.notes.insert('end', '\nUnsaved draft.')
    with patch('atlas.cluster_ui.messagebox.askyesnocancel', return_value=None):
        assert not app.select_node(above.id)
    assert manager.child_id == first.id and manager.dirty
    with patch('atlas.ui.write_atlas', side_effect=OSError('Test write failure')), \
         patch('atlas.ui.messagebox.showerror'), patch('atlas.cluster_ui.messagebox.askyesnocancel', return_value=True):
        assert not app.select_node(above.id)
    assert manager.dirty and app.document.child(first.id) == first
    assert manager.save()
    first = app.document.child(first.id)
    checks.append('Picking an orbit sphere opens its own notes; Cancel and failed saves preserve the child draft and prevent navigation')

    manager.move()
    manager.slot.set(f'{second.orbit_slot+1:02d}')
    assert manager.save_button.instate(['disabled']) and not manager.save()
    assert app.document.child(first.id).orbit_slot == first.orbit_slot
    manager.notes.insert('end', '\nMove draft text.')
    app._escape()
    assert not manager.moving and manager.slot.get() == f'{first.orbit_slot+1:02d}'
    assert manager.notes.get('1.0', 'end-1c').endswith('Move draft text.')
    manager.move()
    manager.slot.set('05')
    assert manager.save()
    first = app.document.child(first.id)
    assert first.orbit_slot == 4
    assert app.document.child(second.id) == second
    checks.append('Orbit moves reject occupied slots; Escape restores the saved position while keeping text; Save changes only the chosen child')

    app.set_view_mode('blocks')
    pump(root)
    assert manager.editing and not app.scene.orbit_actors
    assert manager.notes.get('1.0', 'end-1c') == first.notes
    assert manager.parent_note()
    pump(root)
    assert manager.list_frame.winfo_ismapped() and manager.child_list.size() == 2
    assert set(app.scene.actors) == {parent.id, neighbor.id, above.id}
    manager.child_list.selection_set(1)
    manager.child_list.event_generate('<<ListboxSelect>>')
    pump(root)
    assert manager.editing and manager.child_id in (first.id, second.id)
    manager.explore()
    pump(root)
    assert app.scene.mode == 'nodes' and len(app.scene.orbit_actors) == 2
    checks.append('Blocks keeps the parent footprint and selectable child list; switching views preserves child notes and Explore restores the Nodes orbit')

    assert manager.parent_note()
    children = app.document.subconcepts
    assert app.move_node()
    app.layer_var.set(app._layer_displays[4])
    app.depth_var.set(1)
    app.slot_var.set('05')
    assert app.save_node()
    moved = app.document.get(parent.id)
    assert app.document.subconcepts == children
    px, py, pz = node_position(moved)
    for child in children:
        x, y, z = orbit_position(moved, child.orbit_slot, app.document.design)
        assert z == pz and abs((x-px)**2 + (y-py)**2 - .36**2) < 1e-10
    app.filter_var.set(app._layer_displays[3])
    app._filter_changed()
    pump(root)
    assert not app.scene.orbit_actors and app.scene.focused_parent is None
    app.filter_var.set('All layers')
    app._filter_changed()
    app.protocol_filter_var.set(app._no_protocol)
    app._filter_changed()
    assert not app.scene.orbit_actors
    app.protocol_filter_var.set(app._all_protocols)
    app._filter_changed()
    checks.append('Parent moves carry the whole orbit without changing child records; layer and protocol filters apply to the complete cluster')

    manager.explore()
    pump(root)
    assert not app.scene.actors[neighbor.id][0].GetVisibility()
    assert app.scene.actors[parent.id][0].GetVisibility()
    manager.toggle_focus()
    pump(root)
    assert app.scene.actors[neighbor.id][0].GetVisibility()
    assert app.document.subconcepts == children
    manager.toggle_expand()
    pump(root)
    assert not app.scene.orbit_actors
    checks.append('Focus hides unrelated nodes without moving them; Show atlas and Collapse restore the normal view without writing')

    export = path.parent / 'clusters-export.json'
    with patch('atlas.ui.filedialog.asksaveasfilename', return_value=str(export)):
        app.export_json()
    assert read_atlas(export) == app.document
    assert manager.select_child(first.id)
    with patch('atlas.cluster_ui.messagebox.askyesno', return_value=True):
        assert manager.delete()
    assert app.document.child(first.id) is None and app.document.child(second.id) == second
    with patch('atlas.ui.filedialog.askopenfilename', return_value=str(export)), patch('atlas.ui.messagebox.askyesno', return_value=True):
        app.import_json()
    assert app.document == read_atlas(export)
    app._load_editor(app.document.get(parent.id))
    before = app.document
    app.open_templates()
    pump(root)
    app.cancel_templates()
    assert app.document == before and read_atlas(path) == before
    checks.append('JSON export/import, child deletion and template previews preserve cluster identities, parent links and independent note contents')

    root.geometry('1020x780')
    pump(root)
    assert app.notes.winfo_height() >= 80
    assert manager.add_button.winfo_rootx() + manager.add_button.winfo_width() <= app.canvas.winfo_rootx() + app.canvas.winfo_width()
    assert manager.select_child(first.id)
    pump(root)
    assert manager.notes.winfo_height() >= 80
    assert manager.save_button.winfo_rootx() + manager.save_button.winfo_width() < root.winfo_rootx() + root.winfo_width()
    assert manager.parent_note()
    with patch('atlas.ui.messagebox.askyesno', return_value=False):
        assert not app.delete_node()
    assert app.document == before
    with patch('atlas.ui.messagebox.askyesno', return_value=True):
        assert app.delete_node()
    assert not app.document.subconcepts and app.document.get(neighbor.id) is not None
    assert read_atlas(path.with_suffix('.json.bak')) == before
    checks.append('Cluster editors and controls fit the minimum window; parent deletion requires confirmation and backs up all child notes')
