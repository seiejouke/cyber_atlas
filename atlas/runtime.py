"""Diagnostics that also work in a desktop build without a console."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys


LOGGER = logging.getLogger("cyber_atlas")


def configure_logging(directory: Path) -> Path | None:
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    for handler in LOGGER.handlers[:]:
        handler.close()
        LOGGER.removeHandler(handler)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "cyber-atlas.log"
        handler = RotatingFileHandler(path, maxBytes=1_048_576, backupCount=2, encoding="utf-8")
    except OSError:
        LOGGER.addHandler(logging.NullHandler())
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    return path


def show_error(message: str, *, root=None) -> None:
    """Report startup failures even when sys.stderr is None in a windowed EXE."""
    LOGGER.error(message)
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    try:
        from tkinter import messagebox
        messagebox.showerror("Cyber Atlas", message, parent=root)
    except Exception:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "Cyber Atlas", 0x10)


def callback_error(root, exception_type, exception, traceback) -> None:
    LOGGER.error("Interface callback failed", exc_info=(exception_type, exception, traceback))
    show_error("An operation could not be completed. Details were written to the application log.", root=root)
