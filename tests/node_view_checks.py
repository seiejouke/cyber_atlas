"""Real Tk/VTK workflow checks shared by the GUI smoke runner."""
from dataclasses import replace
from math import pi
import time
from unittest.mock import patch

from atlas.model import Atlas, CENTER_DEPTH, Design, Layer, Node, Protocol
from atlas.storage import read_atlas


def _pump(root, steps=5):
    for _ in range(steps):
        root.update()
        time.sleep(0.025)


def check_node_view(root, app, path, checks):
    """Exercise both representations against the same saved, custom atlas."""
    design = Design(
        (Layer("node-base", "Foundations", "#65b6a1"),
         Layer("node-top", "Applications", "#edbb69")),
        (Protocol("node-visible", "Visible group"), Protocol("node-hidden", "Hidden group")),
        "My layer", "Group", "combined",
    )
    wide = Node("node-wide", "Wide original", "node-base", "node-visible", 2,
                "Keep the wide block's notes.", slot=2, span=4)
    neighbor = Node("node-neighbor", "Hover example", "node-top", "node-visible", 1,
                    "A second custom layer.", slot=11)
    blocker = Node("node-blocker", "Hidden reservation", "node-base", "node-hidden", 2,
                   "Its occupied slots still count.", slot=9, span=2)
    fixture = Atlas((wide, neighbor, blocker), design)
    app.set_view_mode("blocks")
    app._load_editor(app.document.nodes[0] if app.document.nodes else None)
    assert app.apply_design(fixture)
    app._load_editor(wide)
    app.size_box.event_generate("<<ComboboxSelected>>")
    assert app._last_size == "1/4"
    app.labels_var.set(True)
    root.geometry("1300x860")
    app.scene.yaw = pi * 0.75
    app.scene.elevation = pi / 4
    app.scene.scale = 4.4
    app.scene.target = [0.0, 0.0, 0.0]
    app.scene._apply_camera()
    app.request_render()
    _pump(root)

    def camera():
        return (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target))

    def point(node):
        x, y, _ = app.scene.project(app.scene.node_anchor(node))
        return round(x), round(y)

    def click(node, *, settle=True):
        x, y = point(node)
        app.canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        app.canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
        if settle:
            _pump(root)

    def target(slot, *, span=4, depth=2):
        return replace(wide, id="node-target", slot=slot, span=span, depth=depth)

    saved_bytes = path.read_bytes()
    original_camera = camera()
    app.name_var.set("Unsaved title survives the view switch")
    app.notes.insert("end", "\nUnsaved notes survive too.")
    original_form = app._form_state()
    assert app.dirty
    app.nodes_button.invoke()
    _pump(root)
    assert app.scene.mode == "nodes" and app.view_mode_var.get() == "Nodes"
    assert app._form_state() == original_form and app.dirty and app.selected == wide.id
    assert app.document == fixture and path.read_bytes() == saved_bytes and camera() == original_camera
    assert not app.size_box.winfo_ismapped() and not app.size_label.winfo_ismapped()
    assert not app.labels_var.get()
    assert app.connections_var.get() and app.connections_check.instate(["!disabled"])
    assert set(app.scene.axis_markers) == {layer.id for layer in design.layers}
    axis_bounds = [actor.GetBounds() for actor in app.scene._axis_actors]
    # The selected layer marker is intentionally 35% larger.
    assert min(bounds[4] for bounds in axis_bounds) >= design.z_base + .5 - .076
    assert max(bounds[5] for bounds in axis_bounds) <= -design.z_base - .5 + .076
    assert not app.scene.connections  # These isolated footprints do not touch.
    app.connections_check.invoke()
    _pump(root)
    assert not app.connections_var.get() and not app.scene.connections
    assert app.scene._axis_connection_actors and not any(actor.GetVisibility() for actor in app.scene._axis_connection_actors)
    assert app.document == fixture and path.read_bytes() == saved_bytes and camera() == original_camera
    app.connections_check.invoke()
    _pump(root)
    assert app.connections_var.get() and not app.scene.connections
    assert all(actor.GetVisibility() for actor in app.scene._axis_connection_actors)
    checks.append("Nodes leaves isolated footprints unconnected; Connections toggles the spine without changing atlas data or camera")
    app.blocks_button.invoke()
    _pump(root)
    assert app.labels_var.get() and app.size_box.winfo_ismapped() and app.size_label.winfo_ismapped()
    assert app.connections_check.instate(["disabled"])
    assert app._form_state() == original_form and camera() == original_camera
    app.set_view_mode("nodes")
    _pump(root)
    checks.append("Blocks/Nodes switches preserve dirty titles, notes, selection, camera and saved data; Nodes hides block size and restores the Blocks label choice")

    app._load_editor(wide)
    assert app.editor_heading.cget("text") == "EDIT NOTE"
    assert app.layer_box.instate(["disabled"]) and app.protocol_box.instate(["disabled"])
    assert not app.scale_widget.enabled and not app.slot_slider.enabled
    before_form = app._form_state()
    app.scale_widget.event_generate("<Home>")
    app.slot_slider.event_generate("<End>")
    assert app._form_state() == before_form
    app.set_view_mode("blocks")
    assert not app.layer_box.instate(["disabled"]) and app.scale_widget.enabled and app.slot_slider.enabled
    app.set_view_mode("nodes")
    _pump(root)
    assert app._form_state() == before_form and app.selected == wide.id
    checks.append("saved Nodes expose title and notes while coordinate dropdowns and sliders stay read-only; Blocks restores its placement controls")

    assert set(app.scene.guides) == {node.position for node in fixture.nodes}
    assert all(not actor.GetPickable() for actor in app.scene.guides.values())
    for depth in range(CENTER_DEPTH, 5):
        for span in (1, 2, 4, 8, 16):
            for slot in range(16):
                candidate = replace(wide, slot=slot, span=span, depth=depth)
                x, y, _ = app.scene.project(app.scene.node_anchor(candidate))
                expected_slot = 0 if depth == CENTER_DEPTH and span == 16 else slot
                assert app.scene.position_at(x, y, wide.layer, span=span) == (depth, expected_slot), (depth, span, slot)
    for node in fixture.nodes:
        anchor = app.scene.node_anchor(node)
        assert abs(anchor[2] - (design.z_base + design.layer_index(node.layer) + .5)) < 1e-9
        assert app.scene.pick(*point(node)) == node.id
    assert app.canvas.find_withtag("node-halo")
    assert {node_id for node_id, _ in app._label_hits} == {wide.id}
    app._hover_at(*point(neighbor))
    _pump(root)
    assert app._hovered_node == neighbor.id and not app.labels_var.get(), (app._hovered_node, app.labels_var.get())
    assert {node_id for node_id, _ in app._label_hits} == {wide.id, neighbor.id}
    app._hover_at(2, 2)
    _pump(root)
    assert app._hovered_node is None
    assert {node_id for node_id, _ in app._label_hits} == {wide.id}
    checks.append("custom-layer spheres pick at their midplanes, occupied rings have unpickable guides, and selected/hover labels remain visible with Labels off")

    click(neighbor)
    assert app.selected == neighbor.id and app.placement_state == "locked"
    click(wide)
    assert app.selected == wide.id and app.placement_state == "locked"
    click(wide)
    assert app.selected == wide.id and app.placement_state == "locked" and app.scene.preview_node is None
    empty_target = target(6, span=1, depth=4)
    click(empty_target)
    assert app.selected == wide.id and app._form_state() == before_form
    app.name_var.set("Edited from the sphere")
    app.notes.delete("1.0", "end")
    app.notes.insert("1.0", "Mouse selection edits this note without moving it.")
    assert app.save_node()
    edited = app.document.get(wide.id)
    assert (edited.layer, edited.protocol, edited.depth, edited.slot, edited.span) == (
        wide.layer, wide.protocol, wide.depth, wide.slot, wide.span)
    assert edited.name == "Edited from the sphere" and read_atlas(path).get(wide.id) == edited
    assert len(app.document.nodes) == len(fixture.nodes)
    checks.append("sphere and label clicks select notes for editing; repeat and empty-space clicks never move or create nodes")

    saved_bytes = path.read_bytes()
    app.protocol_filter_var.set("Visible group")
    app._filter_changed()
    _pump(root)
    assert not app.scene.is_visible(blocker)
    assert all(blocker.id not in endpoint_ids for endpoint_ids in app.scene._connection_nodes.values())
    app.new_node()
    assert app.selected is None and app.placement_state == "locked"
    assert app.editor_heading.cget("text") == "CREATE NODE"
    assert app.layer_box.instate(["readonly"]) and app.protocol_box.instate(["readonly"])
    assert app.scale_widget.enabled and app.slot_slider.enabled
    app.layer_var.set(app._layer_displays[wide.layer])
    app.depth_var.set(2)
    app.slot_var.set("10")
    assert app.scene.preview_node.slot == 9 and not app.scene.preview_valid
    assert app.save_button.instate(["disabled"])
    assert not app.save_node() and path.read_bytes() == saved_bytes
    app.slot_var.set("07")
    assert app.scene.preview_valid and app.save_button.instate(["!disabled"])
    app.protocol_filter_var.set(app._all_protocols)
    app._filter_changed()
    _pump(root)
    assert app.scene.is_visible(blocker)
    assert all(blocker.id not in endpoint_ids for endpoint_ids in app.scene._connection_nodes.values())
    checks.append("Nodes creation uses only dropdowns and sliders; hidden occupied slots disable Create node without changing saved data")

    app.name_var.set("Small node addition")
    app.notes.insert("1.0", "A new sphere occupies one slot.")
    assert app.save_node()
    added = app.document.get(app.selected)
    assert app.placement_state == "locked" and app.size_var.get() == "1/16"
    assert app._last_size == "1/4"
    assert added.span == 1 and added.slot == 6 and added.notes == "A new sphere occupies one slot."
    assert app.document.get(wide.id) == edited
    app.set_view_mode("blocks")
    _pump(root)
    assert app.scene.mode == "blocks" and app.labels_var.get() and app.size_box.winfo_ismapped()
    app._load_editor(app.document.get(wide.id))
    assert app.size_var.get() == "1/4" and app.document.get(wide.id).span == 4
    app.new_node()
    assert app.size_var.get() == "1/4"
    app._load_editor(app.document.get(wide.id))
    app.set_view_mode("nodes")
    _pump(root)
    checks.append("Create node saves the slider position with a one-slot footprint; Blocks restores its independent size choice")

    without_protocols = app.document.without_protocols()
    assert app.apply_design(without_protocols)
    _pump(root)
    assert app.scene.mode == "nodes" and app.protocol_var.get() == "No protocol"
    assert all(node.protocol is None for node in app.document.nodes)
    assert set(app.scene.guides) == {node.position for node in app.document.nodes}
    saved_bytes = path.read_bytes()
    app.set_view_mode("blocks")
    app.set_view_mode("nodes")
    _pump(root)
    assert app.document == without_protocols and path.read_bytes() == saved_bytes
    assert app.scene.pick(*point(app.document.get(wide.id))) == wide.id
    checks.append("both views support custom layers and an empty protocol list without adding entries or changing the saved atlas")

    with patch("atlas.ui.messagebox.askyesno", return_value=True):
        assert app.new_empty_atlas()
    _pump(root)
    assert app.scene.mode == "nodes" and app.document.design == without_protocols.design
    assert len(app.document.nodes) == len(app.document.design.layers)
    assert not app.document.has_content
    layer = app.document.design.layers[-1]
    center = app.document.layer_center(layer.id)
    axis_x, axis_y, _ = app.scene.project(app.scene.layer_anchor(layer.id))
    axis_x, axis_y = round(axis_x), round(axis_y)
    app.canvas.event_generate("<ButtonPress-1>", x=axis_x, y=axis_y)
    app.canvas.event_generate("<ButtonRelease-1>", x=axis_x, y=axis_y)
    _pump(root)
    assert app.selected == center.id and not app.dirty
    assert app.depth_var.get() == CENTER_DEPTH and app.size_var.get() == "Full"
    assert app.slot_var.get() == "01" and not app.slot_slider.enabled
    assert not app.scale_widget.enabled and app.move_button.cget("text") == "Edit layer"
    app.name_var.set("Center sphere")
    app.notes.insert("1.0", "An empty custom atlas can start with an editable axis note.")
    assert app.save_node()
    center = app.document.get(app.selected)
    _pump(root)
    assert center.depth == CENTER_DEPTH and center.protocol is None and center.span == 16
    assert app.scene.node_anchor(center) == app.scene.layer_anchor(center.layer)
    assert app.scene.pick(*point(center)) == center.id
    assert set(app.scene.guides) == {node.position for node in app.document.nodes}
    assert not app.scene.axis_markers[center.layer].GetVisibility()
    assert read_atlas(path) == app.document and not app.dirty

    app.new_node()
    assert app.selected is None and app.depth_var.get() == 0
    assert app.save_button.instate(["!disabled"])
    app.depth_var.set(0)
    app.slot_var.set("05")
    assert app.size_var.get() == "1/16" and app.slot_slider.enabled
    assert app.save_button.instate(["!disabled"])
    app.name_var.set("Adjacent sphere")
    app.notes.insert("1.0", "Connected to the editable center node.")
    assert app.save_node()
    outer = app.document.get(app.selected)
    _pump(root)
    assert any(endpoint_ids == frozenset((center.id, outer.id))
               for endpoint_ids in app.scene._connection_nodes.values())
    click(center)
    assert app.selected == center.id
    assert app.notes.get("1.0", "end-1c") == "An empty custom atlas can start with an editable axis note."
    app.notes.insert("end", "\nSaved like every other node.")
    assert app.save_node()
    center = app.document.get(center.id)
    assert center.notes.endswith("Saved like every other node.") and read_atlas(path).get(center.id) == center
    checks.append("empty atlases contain editable, anchored layer concepts; adding an outward node preserves their identity and normal connections")

    root.geometry("1020x780")
    _pump(root)
    assert app.notes.winfo_height() >= 80
    assert not app.size_box.winfo_ismapped() and not app.size_label.winfo_ismapped()
    assert app.blocks_button.winfo_ismapped() and app.nodes_button.winfo_ismapped()
    assert app.connections_check.winfo_ismapped() and app.connections_check.instate(["!disabled"])
    for button in (app.blocks_button, app.nodes_button, app.connections_check, app.save_button):
        assert button.winfo_rootx() + button.winfo_width() <= root.winfo_rootx() + root.winfo_width()
    assert app.canvas.find_withtag("node-halo") and app.selected == center.id and not app.dirty
    checks.append("Nodes controls, selected halo and note editor fit the minimum window with a clean saved selection")


def check_node_moves(root, app, path, checks):
    """Move saved spheres through the real controls without changing their footprint."""
    design = Design(
        (Layer("move-base", "Base", "#65b6a1"), Layer("move-top", "Top", "#edbb69")),
        (Protocol("visible", "Visible"), Protocol("hidden", "Hidden")),
    )
    wide = Node("move-wide", "Wide node", "move-base", "visible", 2, "Original notes", slot=2, span=4)
    blocker = Node("move-blocker", "Hidden reservation", "move-base", "hidden", 2, slot=9, span=2)
    neighbor = Node("move-neighbor", "Neighbor", "move-top", "visible", 1, slot=11)
    center = Node("move-center", "Center", "move-base", None, CENTER_DEPTH, slot=0, span=16)
    fixture = Atlas((wide, blocker, neighbor, center), design)
    assert app.apply_design(fixture)
    app.set_view_mode("nodes")
    app._load_editor(wide)
    _pump(root)
    original_bytes = path.read_bytes()
    original_form = app._form_state()
    assert app.move_button.winfo_ismapped() and app.move_button.cget("text") == "Move node"
    app.move_button.invoke()
    assert app.editor_heading.cget("text") == "MOVE NODE"
    assert app.layer_box.instate(["readonly"]) and app.protocol_box.instate(["disabled"])
    assert app.scale_widget.enabled and app.slot_slider.enabled
    assert app.save_button.cget("text") == "Save move" and not app.dirty
    app.depth_var.set(4)
    app.slot_slider.focus_force()
    app.slot_slider.event_generate("<End>")
    _pump(root)
    assert app.slot_var.get() == "16" and app.scene.preview_node.span == wide.span
    assert app.scene.preview_node.depth == 4 and app.scene.preview_node.slot == 15
    assert app.scene.preview_valid and app.canvas.find_withtag("preview-halo")
    assert app.document == fixture and path.read_bytes() == original_bytes
    app.move_button.invoke()
    assert app._form_state() == original_form and not app.dirty
    assert app.scene.preview_node is None and not app.scale_widget.enabled
    checks.append("Move node unlocks position controls and previews a wrapping footprint; Cancel move restores coordinates without writing")

    app.name_var.set("Title edited before moving")
    app.notes.insert("end", "\nText edited before moving.")
    app.move_button.invoke()
    app.layer_var.set(app._layer_displays[neighbor.layer])
    app.depth_var.set(3)
    app.slot_var.set("14")
    app.notes.insert("end", "\nText edited during moving.")
    app.name_entry.focus_force()
    app.name_entry.event_generate("<Escape>")
    _pump(root)
    assert app._node_move_origin is None and app._form_state()[1:6] == original_form[1:6]
    assert app.name_var.get() == "Title edited before moving"
    assert app.notes.get("1.0", "end-1c").endswith("Text edited during moving.") and app.dirty
    assert path.read_bytes() == original_bytes and app.scene.preview_node is None
    assert app.save_node()
    edited = app.document.get(wide.id)
    assert (edited.layer, edited.depth, edited.slot, edited.span) == (wide.layer, wide.depth, wide.slot, wide.span)
    checks.append("Escape cancels only the move, keeping title and note edits made before and during movement")

    original = app.document
    original_bytes = path.read_bytes()
    app.protocol_filter_var.set("Visible")
    app._filter_changed()
    app.move_button.invoke()
    app.slot_var.set("07")  # The start is free, but this four-slot footprint reaches the hidden blocker.
    assert not app.scene.is_visible(blocker)
    assert not app.scene.preview_valid and app.scene.preview_node.slot == 6
    assert app.save_button.instate(["disabled"]) and app.slot_slider.find_withtag("blocked")
    assert not app.save_node() and app.document == original and path.read_bytes() == original_bytes
    with patch("atlas.ui.messagebox.askyesnocancel", return_value=True):
        assert not app.select_node(neighbor.id)
    assert app.selected == wide.id and app._node_move_origin is not None
    app.filter_var.set(app._layer_displays[wide.layer])
    app._filter_changed()
    app.layer_box.set(app._layer_displays[neighbor.layer])
    app.layer_box.event_generate("<<ComboboxSelected>>")
    app.depth_var.set(3)
    app.slot_var.set("16")
    assert not app.scene.is_visible(app.scene.preview_node)  # The move preview remains visible beyond the filter.
    assert app.scene.preview_actor is not None and app.scene.preview_valid
    form = app._form_state()
    camera = (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target))
    app.canvas.event_generate("<ButtonPress-1>", x=80, y=80)
    app.canvas.event_generate("<B1-Motion>", x=110, y=95)
    app.canvas.event_generate("<ButtonRelease-1>", x=110, y=95)
    app.canvas.event_generate("<MouseWheel>", delta=120)
    _pump(root)
    assert app._form_state() == form and app.selected == wide.id
    assert (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target)) != camera
    assert app.document == original and path.read_bytes() == original_bytes
    checks.append("moves reject hidden reservations across the entire footprint; rotation and zoom preserve the draft and filtered destinations still preview")

    with patch("atlas.ui.messagebox.askyesnocancel", return_value=None) as prompt:
        assert not app.select_node(neighbor.id)
    assert prompt.called and app.selected == wide.id and app._form_state() == form
    with patch("atlas.ui.write_atlas", side_effect=OSError("Simulated move save failure")), \
         patch("atlas.ui.messagebox.showerror"):
        assert not app.save_node()
    assert app._node_move_origin is not None and app._form_state() == form
    assert app.document == original and path.read_bytes() == original_bytes
    app.blocks_button.invoke()
    assert app._form_state() == form and app._node_move_origin is not None
    assert app.size_box.instate(["disabled"]) and app.move_button.cget("text") == "Cancel move"
    app.nodes_button.invoke()
    assert app._form_state() == form and app.scene.preview_node.slot == 15
    app.save_button.invoke()
    moved = app.document.get(wide.id)
    assert app._node_move_origin is None and not app.dirty
    assert (moved.layer, moved.depth, moved.slot, moved.span) == (neighbor.layer, 3, 15, wide.span)
    assert (moved.name, moved.notes, moved.protocol) == (edited.name, edited.notes, edited.protocol)
    assert [node.id for node in app.document.nodes] == [node.id for node in original.nodes]
    assert all(app.document.get(node.id) == node for node in original.nodes if node.id != wide.id)
    assert read_atlas(path) == app.document and read_atlas(path.with_suffix(".json.bak")) == original
    assert app.scene.layer_filter is None and app.scene.is_visible(moved)
    app.set_view_mode("blocks")
    assert app.scene.meshes[moved.id].center == app.scene.node_anchor(moved)
    app.set_view_mode("nodes")
    assert app.scene.actors[moved.id][0].GetPosition() == app.scene.node_anchor(moved)
    checks.append("unsaved moves survive view switches and save failures; Save move keeps identity, text, size and neighbors, writes a backup and updates both views")

    original = app.document
    original_bytes = path.read_bytes()
    app.move_button.invoke()
    app.depth_var.set(4)
    app.set_view_mode("blocks")
    app.move_button.invoke()
    assert app._node_move_origin is None and not app.dirty and app.depth_var.get() == moved.depth
    assert not app.move_button.winfo_manager() and app.size_box.instate(["readonly"])
    app.set_view_mode("nodes")
    app.move_button.invoke()
    app.depth_var.set(4)
    with patch("atlas.ui.messagebox.askyesnocancel", return_value=False):
        assert app.select_node(neighbor.id)
    assert app._node_move_origin is None and app.document == original and path.read_bytes() == original_bytes
    app.move_button.invoke()
    app.depth_var.set(4)
    with patch("atlas.ui.messagebox.askyesnocancel", return_value=True):
        assert app.select_node(moved.id)
    assert app.document.get(neighbor.id).depth == 4 and app._node_move_origin is None
    checks.append("switching notes during movement honors Save, Discard and Cancel; movement can also be cancelled from Blocks")

    app._load_editor(center)
    with patch.object(app, "edit_design") as edit_layer:
        app.move_button.invoke()
    edit_layer.assert_called_once_with(layer_id=center.layer)
    assert app._node_move_origin is None and not app.slot_slider.enabled and not app.scale_widget.enabled
    assert app.layer_box.instate(["disabled"]) and app.size_box.instate(["disabled"])
    app.set_view_mode("blocks")
    app.begin_placement()
    assert app.placement_state == "locked"
    app.set_view_mode("nodes")
    full = Node("move-full", "Full ring", "move-base", None, 0, span=16)
    assert app.apply_design(app.document.with_node(full))
    app._load_editor(full)
    app.move_button.invoke()
    app.depth_var.set(2)
    assert app.size_var.get() == "Full" and app.slot_slider.enabled
    assert app.save_button.instate(["disabled"])  # A full ring would overlap both saved blocks.
    app.depth_var.set(4)
    assert app.scene.preview_node.span == 16 and app.save_button.instate(["!disabled"])
    assert app.save_node()
    ring = app.document.get(full.id)
    assert ring.depth == 4 and ring.span == 16
    app.move_button.invoke()
    app.layer_var.set(app._layer_displays["move-top"])
    app.depth_var.set(CENTER_DEPTH)
    assert not app.slot_slider.enabled and app.scene.preview_node.span == 16
    assert app.save_node() and app.document.get(full.id).is_layer_center
    assert app.move_button.cget("text") == "Edit layer"
    assert app.scene.node_anchor(app.document.get(center.id)) == app.scene.layer_anchor(center.layer)
    app._load_editor(app.document.get(wide.id))
    app.move_button.invoke()
    app.depth_var.set(CENTER_DEPTH)
    assert app.size_var.get() == "1/4" and app.slot_slider.enabled
    assert app.scene.preview_node.span == 4
    app.move_button.invoke()
    checks.append("layer concepts stay anchored in both views; full and partial radial moves retain footprints and a full node can become an anchored center")

    original_bytes = path.read_bytes()
    app.move_button.invoke()  # An unchanged move is a clean draft, including when previewing templates.
    app.open_templates()
    _pump(root)
    assert app._node_move_origin is None and not app.move_node() and not app.save_node()
    assert path.read_bytes() == original_bytes
    app.cancel_templates()
    assert app._node_move_origin is not None and app.editor_heading.cget("text") == "MOVE NODE"
    assert not app.dirty and path.read_bytes() == original_bytes
    app.move_button.invoke()
    app.new_node()
    assert app.selected is None and not app.move_button.winfo_manager() and not app.move_node()
    app._load_editor(app.document.get(wide.id))
    app.move_button.invoke()
    root.geometry("1020x780")
    _pump(root)
    assert app.notes.winfo_height() >= 80
    for button in (app.move_button, app.save_button):
        assert button.winfo_ismapped()
        assert button.winfo_rootx() + button.winfo_width() <= root.winfo_rootx() + root.winfo_width()
    app.move_button.invoke()
    checks.append("movement stays unavailable for new nodes and read-only templates; template cancellation restores a clean move and controls fit the minimum window")
