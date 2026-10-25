"""Exercise outline selection, hover, filters and appearance state in the real GUI."""
from math import pi

from atlas.model import Atlas, Design, Layer, Node, Protocol
from atlas.scene import Scene


def check_outline_occlusion(checks):
    design = Design((Layer("low", "Low", "#70cbd8"), Layer("high", "High", "#cb96ba")), ())
    lower = Node("low", "Low", "low", None, 0, slot=0, span=16)
    upper = Node("high", "High", "high", None, 0, slot=0, span=16)
    scene = Scene(design)
    try:
        scene.set_nodes((lower, upper))
        scene.elevation, scene.scale = 20 * pi / 180, 2.8
        scene._apply_camera()
        scene.frame(800, 600)
        for point in scene.meshes[lower.id].points:
            x, y, _ = scene.project(point)
            if not scene._block_picker.Pick(x, scene.height - 1 - y, 0, scene.renderer):
                continue
            front = scene._actor_ids.get(scene._block_picker.GetActor().GetAddressAsString(""))
            if front == upper.id and scene.pick(x, y) == lower.id:
                scene.set_selected(upper.id)
                scene.frame(800, 600)
                assert scene.pick(x, y) == upper.id
                break
        else:
            raise AssertionError("An outlined edge behind another block's empty interior must remain selectable")
        checks.append("Outlined edges can be picked through nearer empty interiors; a selected opaque block occludes those same edges")
    finally:
        scene.close()


def check_block_view(root, app, path, pump, checks):
    check_outline_occlusion(checks)
    original, selected = app.document, app.selected
    app._load_editor(app.document.get(selected))
    app.set_view_mode("blocks")
    design = Design((Layer("lower", "Data", "#70cbd8"), Layer("upper", "API", "#cb96ba")),
                    (Protocol("visible", "Visible"), Protocol("hidden", "Hidden")), "Area", "Group", "title")
    first = Node("outline-first", "Authentication", "upper", "visible", 0, "Keep this note", slot=8, span=4)
    second = Node("outline-second", "Database", "lower", "visible", 1, slot=11, span=2)
    hidden = Node("outline-hidden", "Hidden reservation", "upper", "hidden", 2, slot=3, span=2)
    fixture = Atlas((first, second, hidden), design)
    assert app.apply_design(fixture)
    app._load_editor(first)
    app.set_block_appearance("outline")
    app.filter_var.set("All layers")
    app.protocol_filter_var.set(app._all_protocols)
    app._filter_changed()
    root.geometry("1300x860")
    app.scene.yaw, app.scene.elevation, app.scene.scale = 3 * pi / 4, pi / 4, 4.2
    app.scene.target = [0., 0., 0.]
    app.scene._apply_camera()
    app.request_render()
    pump(root, 8)
    saved = path.read_bytes()

    def camera():
        return app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target)

    def point(node):
        x, y, _ = app.scene.project(app.scene.meshes[node.id].label_anchor)
        return round(x), round(y)

    assert app.scene.actors[first.id][0].GetVisibility()
    assert not app.scene.actors[second.id][0].GetVisibility()
    assert all(outline.GetVisibility() for _, outline in app.scene.actors.values())
    assert app.scene.pick(*point(second)) == second.id
    assert not app.scene.occludes(*point(second))
    app.canvas.event_generate("<ButtonPress-1>", x=point(second)[0], y=point(second)[1])
    app.canvas.event_generate("<ButtonRelease-1>", x=point(second)[0], y=point(second)[1])
    pump(root)
    assert app.selected == second.id and app.scene.actors[second.id][0].GetVisibility()
    assert not app.scene.actors[first.id][0].GetVisibility() and path.read_bytes() == saved
    checks.append("Outline keeps only the selection solid; clicking an unfilled block selects it without writing the atlas")

    app.labels_var.set(False)
    app._hover_at(*point(hidden))
    pump(root)
    assert app._hovered_node == hidden.id and app.scene.hovered == hidden.id
    assert hidden.id in [node_id for node_id, _ in app._label_hits]
    assert app.selected == second.id and path.read_bytes() == saved
    app._restore_preview()
    pump(root)
    assert app._hovered_node is None and app.scene.hovered is None
    checks.append("Hover highlights an outlined block on another layer and reveals its label even with Labels off; leaving clears the highlight")

    app.name_var.set("Draft title")
    app.notes.insert("end", "\nDraft notes")
    form, position, meshes = app._form_state(), camera(), dict(app.scene.meshes)
    app.solid_button.invoke()
    pump(root)
    assert all(solid.GetVisibility() for solid, _ in app.scene.actors.values())
    app.outline_button.invoke()
    pump(root)
    assert app.scene.block_appearance == "outline" and app._form_state() == form
    assert app.dirty and camera() == position and app.scene.meshes == meshes and path.read_bytes() == saved
    app.begin_placement()
    draft = app.scene.preview_node
    app.set_block_appearance("solid")
    app.set_block_appearance("outline")
    assert app.placement_state == "placing" and app.scene.preview_node == draft and app._form_state() == form
    app.cancel_placement()
    app._load_editor(second)
    checks.append("Solid/Outline switches preserve camera, saved geometry, unsaved text and an active placement draft")

    app.protocol_filter_var.set("Visible")
    app._filter_changed()
    pump(root)
    assert not app.scene.actors[hidden.id][1].GetVisibility()
    assert app.scene.pick(*point(hidden)) is None
    app.filter_var.set(app._layer_displays[first.layer])
    app._filter_changed()
    pump(root)
    assert app.scene.pick(*point(second)) is None
    assert not any(solid.GetVisibility() for solid, _ in app.scene.actors.values())
    checks.append("Layer and protocol filters remove outlined blocks from both edge and interior picking, including a filtered selection")

    app.filter_var.set("All layers")
    app.protocol_filter_var.set(app._all_protocols)
    app._filter_changed()
    app.set_view_mode("nodes")
    pump(root)
    assert not app.block_bar.winfo_ismapped()
    assert all(solid.GetVisibility() for solid, _ in app.scene.actors.values())
    app.set_view_mode("blocks")
    pump(root)
    assert app.block_bar.winfo_ismapped() and app.scene.block_appearance == "outline"
    assert sum(solid.GetVisibility() for solid, _ in app.scene.actors.values()) == 1
    app.open_templates()
    pump(root)
    assert not app.block_bar.winfo_ismapped()
    app.cancel_templates()
    pump(root)
    assert app.scene.mode == "blocks" and app.scene.block_appearance == "outline" and app.block_bar.winfo_ismapped()
    assert path.read_bytes() == saved and app.document == fixture
    checks.append("Outline appearance survives Nodes and template previews; appearance controls stay out of Nodes view")

    app.set_block_appearance("solid")
    assert app.apply_design(original)
    app._load_editor(app.document.get(selected))
    app.labels_var.set(True)
