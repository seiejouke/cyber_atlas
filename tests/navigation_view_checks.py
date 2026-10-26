"""Real layer-slider filtering, retracting and settings persistence."""
from unittest.mock import patch

from atlas.model import Atlas, Design, Layer, Node, Protocol, Subconcept
from atlas.navigation_ui import NavigationPanel
from atlas.view_settings import navigation_collapsed


def check_navigation(root, app, path, pump, checks):
    original, original_mode = app.document, app.scene.mode
    nav = app.navigation
    original_collapsed = nav.collapsed
    design = Design((Layer("low", "Foundation", "#70cbd8"),
                     Layer("middle", "Shared services", "#91abe2"),
                     Layer("high", "User interface", "#edbb69")),
                    (Protocol("visible", "Visible"), Protocol("hidden", "Hidden")))
    parent = Node("navigation-parent", "Parent", "middle", "visible", 0, "Keep these notes", slot=3)
    nodes = (Node("navigation-low", "Low note", "low", "visible", 0, "Low notes", slot=0), parent,
             Node("navigation-high", "High note", "high", "hidden", 0, "High notes", slot=8))
    child = Subconcept("navigation-child", parent.id, "Independent child", "Child notes", 2)
    fixture = Atlas(nodes, design, (child,))

    def camera():
        return app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target)

    def choose(index):
        y = round(nav.slider.stops[index])
        nav.slider.event_generate("<ButtonPress-1>", x=42, y=y)
        nav.slider.event_generate("<ButtonRelease-1>", x=42, y=y)
        pump(root)

    try:
        app.scene.collapse_orbit()
        app._load_editor(None)
        assert app.apply_design(fixture)
        app.set_view_mode("nodes")
        app._load_editor(parent)
        if nav.collapsed:
            nav.toggle()
        root.geometry("1300x860")
        pump(root)
        app.name_var.set("Unsaved main-note title")
        app.notes.insert("end", "\nUnsaved main-note text")
        draft = app._form_state()
        saved, backup, revisions = path.read_bytes(), path.with_suffix(".json.bak").read_bytes(), app.history.store.revisions()
        view = camera()
        assert [layer.id for layer in nav.slider.layers] == ["high", "middle", "low"]
        assert abs((nav.slider.stops[1]-nav.slider.stops[0]) - (nav.slider.stops[2]-nav.slider.stops[1])) < .001
        for i, layer_id in enumerate(("high", "middle", "low")):
            choose(i)
            assert app.scene.layer_filter == nav.slider.selected == layer_id
            assert app.filter_var.get() == app._layer_displays[layer_id]
            assert app._form_state() == draft and app.dirty and app.selected == parent.id
            assert camera() == view and app.document == fixture
        nav.all_button.invoke()
        pump(root)
        assert app.scene.layer_filter is None and nav.slider.selected is None and app.filter_var.get() == "All layers"
        checks.append("Visible-layer stops follow custom layer order at equal intervals; filtering and All preserve the camera, selected note and dirty draft")

        app.filter_var.set(app._layer_displays["middle"])
        app.filter_box.event_generate("<<ComboboxSelected>>")
        pump(root)
        assert nav.slider.selected == "middle"
        nav.slider.event_generate("<ButtonPress-1>", x=42, y=round(nav.slider.stops[0]))
        nav.slider.event_generate("<B1-Motion>", x=42, y=round(nav.slider.stops[1]))
        assert app.scene.layer_filter == "middle"
        nav.slider.event_generate("<ButtonRelease-1>", x=42, y=round(nav.slider.stops[-1]))
        pump(root)
        assert app.scene.layer_filter == "low"
        nav.slider.focus_force()
        pump(root)
        nav.slider.event_generate("<Up>")
        pump(root)
        assert app.scene.layer_filter == "middle"
        nav.slider.event_generate("<Home>")
        pump(root)
        assert app.scene.layer_filter == "high"
        nav.slider.event_generate("<End>")
        pump(root)
        assert app.scene.layer_filter == "low"
        nav.all_button.invoke()
        app.protocol_filter_var.set("Visible")
        app._filter_changed()
        choose(0)
        assert nav.slider.selected == "high" and not any(app.scene.is_visible(n) for n in nodes)
        app.protocol_filter_var.set(app._all_protocols)
        app._filter_changed()
        checks.append("Slider dragging and focused keyboard input snap to saved layers; the dropdown stays synchronized and protocol filters continue to apply")

        # A real node under the expanded panel becomes pickable when it retracts.
        high_node = nodes[-1]
        x, y, _ = app.scene.project(app.scene.node_anchor(high_node))
        destination = (app.canvas.winfo_width()-70, 140)
        app.scene.pan(destination[0]-x, destination[1]-y)
        app.request_render()
        pump(root)
        x, y, _ = app.scene.project(app.scene.node_anchor(high_node))
        assert app._pick_at(round(x), round(y)) is None
        shifted_view = camera()
        nav.toggle()
        pump(root)
        assert nav.collapsed and nav.tab.winfo_ismapped() and not app.compass.winfo_ismapped()
        assert app.scene.layer_filter == "high" and camera() == shifted_view and app._form_state() == draft
        assert app._pick_at(round(x), round(y)) == high_node.id
        app.scene.yaw, app.scene.elevation, app.scene.scale = view[:3]
        app.scene.target = list(view[3])
        app.scene._apply_camera()
        app.request_render()
        pump(root)
        assert navigation_collapsed(nav.settings_path)
        reserved = nav.reserved_box
        assert reserved[2]-reserved[0] < 40
        probe = NavigationPanel(app.canvas, app.scene, app.request_render, app._visible_layer_changed,
                                nav.settings_path, family=app.family, mono=app.mono, on_status=app._set_status)
        try:
            assert probe.collapsed
        finally:
            probe.close()
            probe.destroy()
        nav.tab.invoke()
        pump(root)
        assert not nav.collapsed and app.compass.winfo_ismapped() and not navigation_collapsed(nav.settings_path)
        assert nav.reserved_box[2]-nav.reserved_box[0] > 100
        with patch("atlas.navigation_ui.save_navigation_collapsed", side_effect=OSError("Simulated settings failure")):
            nav.toggle()
        pump(root)
        assert nav.collapsed and "this session" in app.status.cget("text")
        nav.tab.invoke()
        pump(root)
        assert app._form_state() == draft and camera() == view
        assert path.read_bytes() == saved and path.with_suffix(".json.bak").read_bytes() == backup
        assert app.history.store.revisions() == revisions
        checks.append("Retracting releases viewport space, reopens with one click and remembers its state separately; settings failures never lose drafts, filters or saved atlas history")

        app._load_editor(parent)
        nav.all_button.invoke()
        app.scene.expand_orbit(parent.id)
        app.scene.focus_orbit()
        pump(root)
        focused_camera = camera()
        choose(0)
        assert app.scene.focused_parent is None and camera() == focused_camera
        assert app.scene.layer_filter == "high"
        checks.append("Filtering away a focused cluster ends its focus without changing camera orientation, zoom, pan or any saved child")

        root.geometry("1020x780")
        pump(root)
        assert nav.winfo_ismapped() and nav.winfo_x() >= 0
        assert nav.winfo_y()+nav.winfo_height() < app.canvas.winfo_height()
        assert nav.slider.winfo_height() >= 70 and app.notes.winfo_height() >= 80
        assert len(nav.slider.stops) == 3
        app.compass.activate("home")
        pump(root, 16)
        tip_y = {axis: (app.compass.hits[axis][1]+app.compass.hits[axis][3])/2 for axis in "XYZ"}
        assert tip_y["Z"] < tip_y["X"] < tip_y["Y"]
        app.set_view_mode("blocks")
        choose(1)
        assert app.scene.layer_filter == "middle" and nav.slider.selected == "middle"
        app.set_view_mode("nodes")
        assert nav.slider.selected == "middle"
        checks.append("Combined compass and slider fit the minimum viewport and preserve independent layer filtering through Blocks/Nodes switches")

        # Exercise both ends of the supported custom-layer range.
        for count in (1, 7, 64):
            layers = tuple(Layer(f"navigation-{i}", f"Custom layer {i+1}", "#70cbd8") for i in range(count))
            app._load_editor(None)
            assert app.apply_design(Atlas(design=Design(layers, ())))
            pump(root)
            assert len(nav.slider.layers) == len(nav.slider.stops) == count
            if count <= 7:
                assert len(nav.slider.find_withtag("layer-label")) == count
            if count > 2:
                intervals = [b-a for a, b in zip(nav.slider.stops, nav.slider.stops[1:])]
                assert max(intervals)-min(intervals) < .001
            choose(0)
            assert app.scene.layer_filter == layers[-1].id
            choose(count-1)
            assert app.scene.layer_filter == layers[0].id
            nav.all_button.invoke()
            assert app.scene.layer_filter is None
        checks.append("Single-layer and 64-layer custom atlases remain selectable with equal slider intervals and readable, thinned labels")
    finally:
        app.scene.collapse_orbit()
        app._load_editor(None)
        assert app.apply_design(original)
        app.set_view_mode(original_mode)
        app._load_editor(original.nodes[0] if original.nodes else None)
        if nav.collapsed != original_collapsed:
            nav.toggle()
        app.request_render()
        pump(root)
