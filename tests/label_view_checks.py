"""Real rendering checks for label stability, visibility, priority and picking."""
from dataclasses import replace
from math import isclose, pi
import time

from atlas.label_layout import inside, overlaps
from atlas.model import Atlas, CENTER_DEPTH, Design, Layer, Node, Subconcept
from atlas.scene import Scene


def check_labels(root, app, path, pump, checks):
    original, original_mode = app.document, app.scene.mode
    original_labels = app.labels_var.get()
    design = replace(Design(), protocols=(), label_mode="combined")
    physical = (Node("label-axis", "Physical layer", 1, None, CENTER_DEPTH, "Axis note", slot=0, span=16),
                Node("label-bits", "Synchronizing bits", 1, None, 0, "Bits note", slot=8),
                Node("label-timing", "Transmission timing", 1, None, 0, "Timing note", slot=9),
                Node("label-mux", "Multiplexing strategy", 1, None, 0, "Main note", slot=10))
    frames = Node("label-frames", "Frames", 2, None, 0, "A note on another layer", slot=8)
    fixture = Atlas((*physical, frames), design)

    def settle():
        deadline = time.monotonic()+5
        pump(root, 2)
        manager = app.label_manager
        while (app._render_job or manager._settle_job or manager._animation_job or app.compass._job is not None) and time.monotonic() < deadline:
            pump(root, 1)
        assert manager._settle_job is None and manager._animation_job is None and app.compass._job is None

    def ids():
        return {key.split(":", 1)[1] for key in app.label_manager.placements}

    def camera():
        return app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target)

    try:
        app.scene.collapse_orbit()
        app._load_editor(None)
        assert app.apply_design(fixture)
        app.set_view_mode("nodes")
        app.labels_var.set(True)
        app._load_editor(frames)
        app._visible_layer_changed(1)
        root.geometry("1300x860")
        app.scene.target = [0, 0, -3]
        app.scene.scale = 2.1
        app.name_var.set("Unsaved Frames title")
        app.notes.insert("end", "\nKeep this draft through camera changes.")
        draft = app._form_state()
        saved, revisions = path.read_bytes(), app.history.store.revisions()
        for yaw, elevation in ((-pi/2, pi/2), (.3, .8), (2.4, 1.1)):
            app.scene.yaw, app.scene.elevation = yaw, elevation
            app.scene._apply_camera()
            app.request_render()
            settle()
            expected = set()
            for node in physical:
                x, y, depth = app.scene.project(app.scene.node_anchor(node))
                if 0 <= depth <= 1 and 0 < x < app.scene.width and 0 < y < app.scene.height and app.scene.label_visible(node, x, y):
                    expected.add(node.id)
            assert expected <= ids(), (expected, ids())
            assert app.label_manager.hidden_count == 0
        app.compass.activate("Z")
        settle()
        assert ids() == {node.id for node in physical}
        assert frames.id not in ids()
        checks.append("The four-node physical-layer example shows every visible label across top and angled views, while the filtered-out selected note stays excluded")

        before = dict(app.label_manager.placements)
        app.scene.pan(7, 0)
        app.request_render()
        pump(root, 2)  # Let the scheduled frame run while its camera-motion debounce is active.
        for key, box in before.items():
            current = app.label_manager.placements[key]
            assert all(isclose(b-a, expected, abs_tol=1e-5) for a, b, expected in zip(box, current, (7, 0, 7, 0))), (key, box, current)
        settle()
        assert app._form_state() == draft and app.dirty
        assert path.read_bytes() == saved and app.history.store.revisions() == revisions
        checks.append("Labels follow camera movement with stable node-relative offsets; label settling preserves hidden selections, dirty drafts and saved history")

        # Use the actual VTK picker to distinguish partial and complete occlusion.
        isolated = Scene(Design((Layer("only", "Only", "#70cbd8"),), ()))
        try:
            front = Node("front", "Front", "only", None, 0, slot=0)
            rear = Node("rear", "Rear", "only", None, 0, slot=8)
            child = Subconcept("rim-child", front.id, "Child", "Child note", 2)
            isolated.set_nodes((front, rear))
            isolated.set_mode("nodes")
            isolated.set_subconcepts((child,))
            isolated.expand_orbit(front.id)
            isolated.yaw, isolated.elevation, isolated.scale = 0, 0, 1.2
            isolated.target = [0, 0, 0]
            isolated._apply_camera()
            isolated.actors[front.id][0].SetPosition(.25, 0, 0)
            isolated.actors[rear.id][0].SetPosition(0, .04, 0)
            isolated.orbit_actors[child.id].SetPosition(0, -.05, 0)
            isolated.frame(640, 480)
            for concept, actor in ((rear, isolated.actors[rear.id][0]), (child, isolated.orbit_actors[child.id])):
                x, y, _ = isolated.project(actor.GetPosition())
                assert isolated.pick(x, y) == front.id
                assert isolated.label_visible(concept, x, y), concept.id
                actor.SetPosition(0, 0, 0)
                isolated.frame(640, 480)
                x, y, _ = isolated.project(actor.GetPosition())
                assert not isolated.label_visible(concept, x, y), concept.id
        finally:
            isolated.close()
        checks.append("VTK rim samples keep partially obscured node and suborbital labels visible; completely covered concepts remain hidden")

        app._load_editor(physical[-1])
        children = tuple(Subconcept(f"label-child-{i}", physical[-1].id, f"Suborbital {i+1}", "Saved child note", i) for i in range(8))
        cluster = Atlas(fixture.nodes, design, children)
        assert app._commit(cluster)
        app._load_editor(cluster.get(physical[-1].id))
        app.labels_var.set(False)
        assert app.clusters.select_child(children[0].id)
        app.request_render()
        settle()
        assert children[0].id in ids() and physical[-1].id in ids()
        child_box = app.label_manager.placements[f"nodes:{children[0].id}"]
        for key, box in app.label_manager.placements.items():
            if key != f"nodes:{children[0].id}":
                assert not overlaps(child_box, box), (child_box, box)
        assert app._pick_at(round((child_box[0]+child_box[2])/2), round((child_box[1]+child_box[3])/2)) == children[0].id
        checks.append("Nodes and suborbitals share one layout; the selected child receives priority over parent and sibling labels and keeps its clickable label")

        app.clusters.parent_note()
        app.scene.collapse_orbit()
        app._load_editor(None)
        dense_design = Design((Layer("dense", "Dense layer", "#70cbd8"),), (), label_mode="combined")
        dense = Atlas(tuple(Node(f"dense-{depth}-{slot}", f"A detailed information record {depth}-{slot}", "dense", None,
                                 depth, "Saved note", slot=slot) for depth in range(4) for slot in range(16)), dense_design)
        assert app.apply_design(dense)
        app.set_view_mode("nodes")
        app.labels_var.set(True)
        app._load_editor(dense.nodes[0])
        root.geometry("1020x780")
        app.scene.yaw, app.scene.elevation, app.scene.scale = -pi/2, pi/2, 2.4
        app.scene.target = [0, 0, 0]
        app.scene._apply_camera()
        app.request_render()
        settle()
        hovered = next(node for node in dense.nodes[1:] if (lambda p: 0 < p[0] < app.scene.width and 0 < p[1] < app.scene.height)(app.scene.project(app.scene.node_anchor(node))))
        app._hovered_node = hovered.id
        app.scene.set_hovered(hovered.id)
        app.request_render()
        settle()
        assert dense.nodes[0].id in ids() and hovered.id in ids()
        assert app.label_manager.hidden_count > 0 and app.canvas.find_withtag("labels-hidden")
        boxes = list(app.label_manager.placements.values())
        for i, box in enumerate(boxes):
            assert inside(box, (8, 36, app.scene.width-8, app.scene.height-82))
            assert not any(overlaps(box, other) for other in boxes[i+1:])
            assert not overlaps(box, app.navigation.reserved_box)
        saved, revisions = path.read_bytes(), app.history.store.revisions()
        view = camera()
        box = app.label_manager.placements[f"nodes:{hovered.id}"]
        x, y = round((box[0]+box[2])/2), round((box[1]+box[3])/2)
        app.canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        app.canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
        settle()
        assert app.selected == hovered.id and app.document == dense and camera() == view
        assert path.read_bytes() == saved and app.history.store.revisions() == revisions
        checks.append("Crowded minimum-size views reserve space for selected and hovered labels, report labels hidden for space and keep label clicks read-only")
    finally:
        app._hovered_node = None
        app.scene.collapse_orbit()
        app._load_editor(None)
        assert app.apply_design(original)
        app.set_view_mode(original_mode)
        app.labels_var.set(original_labels)
        app._load_editor(original.nodes[0] if original.nodes else None)
        app.request_render()
        settle()
