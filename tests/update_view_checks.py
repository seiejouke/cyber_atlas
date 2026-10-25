"""Exercise update consent and unsaved work using the real GUI and fake releases."""
from dataclasses import replace
import hashlib
import threading
import time
from unittest.mock import patch

from atlas import __version__, updates


def check_updates(root, app, path, pump, checks):
    manager = app.updates
    saved, form, original_context = path.read_bytes(), app._form_state(), manager.context
    notes = b"verified update fixture"
    asset = updates.ReleaseAsset("CyberAtlas-99.0.0-Setup.exe",
        f"{updates.RELEASES_URL}/download/v99.0.0/CyberAtlas-99.0.0-Setup.exe", len(notes), hashlib.sha256(notes).hexdigest())
    release = updates.Release("99.0.0", f"{updates.RELEASES_URL}/tag/v99.0.0", "New features and fixes.", asset)
    manager.context = updates.UpdateContext("windows", path.parent / "installed" / "CyberAtlas.exe")
    assert not manager.settings.automatic

    def settle():
        deadline = time.monotonic() + 5
        while manager.busy and time.monotonic() < deadline:
            pump(root, 2)
        assert not manager.busy, "Update worker did not finish"
        pump(root, 2)

    gate = threading.Event()
    worker_threads = []

    def delayed_check(context):
        worker_threads.append(threading.get_ident())
        assert gate.wait(3)
        return release

    with patch("atlas.updates.check_release", side_effect=delayed_check) as check, \
         patch("atlas.updates.download_release") as download:
        app.updates_button.invoke()
        pump(root, 2)
        assert manager.busy and manager.dialog.winfo_exists()
        app.name_var.set("Text typed while checking")
        pump(root, 2)
        assert app.name_var.get() == "Text typed while checking"
        gate.set()
        settle()
        assert worker_threads and worker_threads[0] != threading.get_ident()
        assert manager.release == release and manager.action_button.instate(["!disabled"])
        assert "99.0.0" in manager.message.get()
        download.assert_not_called()
        manager.close_dialog()
        download.assert_not_called()
        assert path.read_bytes() == saved
    checks.append("Updates checks GitHub on a worker thread only after the user opens Updates; Later never starts a download and editing stays responsive")

    with patch("atlas.updates.check_release", return_value=replace(release, version=__version__)), \
         patch("atlas.updates.download_release") as download:
        manager.open(check=False)
        manager.check()
        settle()
        assert "up to date" in manager.message.get()
        assert manager.action_button.instate(["disabled"])
        download.assert_not_called()
    checks.append("An installed or newer development version is never offered an older package")

    download_path = path.parent / asset.name

    def downloaded(release, directory, cancel, progress):
        progress(len(notes), len(notes))
        download_path.write_bytes(notes)
        return download_path

    with patch("atlas.updates.check_release", return_value=release), \
         patch("atlas.updates.download_release", side_effect=downloaded) as download, \
         patch("atlas.updates.start_windows_update") as install:
        manager.check()
        settle()
        manager.action_button.invoke()
        settle()
        download.assert_called_once()
        install.assert_not_called()
        assert manager.download == download_path and manager.action_button.cget("text") == "Restart and update"
        assert path.read_bytes() == saved
        with patch("atlas.ui.messagebox.askyesnocancel", return_value=None):
            assert not manager.apply()
        install.assert_not_called()
        assert app.dirty and app.name_var.get() == "Text typed while checking"
        with patch("atlas.ui.messagebox.askyesnocancel", return_value=True), patch.object(app, "save_node", return_value=False):
            assert not manager.apply()
        install.assert_not_called()
        assert not app._closed
        with patch("atlas.ui.messagebox.askyesnocancel", return_value=True), patch.object(app, "shutdown") as shutdown:
            assert manager.apply()
        shutdown.assert_called_once()
        install.assert_called_once()
        assert install.call_args.args[3] == app.path
        assert not app.dirty and path.read_bytes() != saved
    checks.append("Only Download update fetches a package; verified downloads wait for Restart and update before starting an installer")
    checks.append("Cancelling the unsaved-notes prompt or a failed save prevents installation; a successful save precedes the installer and retains the atlas path")
    app.name_var.set(form[0])
    assert app.save_node()

    with patch("atlas.updates.check_release", side_effect=updates.UpdateError("Could not reach GitHub.")):
        manager.check()
        settle()
        assert "Could not reach" in manager.message.get()
        assert manager.action_button.instate(["disabled"]) and not app.dirty
    checks.append("Offline checks show an actionable message and leave the editor and saved atlas available")

    manager.automatic_var.set(True)
    manager._toggle_automatic()
    assert updates.load_settings(manager.settings_path).automatic
    manager.close_dialog()
    if manager._auto_job is not None:
        root.after_cancel(manager._auto_job)
        manager._auto_job = None
    manager.settings = updates.UpdateSettings(True, 0)
    with patch("atlas.updates.check_release", return_value=replace(release, version=__version__)) as check:
        manager._automatic_check()
        settle()
        assert manager.dialog is None
        root.after_cancel(manager._auto_job)
        manager._auto_job = None
        manager._automatic_check()
        settle()
        check.assert_called_once()
    root.after_cancel(manager._auto_job)
    manager._auto_job = None
    gate.clear()
    manager.settings = updates.UpdateSettings(True, 0)
    with patch("atlas.updates.check_release", side_effect=delayed_check):
        manager._automatic_check()
        manager.open(check=False)
        manager.close_dialog()
        gate.set()
        settle()
        assert manager.dialog is None
    root.after_cancel(manager._auto_job)
    manager._auto_job = None
    checks.append("Dismissing a pending automatic check prevents its result from reopening the update window")
    manager.open(check=False)
    manager.automatic_var.set(False)
    manager._toggle_automatic()
    assert not updates.load_settings(manager.settings_path).automatic
    checks.append("Daily automatic checks require an explicit saved opt-in, run at most once per day, and stay quiet when the app is current")

    manager.context = original_context
    manager.close_dialog()
    assert app._form_state() == form
