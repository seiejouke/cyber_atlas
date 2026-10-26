"""Real compass clicks and camera projections, without changing atlas files."""
from math import isclose
import time

from atlas.orientation import DEFAULT_ELEVATION, DEFAULT_YAW, aligned_view, camera_basis


def check_compass(root, app, path, pump, checks):
    document, selection = app.document, app.selected
    mode = app.scene.mode
    camera = (app.scene.yaw, app.scene.elevation, app.scene.scale, list(app.scene.target))
    saved = path.read_bytes()
    revisions = app.history.store.revisions()
    filters = (app.scene.layer_filter, app.scene.protocol_filter)

    def settle(compass):
        deadline = time.monotonic() + 3
        while compass._job is not None and time.monotonic() < deadline:
            pump(root, 1)
        assert compass._job is None, "Camera transition did not finish"
        pump(root, 2)

    def click(compass, key):
        box = compass.hits[key]
        x, y = round((box[0] + box[2]) / 2), round((box[1] + box[3]) / 2)
        assert compass.hit(x, y) == key
        compass.event_generate("<ButtonPress-1>", x=x, y=y)
        compass.event_generate("<ButtonRelease-1>", x=x, y=y)
        settle(compass)

    try:
        app.scene.target = [.2, -.3, .1]
        app.scene.scale = 3.8
        app.scene._apply_camera()
        app.name_var.set(app.name_var.get() + " draft")
        app.notes.insert("end", "\nUnsaved draft survives compass clicks.")
        draft = app._form_state()
        assert app.dirty
        for view_mode in ("nodes", "blocks"):
            app.set_view_mode(view_mode)
            pump(root)
            compass = app.compass
            colors = {key: actors[0].GetProperty().GetColor() for key, actors in app.scene.actors.items()}
            for axis in "XYZ":
                for sign in (1, -1):
                    click(compass, axis)
                    assert aligned_view(app.scene.yaw, app.scene.elevation) == (axis, sign)
                    assert app.scene.scale == 3.8 and app.scene.target == [.2, -.3, .1]
                    assert app._form_state() == draft and app.dirty and app.selected == selection
                    assert app.document == document and path.read_bytes() == saved
                    assert (app.scene.layer_filter, app.scene.protocol_filter) == filters
                    assert colors == {key: actors[0].GetProperty().GetColor() for key, actors in app.scene.actors.items()}
                    # Check real VTK screen directions against compass directions, including both poles.
                    origin = app.scene.project(tuple(app.scene.target))
                    right, up, toward = camera_basis(app.scene.yaw, app.scene.elevation)
                    for delta, expected in ((right, (1, 0)), (up, (0, -1)), (toward, (0, 0))):
                        projected = app.scene.project(tuple(a + b for a, b in zip(app.scene.target, delta)))
                        units = app.scene.height / (2 * app.scene.scale)
                        assert isclose(projected[0] - origin[0], expected[0]*units, abs_tol=1e-5)
                        assert isclose(projected[1] - origin[1], expected[1]*units, abs_tol=1e-5)
            click(compass, "home")
            assert (app.scene.yaw, app.scene.elevation) == (DEFAULT_YAW, DEFAULT_ELEVATION)
            assert app.scene.scale == 3.8 and app.scene.target == [.2, -.3, .1]
        assert app.history.store.revisions() == revisions
        checks.append("Compass clicks reach all six signed axis views in Nodes and Blocks; Home preserves zoom, focus, drafts, filters, heat and saved history")

        click(app.compass, "Z")
        bounds = app.compass.reserved_box
        app.scene.pan(30, -20)
        app.scene.zoom(1)
        app.request_render()
        pump(root)
        assert app.compass.reserved_box == bounds
        assert aligned_view(app.scene.yaw, app.scene.elevation) == ("Z", 1)
        app._rotate_key(0, -10)
        pump(root)
        assert aligned_view(app.scene.yaw, app.scene.elevation) is None
        assert app.scene.elevation > 1.4  # No jump back to the old 1.30 clamp.
        checks.append("The compass follows manual rotation, stays fixed through pan/zoom, and exact top view rotates away without a pole jump")

        app.compass.activate("X")
        app._rotate_key(8, -4)
        interrupted = (app.scene.yaw, app.scene.elevation)
        pump(root, 12)
        assert app.compass._job is None and interrupted == (app.scene.yaw, app.scene.elevation)
        # Dragging over a compass tip must not trigger an axis snap.
        x0, y0, x1, y1 = app.compass.hits["Y"]
        x, y = round((x0+x1)/2), round((y0+y1)/2)
        app.compass.event_generate("<ButtonPress-1>", x=x, y=y)
        app.compass.event_generate("<ButtonRelease-1>", x=x+6, y=y)
        pump(root)
        assert interrupted == (app.scene.yaw, app.scene.elevation)
        checks.append("Manual camera input cancels an in-flight snap, and dragging a compass tip does not click it")

        root.geometry("1020x780")
        pump(root)
        assert app.compass.winfo_ismapped()
        assert app.compass.winfo_x() >= 0
        assert app.compass.winfo_y() + app.compass.winfo_height() < app.canvas.winfo_height() - 72
        reserved = app.compass.reserved_box
        for _, box in app._label_hits:
            assert not (box[0] < reserved[2] and box[2] > reserved[0] and box[1] < reserved[3] and box[3] > reserved[1]), box
        checks.append("Compass and note labels fit the minimum window with separate click targets and reserved label space")

        app._load_editor(document.get(selection))
        assert app.history.open()
        pump(root)
        history = app.history
        active_camera = (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target))
        for axis in "XYZ":
            click(history.compass, axis)
            assert aligned_view(history.scene.yaw, history.scene.elevation) == (axis, 1)
        click(history.compass, "home")
        assert active_camera == (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target))
        assert app.history.store.revisions() == revisions and path.read_bytes() == saved
        history.compass.activate("Z")
        history.close()
        pump(root, 12)
        checks.append("History has its own clickable compass; orientation creates no revisions, leaves the main camera alone and cancels cleanly on close")
    finally:
        app.history.close()
        app.compass.cancel_animation()
        app._load_editor(document.get(selection))
        app.set_view_mode(mode)
        app.scene.yaw, app.scene.elevation, app.scene.scale, app.scene.target = camera
        app.scene._apply_camera()
        app.request_render()
        pump(root)
