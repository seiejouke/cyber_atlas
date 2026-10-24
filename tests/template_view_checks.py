"""GUI checks for the live, read-only template preview."""
from unittest.mock import patch

from atlas.storage import read_atlas
from atlas.templates import find_template


def check_template_browser(root, app, path, pump, checks):
    app.set_view_mode("blocks")
    original = app.document
    original_bytes = path.read_bytes()
    original_selected = app.selected
    app.scene.yaw = .71
    app.scene.elevation = .22
    app.scene.scale = 4.31
    app.scene.target = [.2, -.3, .4]
    app.scene._apply_camera()
    original_camera = (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target))

    app.open_templates()
    pump(root)
    python = find_template("python")
    assert app._active_template == python
    assert app.document == python.atlas and path.read_bytes() == original_bytes
    assert app.scene.mode == "nodes" and len(app.scene.actors) == len(python.atlas.nodes)
    assert app.template_form.winfo_ismapped() and not app.editor_form.winfo_ismapped()
    assert [app.template_list.get(i) for i in range(app.template_list.size())] == [
        "Blank atlas", "Python", "TypeScript", "Web application", "Solar system", "Project planning"
    ]
    assert app.template_preview_label.cget("text") == "Previewing: Python"
    assert app.template_meta_label.cget("text") == "5 layers  /  18 nodes"
    assert not app.save_node() and path.read_bytes() == original_bytes
    app.filter_var.set(app.layer_values[-1])
    app._filter_changed()
    app.canvas.event_generate("<Leave>")
    pump(root)
    node = python.atlas.nodes[0]
    x, y, _ = app.scene.project(app.scene.node_anchor(node))
    app.canvas.event_generate("<ButtonPress-1>", x=round(x), y=round(y))
    app.canvas.event_generate("<ButtonRelease-1>", x=round(x), y=round(y))
    pump(root)
    assert app.selected is None and app.document == python.atlas
    app._show_template(find_template("blank"))
    pump(root)
    overlay_text = [app.canvas.itemcget(item, "text") for item in app.canvas.find_withtag("overlay")
                    if app.canvas.type(item) == "text"]
    assert "Your atlas starts here." not in overlay_text
    assert not any("Choose the editor controls" in text for text in overlay_text)
    root.geometry("1020x780")
    pump(root)
    assert app.template_list.winfo_height() >= 120
    assert (app.use_template_button.winfo_rootx() + app.use_template_button.winfo_width()
            < root.winfo_rootx() + root.winfo_width())
    app.scene.rotate(18, -7)
    app.cancel_templates()
    pump(root)
    assert app.document == original and path.read_bytes() == original_bytes
    assert app.selected == original_selected and app.scene.mode == "blocks"
    assert (app.scene.yaw, app.scene.elevation, app.scene.scale, tuple(app.scene.target)) == original_camera
    assert app.editor_form.winfo_ismapped() and not app.template_form.winfo_ismapped()
    checks.append("template previews use real read-only atlas nodes; Cancel restores the document, editor, view and camera without writing")

    app.open_templates()
    typescript = find_template("typescript")
    app._show_template(typescript)
    pump(root)
    with patch("atlas.ui.messagebox.askyesno", return_value=True):
        assert app.use_template()
    pump(root)
    assert app.document == read_atlas(path) == typescript.atlas
    assert app.scene.mode == "nodes" and len(app.scene.actors) == len(typescript.atlas.nodes)
    assert app.editor_form.winfo_ismapped() and not app.template_form.winfo_ismapped()
    assert app.selected == typescript.atlas.nodes[0].id
    assert path.with_suffix(path.suffix + ".bak").exists()
    checks.append("Use template atomically saves the selected ordinary Atlas and returns to the existing node editor")
