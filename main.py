#!/usr/bin/env python3
"""Run with: python main.py. All data stays in a per-user local JSON file."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Cyber Atlas - a spatial cybersecurity notebook.")
    parser.add_argument("--file", type=Path, help="Use this local JSON file instead of the default data location.")
    parser.add_argument("--empty", action="store_true", help="Start empty only when the chosen data file does not exist.")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        print("Cyber Atlas requires Python 3.10 or newer.", file=sys.stderr)
        return 1
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        print("Tkinter is missing. Install Tk support for your Python, then run again. See README.md.", file=sys.stderr)
        return 1
    try:
        from atlas.model import Atlas, AtlasError, example_atlas
        from atlas.storage import default_path, read_atlas, write_atlas
        from atlas.ui import AtlasApp
    except ImportError as exc:
        print(f"A dependency could not be loaded: {exc}\nRun: python -m pip install -r requirements.txt", file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError as exc:
        print(f"A graphical desktop is required.\n{exc}", file=sys.stderr)
        return 1
    path = (args.file or default_path()).expanduser().resolve()
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
            document = Atlas() if args.empty else example_atlas()
            write_atlas(path, document, backup=False)
        app = AtlasApp(root, path, document)
        root.deiconify()
        root.mainloop()
        return 0
    except (OSError, AtlasError) as exc:
        messagebox.showerror("Could not open Cyber Atlas", f"{exc}\n\nData file: {path}\nNo existing atlas has been replaced.", parent=root)
        root.destroy()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
