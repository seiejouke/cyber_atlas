"""Real saved-flow editing, process traversal and independent 3D overlays."""
from dataclasses import replace
from unittest.mock import patch

from atlas.heat import information_heat
from atlas.model import Atlas, Design, InformationEntry, Layer, Node, Subconcept
from atlas.storage import read_atlas
from atlas.study_text import concept_link


def check_flows(root, app, path, pump, checks):
    original, original_mode = app.document, app.scene.mode
    original_labels = app.labels_var.get()
    manager = app.flows
    design = Design((Layer('link', 'Link layer', '#70cbd8'), Layer('network', 'Network layer', '#91abe2')), ())
    interface = Node('flow-interface', 'Network interface', 'link', None, 0, '## Definition\nAn interface note.', slot=1)
    ip = Node('flow-ip', 'IPv4', 'network', None, 1, 'Read the destination.', slot=5)
    firewall = Node('flow-firewall', 'Firewall', 'network', None, 2, 'Apply the saved policy.', slot=8)
    route = Node('flow-route', 'Routing table', 'network', None, 3, 'Choose a route.', slot=12)
    outside = Node('flow-outside', 'Context reference', 'link', None, 3, 'Linked context.', slot=3)
    arp = Subconcept('flow-arp', interface.id, 'ARP', 'An independent child note.', 0)
    policy = Subconcept('flow-policy', firewall.id, 'Packet policy', 'A second parent child.', 3)
    policy_entry = InformationEntry('flow-policy-entry', firewall.id, 'Policy example', 'A separately saved information record.')
    fixture = Atlas((interface, ip, firewall, route, outside), design, (arp, policy), (policy_entry,))

    def settle():
        pump(root, 14)

    def camera():
        return app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target)

    try:
        app.scene.collapse_orbit()
        app._load_editor(None)
        assert app.apply_design(fixture)
        app.set_view_mode('nodes')
        app._load_editor(interface)
        app.information.color_mode.set('Information heat')
        app.information.change_color()
        app._visible_layer_changed('network')
        app.scene.target, app.scene.scale = [.2, -.1, 0], 3.4
        app.scene._apply_camera()
        app.notes.insert('end', '\nUNSAVED MAIN NOTE')
        draft = app._form_state()
        saved, revisions, view = path.read_bytes(), app.history.store.revisions(), camera()
        assert manager.open()
        settle()
        assert manager.panel.winfo_ismapped() and app.navigation.winfo_ismapped()
        assert app._form_state() == draft and app.dirty
        assert path.read_bytes() == saved and app.history.store.revisions() == revisions and camera() == view
        checks.append('Flows opens beside the existing compass and layer slider without writing data, moving the camera or discarding an unsaved main note')

        manager.pick(manager.add_step)
        settle()
        manager.picker.query.set('Network interface')
        assert manager.picker.matches[0] == interface
        manager.picker.accept()
        for concept in (ip, firewall, route, arp, interface, policy):
            assert manager.add_step(concept)
        manager.title.set('Packet forwarding')
        manager.introduction.insert('1.0', 'Study ' + concept_link(ip.id, 'IPv4') + '.')
        ids = [step.id for step in manager.draft.steps]
        assert len(ids) == len(set(ids)) == 7
        assert manager.draft.steps[0].concept_id == manager.draft.steps[5].concept_id == interface.id
        assert app.document == fixture and path.read_bytes() == saved
        checks.append('Search selects existing concepts and suborbitals; repeated occurrences have independent step IDs and stay in an unsaved draft')

        assert manager.select_step(ids[2])
        manager.step_title.set('Apply packet policy')
        manager.explanation.insert('1.0', '## Mechanism\nApply **the rules**. See ' + concept_link(outside.id, 'Context') + '.')
        manager.question.insert('1.0', 'What happens when the packet is blocked?')
        manager.connection_list.selection_set(0)
        manager._edge_selected()
        manager.edge_label.set('Allowed')
        assert manager.connect()
        manager.new_connection()
        manager.edge_label.set('Blocked')
        manager.edge_target.set('End flow')
        assert manager.connect()
        assert manager.save()
        settle()
        assert read_atlas(path) == app.document and len(app.document.flows) == 1
        assert app.document.nodes == fixture.nodes and app.document.subconcepts == fixture.subconcepts
        assert information_heat(app.document) == information_heat(fixture)
        assert not app.scene.connection_pairs
        checks.append('A saved flow retains conditional and terminal edges in JSON and history while preserving canonical notes, coordinates, adjacency and heat counts')

        manager.connection_list.selection_set(0)
        manager._edge_selected()
        manager.edge_label.set('Allowed route')
        manager.connection_list.selection_clear(0, 'end')
        manager.connection_list.selection_set(1)
        manager._edge_selected()
        assert any(edge.label == 'Allowed route' for edge in manager.draft.connections)
        assert manager.save()
        manager.connection_list.selection_clear(0, 'end')
        manager.connection_list.selection_set(0)
        manager._edge_selected()
        manager.edge_label.set('Allowed')
        assert manager.dirty and manager.save()
        assert any(edge.label == 'Allowed' for edge in app.document.flows[0].connections)
        manager.connection_list.selection_clear(0, 'end')
        manager.connection_list.selection_set(1)
        manager._edge_selected()
        removed_id = manager.edge_id
        manager.edge_label.set('Discard this pending edit')
        manager.remove_connection()
        assert all(edge.id != removed_id for edge in manager.draft.connections)
        manager.new_connection()
        manager.edge_label.set('Blocked')
        manager.edge_target.set('End flow')
        assert manager.connect() and manager.save()
        checks.append('Connection field edits survive selecting another edge, and Save flow applies pending branch edits without requiring an extra update click')

        manager.show_flow_layers()
        settle()
        assert set(app.scene.flow_child_actors) == {arp.id, policy.id}
        assert all(not actor.GetPickable() for actors in app.scene.flow_actors.values() for actor in actors)
        assert set(app.scene.flow_paths) == {edge.id for edge in manager.draft.connections}
        assert app.scene.actors[outside.id][0].GetProperty().GetOpacity() < .3
        assert app.scene.actors[interface.id][0].GetProperty().GetOpacity() == 1
        assert all(app.scene.actors[node.id][0].GetPosition() == app.scene.node_anchor(node) for node in fixture.nodes)
        checks.append('The independent native 3D arrow overlay crosses layers, dims unrelated concepts, exposes children of multiple parents and remains non-pickable')

        assert manager.set_mode('study')
        assert manager.select_step(ids[0])
        saved, revisions = path.read_bytes(), app.history.store.revisions()
        assert manager.next() and manager.run.current == ids[1]
        assert manager.next() and manager.run.current == ids[2]
        assert manager.next_button.instate(['disabled'])
        assert not manager.next()
        assert 'h2' in manager.reader.tag_names()
        assert manager.reader.cget('state') == 'disabled'
        assert 'Apply the saved policy.' in manager.reader.get('1.0', 'end')
        assert policy_entry.title in manager.reader.get('1.0', 'end')
        assert policy_entry.body in manager.reader.get('1.0', 'end')
        assert 'Mechanism' in manager.reader.get('1.0', 'end')
        assert manager.reader._links
        checks.append('Study renders canonical notes, headings, emphasis, recall prompts and concept links; multiple outgoing branches require an explicit learner choice')

        blocked = next(edge.id for edge in manager.run.choices if edge.label == 'Blocked')
        allowed = next(edge.id for edge in manager.run.choices if edge.label == 'Allowed')
        manager.choice.set(blocked)
        manager.choose_branch()
        assert manager.next_button.instate(['!disabled'])
        assert manager.next() and manager.run.finished
        manager.previous()
        assert manager.run.current == ids[2] and not manager.run.finished
        manager.choice.set(allowed)
        manager.choose_branch()
        assert manager.next() and manager.run.current == ids[3]
        manager.previous()
        assert manager.run.current == ids[2]
        assert path.read_bytes() == saved and app.history.store.revisions() == revisions
        checks.append('Allowed and Blocked branches highlight their own paths; terminal choices and Previous retrace the actual visit trail without saving revisions')

        manager.highlight_concept(outside.id)
        settle()
        assert manager.linked_concept == outside.id and app.scene.flow_concept_id == outside.id
        assert manager.link_return.winfo_ismapped() or manager.link_return.winfo_manager()
        manager.return_to_step()
        assert app.scene.flow_concept_id == firewall.id
        assert manager.select_step(ids[5])
        assert app.scene.flow_concept_id == interface.id
        assert not manager.edit_concept()  # Original inspector has an unsaved note.
        assert manager.close()
        settle()
        assert app._form_state() == draft and app.dirty and camera() == view
        assert app.scene.layer_filter == 'network' and not app.scene.flow_actors and not app.scene.flow_child_actors
        assert all(actors[0].GetProperty().GetOpacity() == 1 for actors in app.scene.actors.values())
        assert path.read_bytes() == saved and app.history.store.revisions() == revisions
        checks.append('Concept links highlight shared references; leaving a flow restores the exact camera, filters and dirty inspector and removes all temporary actors')

        app._load_editor(interface)
        assert manager.open()
        manager.show_flow_layers()
        assert manager.select_step(ids[0])
        assert manager.edit_concept()
        editor = manager.concept_editor
        editor.name.set('Renamed interface')
        editor.notes.insert('end', '\nCanonical edit from the study view.')
        assert editor.save()
        assert manager.select_step(ids[5])
        assert 'Canonical edit from the study view.' in manager.reader.get('1.0', 'end')
        assert app.document.get(interface.id).name == 'Renamed interface'
        assert manager.close()
        assert 'Canonical edit from the study view.' in app.notes.get('1.0', 'end') and not app.dirty
        checks.append('Edit concept note updates one canonical record, refreshes every occurrence and restores the updated standard editor on leaving the flow')

        app._visible_layer_changed(None)
        app.scene.expand_orbit(interface.id)
        app.scene.focus_orbit()
        focused_view, orbit_camera = camera(), app.scene._orbit_camera
        assert app.scene.focused_parent == interface.id
        assert manager.open()
        settle()
        assert app.scene.focused_parent is None and all(actors[0].GetVisibility() for actors in app.scene.actors.values())
        assert camera() == focused_view and manager.close()
        assert app.scene.focused_parent == interface.id and app.scene._orbit_camera == orbit_camera and camera() == focused_view
        app.scene.collapse_orbit()
        checks.append('Opening a flow from a focused orbit restores contextual visibility without moving the camera and restores the original orbit focus on return')

        app.set_view_mode('blocks')
        block_view = camera()
        assert manager.open()
        settle()
        assert app.scene.mode == 'nodes' and app.connections_check.instate(['!disabled'])
        assert manager.close() and app.scene.mode == 'blocks' and camera() == block_view
        assert app.connections_check.instate(['disabled'])
        app.set_view_mode('nodes')
        checks.append('Flows can be entered from Blocks and return to the original representation with connection controls and camera restored')

        assert app.select_node(policy.id)
        app.clusters.notes.insert('end', '\nUnsaved suborbital draft')
        child_draft = app.clusters.state()
        assert manager.open() and manager.close()
        assert app.clusters.editing and app.clusters.dirty and app.clusters.state() == child_draft
        app._load_editor(app.document.get(interface.id))
        checks.append('Unsaved suborbital note drafts remain intact when the study panel opens and closes')

        assert manager.open()
        assert manager.set_mode('edit')
        saved, revisions = path.read_bytes(), app.history.store.revisions()
        manager.title.set('Keep this failed-save draft')
        with patch('atlas.ui.write_atlas', side_effect=PermissionError('Read only test')), patch('atlas.ui.messagebox.showerror'):
            assert not manager.save()
        assert manager.dirty and manager.title.get() == 'Keep this failed-save draft'
        assert path.read_bytes() == saved and app.history.store.revisions() == revisions
        with patch('atlas.flow_ui.messagebox.askyesnocancel', return_value=None):
            assert not manager.close() and manager.active
        manager.title.set('Packet forwarding')
        assert manager.capture() and not manager.dirty
        checks.append('Failed saves preserve flow drafts and authoritative JSON/history; Cancel keeps the flow open with its unsaved changes')

        assert manager.set_mode('study')
        assert manager.select_step(ids[4])
        app._visible_layer_changed('network')
        prior_view = camera()
        assert not manager.focus_step() and camera() == prior_view
        manager.show_flow_layers()
        assert manager.focus_step()
        settle()
        assert tuple(app.scene.target) == app.scene.concept_point(arp.id)
        x, y, _ = app.scene.project(app.scene.concept_point(arp.id))
        assert app._pick_at(round(x), round(y)) == arp.id
        old_yaw = app.scene.yaw
        app.scene.rotate(30, 10)
        app.request_render()
        settle()
        assert app.scene.yaw != old_yaw and app.scene.flow_paths
        manager.show_entire_flow()
        root.geometry('1020x780')
        assert manager.select_step(ids[2])
        settle()
        assert app.navigation.winfo_ismapped() and manager.next_button.winfo_ismapped()
        assert manager.reader.winfo_width() >= 200 and app.canvas.winfo_width() >= 350
        assert manager.choices_frame.winfo_rooty()+manager.choices_frame.winfo_height() <= manager.study_scroll.canvas.winfo_rooty()+manager.study_scroll.canvas.winfo_height()
        assert manager.close()
        checks.append('Focus respects hidden filters, Show flow layers reveals the process, arrows survive rotation and the study controls fit the minimum window')

        app.select_node(arp.id)
        with patch('atlas.cluster_ui.messagebox.askyesno', return_value=True) as confirmation:
            assert app.clusters.delete()
        assert 'flow(s)' in confirmation.call_args.args[1]
        assert app.document.flow(manager.draft.id).step(ids[4]).concept_id == arp.id
        assert manager.open()
        assert manager.select_step(ids[4])
        assert 'Missing concept' in manager.read_concept.cget('text')
        assert manager.focus_button.instate(['disabled'])
        assert manager.set_mode('edit') and manager.relink(app.document.get(route.id))
        assert manager.save()
        assert manager.draft.step(ids[4]).concept_id == route.id
        assert manager.close()
        checks.append('Deleting a referenced suborbital warns about affected flows, retains a marked missing step and supports relinking it to another existing concept')

        saved, revisions = path.read_bytes(), app.history.store.revisions()
        assert app.history.open()
        history = app.history
        index = next(i for i, concept in enumerate(history.concepts) if concept.id == manager.draft.id)
        history.concept_list.selection_clear(0, 'end')
        history.concept_list.selection_set(index)
        history._selected_concept()
        settle()
        assert history.notes.cget('state') == 'disabled' and 'Apply packet policy' in history.notes.get('1.0', 'end')
        assert history.scene.flow_note is not None and app.scene.flow_note is None
        history.close()
        assert path.read_bytes() == saved and app.history.store.revisions() == revisions
        checks.append('Saved-state History lists flows, displays their steps and original referenced notes in its independent scene and leaves the active document unchanged')
    finally:
        app.history.close()
        with patch('atlas.flow_ui.messagebox.askyesnocancel', return_value=False):
            manager.close()
        app._load_editor(None)
        assert app.apply_design(original)
        app.set_view_mode(original_mode)
        app.labels_var.set(original_labels)
        app._load_editor(original.nodes[0] if original.nodes else None)
        app.request_render()
        settle()
