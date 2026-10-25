"""Exercise strict spatial edges through the real app, filters and renderer."""
from dataclasses import replace

from atlas.model import Atlas, CENTER_DEPTH, Design, Layer, Node, Protocol, Subconcept


def check_connections(root, app, path, pump, checks):
    design = Design((Layer("base", "Base", "#70cbd8"), Layer("top", "Top", "#edbb69")),
                    (Protocol("visible", "Visible"), Protocol("hidden", "Hidden")))
    a = Node("a", "First", "base", "visible", 0, slot=0)
    bridge = Node("bridge", "Hidden middle", "base", "hidden", 0, slot=1)
    b = Node("b", "Third", "base", "visible", 0, slot=2)
    isolated = Node("isolated", "Across empty slots", "base", "visible", 0, slot=8)
    outer = Node("outer", "Adjacent band", "base", "visible", 1, slot=0)
    far = Node("far", "Across empty band", "base", "visible", 3, slot=0)
    corner = Node("corner", "Corner contact only", "base", "visible", 1, slot=3)
    other = Node("other", "Other layer", "top", "visible", 0, slot=0)
    child = Subconcept("child", a.id, "Explicit child", "Independent child notes")
    fixture = Atlas((a, bridge, b, isolated, outer, far, corner, other), design, (child,))
    app._load_editor(None)
    assert app.apply_design(fixture)
    app.set_view_mode("nodes")
    app._load_editor(a)
    app.scene.set_preview(None)
    pump(root)
    saved = path.read_bytes()
    expected = (("a", "bridge"), ("a", "outer"), ("b", "bridge"))
    assert app.scene.connection_pairs == expected, app.scene.connection_pairs
    assert sum(actor.GetMapper().GetInput().GetNumberOfLines()
               for actor in app.scene.connections.values()) == len(expected)
    assert all(not actor.GetPickable() for actor in app.scene.connections.values())
    assert all(len(endpoints) >= 2 for endpoints in app.scene._connection_nodes.values())
    for actor in app.scene.connections.values():
        assert all(abs(actual - target) < 1e-6 for actual, target in zip(
            actor.GetProperty().GetColor(), (0x70 / 255, 0xcb / 255, 0xd8 / 255)))
    checks.append("VTK renders exactly the edge-sharing spatial pairs; gaps, corners, other layers and marker spokes have no edges")

    app.protocol_filter_var.set("Visible")
    app._filter_changed()
    pump(root)
    assert app.scene.connection_pairs == (("a", "outer"),)
    assert not app.scene.is_visible(bridge)
    assert ("a", "b") not in app.scene.connection_pairs
    app.filter_var.set(app._layer_displays[other.layer])
    app._filter_changed()
    pump(root)
    assert not app.scene.connection_pairs and not app.scene.connections
    app.filter_var.set("All layers")
    app.protocol_filter_var.set(app._all_protocols)
    app._filter_changed()
    pump(root)
    assert app.scene.connection_pairs == expected and path.read_bytes() == saved
    checks.append("protocol and layer filters hide existing edges without reconnecting across hidden concepts or writing data")

    app.scene.set_preview(replace(a, id="preview", slot=5))
    assert app.scene.connection_pairs == (("b", "bridge"),)
    app.scene.set_preview(replace(a, id="preview", slot=1), valid=False)
    assert app.scene.connection_pairs == expected
    app.scene.set_preview(None)
    assert app.scene.connection_pairs == expected and path.read_bytes() == saved
    checks.append("valid move drafts update strict adjacency; invalid drafts and cancellation retain saved edges and notes")

    app.scene.expand_orbit(a.id)
    pump(root)
    assert set(app.scene.orbit_actors) == {child.id}
    assert len(app.scene._orbit_lines) == 2  # Local ring plus explicit parent-child spoke.
    assert app.scene.connection_pairs == expected
    assert all(child.id not in pair for pair in app.scene.connection_pairs)
    app.scene.focus_orbit()
    pump(root)
    assert all(not actor.GetVisibility() for actor in app.scene.connections.values())
    assert app.scene.orbit_actors[child.id].GetVisibility()
    app.scene.collapse_orbit()
    assert app.scene.connection_pairs == expected and not app.scene.orbit_actors
    checks.append("explicit orbital relationships remain separate from spatial adjacency and survive reversible cluster focus")

    camera = (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target))
    app.connections_check.invoke()
    pump(root)
    assert not app.scene.connection_pairs and not app.scene.connections
    app.connections_check.invoke()
    pump(root)
    assert app.scene.connection_pairs == expected and path.read_bytes() == saved
    assert camera == (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target))
    app.set_view_mode("blocks")
    assert not app.scene.connection_pairs
    app.set_view_mode("nodes")
    assert app.scene.connection_pairs == expected and path.read_bytes() == saved
    checks.append("Connections and Blocks/Nodes toggles restore the same graph without moving nodes or changing the camera")

    reduced = fixture.without_node(bridge.id)
    assert app.apply_design(reduced)
    app._load_editor(a)
    assert app.scene.connection_pairs == (("a", "outer"),)
    center = Node("center", "Real center", "base", None, CENTER_DEPTH, span=16)
    assert app.apply_design(reduced.with_node(center))
    app._load_editor(center)
    assert app.scene.connection_pairs == (("a", "center"), ("a", "outer"),
                                           ("b", "center"), ("center", "isolated"))
    assert not app.scene.axis_markers[center.layer].GetVisibility()
    checks.append("deleting a bridging node leaves a gap; real center notes connect only to footprints on the immediately adjacent band")
