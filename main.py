#!/usr/bin/env python3
"""Run with: python main.py. All data stays in a per-user local JSON file."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

from atlas.runtime import LOGGER, callback_error, configure_logging, show_error
from atlas.storage import default_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Cyber Atlas - a spatial cybersecurity notebook.")
    parser.add_argument("--file", type=Path, help="Use this local JSON file instead of the default data location.")
    parser.add_argument("--empty", action="store_true", help="Start empty only when the chosen data file does not exist.")
    parser.add_argument("--self-test", type=Path, metavar="REPORT", help="Run an isolated desktop check; requires --file pointing to a new test atlas.")
    args = parser.parse_args()
    if args.self_test and (args.file is None or args.file.expanduser().exists()):
        parser.error("--self-test requires --file pointing to a new, nonexistent test atlas")
    if args.self_test and args.self_test.expanduser().resolve() == args.file.expanduser().resolve():
        parser.error("The self-test report and atlas must use different paths")
    path = (args.file or default_path()).expanduser().resolve()
    configure_logging(path.parent / "logs")
    if sys.version_info < (3, 10):
        show_error("Cyber Atlas requires Python 3.10 or newer.")
        return 1
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        show_error("Tkinter could not be loaded. Reinstall Cyber Atlas, or install Tk support when running from source.")
        return 1
    try:
        from atlas.model import Atlas, AtlasError, example_atlas
        from atlas.storage import read_atlas, write_atlas
        from atlas.ui import AtlasApp
    except ImportError as exc:
        show_error(f"A dependency could not be loaded: {exc}\nReinstall Cyber Atlas, or install requirements.txt when running from source.")
        return 1
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CyberAtlas.Desktop")
        root = tk.Tk()
        root.withdraw()
    except tk.TclError as exc:
        show_error(f"A graphical desktop is required.\n{exc}")
        return 1
    root.report_callback_exception = lambda *error: callback_error(root, *error)
    try:
        if path.exists():
            try:
                document = read_atlas(path)
            except (OSError, AtlasError) as exc:
                backup = path.with_suffix(path.suffix + ".bak")
                if not backup.exists():
                    raise
                document = read_atlas(backup)
                recover = messagebox.askyesno("Recover your atlas?", f"The atlas could not be read:\n{exc}\n\nRestore its last valid backup? The unreadable original will be kept.", parent=root)
                if not recover:
                    root.destroy()
                    return 1
                broken = path.with_name(path.name + f".broken-{datetime.now():%Y%m%d-%H%M%S-%f}")
                path.rename(broken)
                write_atlas(path, document, backup=False)
        else:
            document = (Atlas() if args.empty else example_atlas()).with_layer_centers()
            write_atlas(path, document, backup=False)
        app = AtlasApp(root, path, document, settings_directory=path.parent if args.self_test else default_path().parent,
                       automatic_updates=not bool(args.self_test))
        root.deiconify()
        if args.self_test:
            from atlas.self_test import run
            return run(app, args.self_test.expanduser().resolve())
        root.mainloop()
        return 0
    except (OSError, AtlasError) as exc:
        messagebox.showerror("Could not open Cyber Atlas", f"{exc}\n\nData file: {path}\nNo existing atlas has been replaced.", parent=root)
        root.destroy()
        return 1
    except Exception:
        LOGGER.exception("Unexpected application failure")
        show_error(f"Cyber Atlas could not start. See the log in:\n{path.parent / 'logs'}", root=root)
        root.destroy()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
