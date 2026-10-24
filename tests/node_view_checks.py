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
    app.blocks_button.invoke()
    _pump(root)
    assert app.labels_var.get() and app.size_box.winfo_ismapped() and app.size_label.winfo_ismapped()
    assert app._form_state() == original_form and camera() == original_camera
    app.set_view_mode("nodes")
    _pump(root)
    checks.append("Blocks/Nodes switches preserve dirty titles, notes, selection, camera and saved data; Nodes hides block size and restores the Blocks label choice")

    app._load_editor(wide)
    app.begin_placement()
    app._hover_at(*point(target(12)))
    assert app.scene.preview_node.slot == 12 and app.scene.preview_node.span == 4
    assert app._floating_position == (2, 12)
    app.name_var.set("Moving draft title")
    app.notes.insert("end", "\nStill moving.")
    preview = app.scene.preview_node
    floating, origin, form = app._floating_position, app._placement_origin, app._form_state()
    app.set_view_mode("blocks")
    app.set_view_mode("nodes")
    _pump(root)
    assert app.placement_state == "placing" and app.scene.preview_node == preview
    assert app._floating_position == floating and app._placement_origin == origin and app._form_state() == form
    assert app.canvas.find_withtag("preview-halo") and app.save_button.instate(["disabled"])
    assert camera() == original_camera and path.read_bytes() == saved_bytes
    app.cancel_placement()
    assert app.slot_var.get() == "03" and app.name_var.get() == "Moving draft title"
    app._load_editor(wide)
    _pump(root)
    checks.append("switching views during placement preserves the floating preview, original lock, wide footprint and text without saving")

    assert set(app.scene.guides) == {node.position for node in fixture.nodes}
    assert all(not actor.GetPickable() for actor in app.scene.guides.values())
    for depth in range(CENTER_DEPTH, 5):
        for span in (1, 2, 4, 8, 16):
            for slot in range(16):
                candidate = replace(wide, slot=slot, span=span, depth=depth)
                x, y, _ = app.scene.project(app.scene.node_anchor(candidate))
                assert app.scene.position_at(x, y, wide.layer, span=span) == (depth, slot), (depth, span, slot)
    for node in fixture.nodes:
        anchor = app.scene.node_anchor(node)
        assert abs(anchor[2] - (design.z_base + design.layer_index(node.layer) + .5)) < 1e-9
        assert app.scene.pick(*point(node)) == node.id
    assert app.canvas.find_withtag("node-halo")
    assert {node_id for node_id, _ in app._label_hits} == {wide.id}
    app._hover_at(*point(neighbor))
    _pump(root)
    assert app._hovered_node == neighbor.id and not app.labels_var.get()
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
    assert app.selected == wide.id and app.placement_state == "placing"
    assert app.scene.position_at(*point(target(12)), wide.layer, span=wide.span) == (2, 12)
    app._hover_at(*point(target(12)))
    click(target(12))
    assert app.placement_state == "locked" and app.slot_var.get() == "13"
    assert app.scene.preview_node.slot == 12 and app.scene.preview_node.span == 4
    app._hover_at(*point(target(0)))
    assert app.scene.preview_node.slot == 12
    assert path.read_bytes() == saved_bytes and app.document.get(wide.id) == wide
    assert app.save_node()
    moved = app.document.get(wide.id)
    assert moved == replace(wide, slot=12) and read_atlas(path).get(wide.id) == moved
    assert len(app.document.nodes) == len(fixture.nodes)
    checks.append("sphere clicks select, pick up and lock at the next location; Save preserves identity, notes and a larger original block footprint")

    saved_bytes = path.read_bytes()
    app.protocol_filter_var.set("Visible group")
    app._filter_changed()
    _pump(root)
    assert not app.scene.is_visible(blocker)
    click(moved)
    assert app.placement_state == "placing"
    app._hover_at(*point(target(8)))
    assert app.scene.preview_node.slot == 8 and not app.scene.preview_valid
    click(target(8))
    assert app.placement_state == "placing" and not app.scene.preview_valid
    assert not app.save_node() and path.read_bytes() == saved_bytes
    app.canvas.focus_force()
    app.canvas.event_generate("<Escape>")
    _pump(root)
    assert app.placement_state == "locked" and app.slot_var.get() == "13" and not app.dirty
    assert app.document.get(wide.id) == moved and path.read_bytes() == saved_bytes
    app.protocol_filter_var.set(app._all_protocols)
    app._filter_changed()
    _pump(root)
    checks.append("Nodes placement rejects slots reserved by a hidden larger block; Escape restores the saved lock without changing the file")

    app.new_node()
    assert app.placement_state == "placing" and app.size_var.get() == "1/16"
    assert app._last_size == "1/4" and app.scene.preview_node.span == 1
    app.name_var.set("Small node addition")
    app.notes.insert("1.0", "A new sphere occupies one slot.")
    click(target(0, span=1))
    assert app.placement_state == "locked" and app.slot_var.get() == "01"
    assert app.save_node()
    added = app.document.get(app.selected)
    assert added.span == 1 and added.slot == 0 and added.notes == "A new sphere occupies one slot."
    assert app.document.get(wide.id) == moved
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
    checks.append("new spheres use one slot despite the remembered larger Blocks size; returning to Blocks restores that size and preserves saved dimensions")

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
    assert not app.document.nodes and not app.scene.guides
    app.name_var.set("Center sphere")
    app.notes.insert("1.0", "An empty custom atlas can start at the center.")
    assert app.place_at(CENTER_DEPTH, 0)
    assert app.save_node()
    center = app.document.get(app.selected)
    _pump(root)
    assert center.depth == CENTER_DEPTH and center.protocol is None and center.span == 1
    assert app.scene.pick(*point(center)) == center.id
    assert set(app.scene.guides) == {center.position}
    assert read_atlas(path) == app.document and not app.dirty
    checks.append("Empty atlas retains Nodes mode and the custom design; a protocol-free center sphere can be created, saved and picked")

    root.geometry("1020x780")
    _pump(root)
    assert app.notes.winfo_height() >= 80
    assert not app.size_box.winfo_ismapped() and not app.size_label.winfo_ismapped()
    assert app.blocks_button.winfo_ismapped() and app.nodes_button.winfo_ismapped()
    for button in (app.blocks_button, app.nodes_button, app.save_button):
        assert button.winfo_rootx() + button.winfo_width() <= root.winfo_rootx() + root.winfo_width()
    assert app.canvas.find_withtag("node-halo") and app.selected == center.id and not app.dirty
    checks.append("Nodes controls, selected halo and note editor fit the minimum window with a clean saved selection")
