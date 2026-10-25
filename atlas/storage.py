"""Human-readable JSON, strict loading, and atomic writes with one backup."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

from .model import Atlas, AtlasError

MAX_FILE_BYTES = 16 * 1024 * 1024


def default_path() -> Path:
    """Use the operating system's per-user data folder, not the source tree."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "CyberAtlas" / "atlas.json"


def read_atlas(path: Path) -> Atlas:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise AtlasError("This file is too large (maximum 16 MiB).")
    try:
        return Atlas.from_dict(json.loads(path.read_text(encoding="utf-8-sig")))
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise AtlasError(f"The file is not valid UTF-8 JSON: {exc}") from exc


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name is not None and os.path.exists(name):
            os.unlink(name)


def write_atlas(path: Path, atlas: Atlas, *, backup: bool = True) -> None:
    content = (json.dumps(atlas.to_dict(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(content) > MAX_FILE_BYTES:
        raise AtlasError("The atlas exceeds the 16 MiB file limit. Shorten some notes or information entries before saving.")
    # Never replace a good backup with a corrupt file.
    if backup and path.exists():
        read_atlas(path)
        _atomic_bytes(path.with_suffix(path.suffix + ".bak"), path.read_bytes())
    _atomic_bytes(path, content)
