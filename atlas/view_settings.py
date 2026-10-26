"""Local interface preferences, kept outside atlas JSON and saved history."""
import json
from pathlib import Path

from .storage import _atomic_bytes


def _read(path):
    try:
        if path.stat().st_size > 32768:
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, RecursionError):
        return {}


def navigation_collapsed(path: Path) -> bool:
    return _read(path).get("navigation_collapsed") is True


def save_navigation_collapsed(path: Path, collapsed: bool):
    data = _read(path)
    data["navigation_collapsed"] = bool(collapsed)
    _atomic_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
