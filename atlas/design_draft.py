"""Layers may temporarily be empty; protocol assignment is optional."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from .model import Atlas, AtlasError, Design, Layer, LayerId, Node, Protocol, validate_occupancy


@dataclass(frozen=True, slots=True)
class PendingAssignment:
    id: LayerId
    name: str
    count: int


class DesignDraft:
    def __init__(self, atlas: Atlas):
        self.nodes = atlas.nodes
        self.layers = atlas.design.layers
        self.protocols = atlas.design.protocols
        self._settings = atlas.design
        self._known = {"layers": {e.id: e for e in self.layers},
                       "protocols": {e.id: e for e in self.protocols}}

    @staticmethod
    def _attribute(kind: str) -> str:
        if kind not in ("layers", "protocols"):
            raise AtlasError("Choose layers or protocols.")
        return "layer" if kind == "layers" else "protocol"

    def entries(self, kind: str) -> tuple[Layer, ...] | tuple[Protocol, ...]:
        self._attribute(kind)
        return getattr(self, kind)

    def set_entries(self, kind: str, entries: tuple) -> None:
        self._attribute(kind)
        # Only the layer list needs the draft exception for zero entries.
        if entries != ():
            replace(self._settings, **{kind: entries})
        setattr(self, kind, entries)
        self._known[kind].update((e.id, e) for e in entries)

    def clear(self, kind: str) -> None:
        self.set_entries(kind, ())
        if kind == "protocols":
            self.nodes = tuple(replace(node, protocol=None) for node in self.nodes)

    def pending(self, kind: str) -> tuple[PendingAssignment, ...]:
        attribute = self._attribute(kind)
        valid = {entry.id for entry in self.entries(kind)}
        if kind == "protocols":
            valid.add(None)
        counts = Counter(getattr(node, attribute) for node in self.nodes if getattr(node, attribute) not in valid)
        return tuple(PendingAssignment(key, self._known[kind][key].name, count) for key, count in counts.items())

    @property
    def ready(self) -> bool:
        return bool(self.layers and not self.pending("layers") and not self.pending("protocols"))

    @property
    def readiness_hint(self) -> str:
        if not self.layers:
            return "Add at least one layer before applying."
        if self.pending("layers") or self.pending("protocols"):
            return "Reassign blocks from removed entries before applying."
        return "Changes take effect when you apply."

    def _moved_nodes(self, kind: str, moves: dict) -> tuple[Node, ...]:
        attribute = self._attribute(kind)
        nodes = tuple(replace(n, **{attribute: moves.get(getattr(n, attribute), getattr(n, attribute))}) for n in self.nodes)
        validate_occupancy(nodes, {key: entry.name for key, entry in self._known["layers"].items()})
        return nodes

    def reassign(self, kind: str, moves: dict) -> None:
        pending = {entry.id for entry in self.pending(kind)}
        valid = {entry.id for entry in self.entries(kind)}
        if set(moves) != pending or any(target not in valid for target in moves.values()):
            raise AtlasError("Choose an existing replacement for every removed entry that has blocks.")
        nodes = self._moved_nodes(kind, moves)
        self.nodes = nodes

    def remove(self, kind: str, entry_id: LayerId, replacement_id: LayerId | None = None) -> None:
        entries = self.entries(kind)
        if entry_id not in {e.id for e in entries}:
            raise AtlasError("The selected entry no longer exists.")
        if len(entries) == 1:
            raise AtlasError("Keep at least one entry, or use the clear-list button to start over.")
        remaining = tuple(e for e in entries if e.id != entry_id)
        used = any(getattr(n, self._attribute(kind)) == entry_id for n in self.nodes)
        if used and replacement_id not in {e.id for e in remaining}:
            raise AtlasError("Choose an existing replacement entry.")
        nodes = self._moved_nodes(kind, {entry_id: replacement_id} if used else {})
        self.set_entries(kind, remaining)
        self.nodes = nodes

    @property
    def design(self) -> Design:
        return replace(self._settings, layers=self.layers, protocols=self.protocols)

    def to_atlas(self, **settings) -> Atlas:
        return Atlas(self.nodes, replace(self.design, **settings))
