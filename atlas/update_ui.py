"""Update notifications and consent, with network work kept off the Tk thread."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from queue import Empty, Queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from . import __version__, theme
from .runtime import LOGGER
from . import updates


class UpdateManager:
    def __init__(self, app, directory: Path, *, automatic: bool = True):
        self.app, self.root, self.directory = app, app.root, directory
        self.settings_path = directory / "updates.json"
        self.settings = updates.load_settings(self.settings_path)
        self.context = updates.update_context()
        self.release = None
        self.download = None
        self.dialog = None
        self.busy = False
        self.closed = False
        self.events = Queue()
        self.cancel = threading.Event()
        self._poll_job = None
        self._auto_job = self.root.after(2000, self._automatic_check) if automatic else None
        self._automatic_request = False

    def _automatic_check(self):
        self._auto_job = None
        if self.closed:
            return
        if self.settings.due() and not self.busy:
            self.check(automatic=True)
        self._auto_job = self.root.after(60 * 60 * 1000, self._automatic_check)

    def _persist(self, settings, *, quiet=False):
        try:
            updates.save_settings(self.settings_path, settings)
        except OSError:
            if not quiet:
                messagebox.showerror("Update settings", "The update preference could not be saved.", parent=self.dialog or self.root)
            return False
        self.settings = settings
        return True

    def _toggle_automatic(self):
        settings = replace(self.settings, automatic=self.automatic_var.get())
        if not self._persist(settings):
            self.automatic_var.set(self.settings.automatic)

    def open(self, *, check=True):
        if self.closed:
            return
        if self.dialog is not None:
            self.dialog.lift()
            return
        dialog = self.dialog = tk.Toplevel(self.root)
        dialog.title("Cyber Atlas updates")
        dialog.transient(self.root)
        dialog.geometry("620x540")
        dialog.minsize(540, 480)
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        ttk.Label(frame, text="Cyber Atlas updates", font=(self.app.family, 16, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=f"Installed version: {__version__}", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 12))
        self.message = tk.StringVar(value="Check GitHub for a newer release.")
        ttk.Label(frame, textvariable=self.message, wraplength=550).grid(row=2, column=0, sticky="ew", pady=(0, 12))
        notes_frame = ttk.Frame(frame)
        notes_frame.grid(row=3, column=0, sticky="nsew")
        notes_frame.columnconfigure(0, weight=1)
        notes_frame.rowconfigure(0, weight=1)
        self.notes = tk.Text(notes_frame, bg=theme.PANEL, fg=theme.TEXT, insertbackground=theme.TEXT,
                             relief="flat", wrap="word", padx=10, pady=10, font=(self.app.family, 10), state="disabled")
        self.notes.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(notes_frame, command=self.notes.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.notes.configure(yscrollcommand=scroll.set)
        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.grid(row=4, column=0, sticky="ew", pady=(12, 12))
        self.automatic_var = tk.BooleanVar(value=self.settings.automatic)
        ttk.Checkbutton(frame, text="Check automatically once a day", variable=self.automatic_var,
                        command=self._toggle_automatic).grid(row=5, column=0, sticky="w")
        ttk.Label(frame, text="Checks contact GitHub. Downloads start only when you choose Download update.",
                  style="Muted.TLabel", wraplength=550).grid(row=6, column=0, sticky="w", pady=(4, 14))
        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, sticky="ew")
        self.check_button = ttk.Button(buttons, text="Check again", command=self.check)
        self.check_button.pack(side="left")
        self.release_button = ttk.Button(buttons, text="View changes", command=self.view_release)
        self.release_button.pack(side="left", padx=6)
        self.action_button = ttk.Button(buttons, text="Download update", command=self.start_download)
        self.action_button.pack(side="left")
        ttk.Button(buttons, text="Later", command=self.close_dialog).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", self.close_dialog)
        if self.busy:
            self._busy_ui("Checking for updates…", True)
        elif self.release is not None:
            self._release_ui()
        elif check:
            self.check()
        else:
            self.action_button.state(["disabled"])

    def _busy_ui(self, text, busy):
        if self.dialog is None:
            return
        self.message.set(text)
        self.check_button.state(["disabled"] if busy else ["!disabled"])
        self.action_button.state(["disabled"] if busy else ["!disabled"])

    def check(self, *, automatic=False):
        if self.closed or self.busy:
            return
        if not self._persist(replace(self.settings, last_check=time.time()), quiet=automatic) and automatic:
            return
        self._automatic_request = automatic
        self._busy_ui("Checking for updates…", True)
        self._run(lambda: updates.check_release(self.context), "release")

    def _run(self, operation, event):
        self.busy = True
        self.cancel = threading.Event()

        def work():
            try:
                self.events.put((event, operation()))
            except updates.DownloadCancelled:
                self.events.put(("cancelled", None))
            except Exception as error:
                message = str(error) if isinstance(error, updates.UpdateError) else "The update could not be completed. Please try again."
                LOGGER.warning("Update operation failed: %s", type(error).__name__)
                self.events.put(("error", message))

        threading.Thread(target=work, name="cyber-atlas-updates", daemon=True).start()
        if self._poll_job is None:
            self._poll_job = self.root.after(80, self._poll)

    def _poll(self):
        self._poll_job = None
        if self.closed:
            return
        try:
            while True:
                event, result = self.events.get_nowait()
                if event == "progress":
                    if self.dialog is not None:
                        received, total = result
                        self.progress["value"] = received / total * 100
                        self.message.set(f"Downloading update… {received / 1048576:.1f} / {total / 1048576:.1f} MB")
                    continue
                self.busy = False
                if event == "release":
                    self.release, self.download = result, None
                    self.app.updates_button.configure(text="Update available" if result.newer else "Updates")
                    if (self._automatic_request and self.settings.automatic and result.newer and self.dialog is None):
                        self.open(check=False)
                    self._release_ui()
                elif event == "download":
                    self.download = result
                    self._release_ui()
                elif event == "error":
                    if self.dialog is not None:
                        self._busy_ui(result, False)
                        self.action_button.state(["disabled"])
                elif event == "cancelled":
                    if self.dialog is not None:
                        self._release_ui()
        except Empty:
            pass
        if self.busy:
            self._poll_job = self.root.after(80, self._poll)

    def _release_ui(self):
        if self.dialog is None or self.release is None:
            return
        release = self.release
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", release.notes)
        self.notes.configure(state="disabled")
        self.check_button.state(["!disabled"])
        if not release.newer:
            self.message.set(f"You're up to date. Installed version: {__version__}.")
            self.action_button.configure(text="Download update", command=self.start_download)
            self.action_button.state(["disabled"])
        elif release.asset is None:
            self.message.set(f"Version {release.version} is available. Use the release page to update this copy.")
            self.action_button.configure(text="View release", command=self.view_release)
            self.action_button.state(["!disabled"])
        elif self.download is not None:
            self.progress["value"] = 100
            self.message.set("Update verified. Your notes will be kept. Save your work before applying the update.")
            self.action_button.configure(text="Open installer" if self.context.kind == "deb" else "Restart and update", command=self.apply)
            self.action_button.state(["!disabled"])
        else:
            self.progress["value"] = 0
            self.message.set(f"Version {release.version} is available. Download size: {release.asset.size / 1048576:.1f} MB.")
            self.action_button.configure(text="Download update", command=self.start_download)
            self.action_button.state(["!disabled"])

    def view_release(self):
        url = self.release.url if self.release else updates.RELEASES_URL
        opener = shutil.which("xdg-open") if sys.platform == "linux" else None
        if opener:
            subprocess.Popen([opener, url], env=updates.external_environment(), start_new_session=True)
        else:
            webbrowser.open(url)

    def start_download(self):
        if self.busy or self.release is None or not self.release.newer or self.release.asset is None:
            return
        self._busy_ui("Downloading update…", True)
        self._run(lambda: updates.download_release(self.release, self.directory / "updates", self.cancel,
                  lambda received, total: self.events.put(("progress", (received, total)))), "download")

    def apply(self):
        if self.busy or self.download is None or self.release is None or self.release.asset is None:
            return False
        if self.app._template_origin is not None:
            self.app.cancel_templates()
        if not self.app._allow_leave():
            return False
        try:
            if self.context.kind == "windows":
                updates.start_windows_update(self.download, self.release.asset, self.context, self.app.path, self.directory / "updates")
            elif self.context.kind == "appimage":
                updates.replace_appimage(self.download, self.release.asset, self.context.executable, self.app.path)
            elif self.context.kind == "deb":
                if not updates.verify_download(self.download, self.release.asset):
                    raise updates.UpdateError("The update file changed. Download it again.")
                opener = shutil.which("xdg-open")
                if opener is None:
                    raise updates.UpdateError("Open the downloaded .deb package with your system's software installer.")
                subprocess.Popen([opener, str(self.download)], env=updates.external_environment(), start_new_session=True)
                self.message.set("Finish the update in your system's package installer, then reopen Cyber Atlas.")
                self.action_button.state(["disabled"])
                return True
            else:
                return False
        except (OSError, updates.UpdateError) as error:
            messagebox.showerror("Update could not start", str(error), parent=self.dialog or self.root)
            return False
        self.app.shutdown()
        return True

    def close_dialog(self):
        self._automatic_request = False
        if self.busy:
            self.cancel.set()
        if self.dialog is not None:
            self.dialog.destroy()
            self.dialog = None

    def shutdown(self):
        self.closed = True
        self.cancel.set()
        for job in (self._poll_job, self._auto_job):
            if job is not None:
                self.root.after_cancel(job)
        self.close_dialog()
