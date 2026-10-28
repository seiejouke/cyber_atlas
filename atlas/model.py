"""Knowledge and coordinates. No GUI or rendering dependencies live here."""
from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any
from uuid import uuid4

LAYERS = ("Physical", "Data Link", "Network", "Transport", "Session", "Presentation", "Application")
# Also retained to validate the fixed-sector grid in older files.
PROTOCOLS = (
    "Ethernet", "ARP", "IPv4", "IPv6", "ICMP", "TCP", "UDP", "DNS", "HTTP",
    "HTTPS", "SSH", "FTP", "SMB", "TLS", "DHCP", "Wi-Fi", "Other",
)
BANDS = ("Overview", "Protocol function", "Service", "Implementation", "Detailed example")
CENTER_DEPTH = -1
POSITIONS = ("Center",) + tuple(f"{i:02d}" for i in range(len(BANDS)))
COLORS = ("#65b6a1", "#65b6a1", "#9c8bdb", "#70cbd8", "#8ca9da", "#cb96ba", "#edbb69")
MAX_NODES = 10_000
ANGULAR_SLOTS = 16
BLOCK_SIZES = {"1/16": 1, "1/8": 2, "1/4": 4, "1/2": 8, "Full": 16}
SCHEMA = "cyber-knowledge-atlas"
VERSION = 11
MAX_FLOWS = 256
MAX_FLOW_STEPS = 256
MAX_FLOW_CONNECTIONS = 1024
MAX_INFORMATION_ENTRIES = 50_000
ORBIT_SLOTS = 8
LAYOUT = "fixed-slots"
NO_PROTOCOL_LABEL = "No protocol"


class AtlasError(ValueError):
    """An invalid note, coordinate, or atlas file."""


LayerId = int | str
LABEL_MODES = {"title": "Title only", "coordinates": "Layer + protocol", "combined": "Title + layer + protocol"}


def _text(value: Any, label: str, limit: int = 60) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise AtlasError(f"{label} must be a single line of 1–{limit} characters.")


def _layer_id(value: Any) -> None:
    if type(value) is int and value > 0:
        return
    if isinstance(value, str) and value and len(value) <= 100 and not any(ord(c) < 32 for c in value):
        return
    raise AtlasError("A layer needs a positive integer or nonempty text ID.")


@dataclass(frozen=True, slots=True)
class Layer:
    id: LayerId
    name: str
    color: str

    def __post_init__(self) -> None:
        _layer_id(self.id)
        _text(self.name, "Layer name")
        if not isinstance(self.color, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", self.color) is None:
            raise AtlasError("Choose a layer color in #RRGGBB format.")


@dataclass(frozen=True, slots=True)
class Protocol:
    id: str
    name: str

    def __post_init__(self) -> None:
        _text(self.id, "Protocol ID", 100)
        _text(self.name, "Protocol name")


@dataclass(frozen=True, slots=True)
class Design:
    # Default IDs retain the references used in earlier atlas files. They never
    # change when an entry is renamed or reordered. Custom entries use UUIDs.
    layers: tuple[Layer, ...] = tuple(Layer(i + 1, name, COLORS[i]) for i, name in enumerate(LAYERS))
    protocols: tuple[Protocol, ...] = tuple(Protocol(name, name) for name in PROTOCOLS)
    layer_caption: str = "OSI layer"
    protocol_caption: str = "Protocol"
    label_mode: str = "title"

    def __post_init__(self) -> None:
        for entries, kind, label, minimum, maximum in ((self.layers, Layer, "layers", 1, 64), (self.protocols, Protocol, "protocols", 0, 256)):
            if not isinstance(entries, tuple) or not minimum <= len(entries) <= maximum or not all(isinstance(e, kind) for e in entries):
                raise AtlasError(f"A design needs {minimum}–{maximum} valid {label}.")
            if len({e.id for e in entries}) != len(entries):
                raise AtlasError(f"Duplicate IDs in {label}.")
            if len({e.name.strip().casefold() for e in entries}) != len(entries):
                raise AtlasError(f"Use distinct names for {label}.")
        _text(self.layer_caption, "Layer field name", 24)
        _text(self.protocol_caption, "Protocol field name", 24)
        if not isinstance(self.label_mode, str) or self.label_mode not in LABEL_MODES:
            raise AtlasError("Choose a supported block label style.")

    def layer(self, layer_id: LayerId) -> Layer:
        # Reject bools: True must not resolve to the default layer ID 1.
        _layer_id(layer_id)
        found = next((layer for layer in self.layers if layer.id == layer_id), None)
        if found is None:
            raise AtlasError(f"Unknown layer ID: {layer_id}")
        return found

    def protocol(self, protocol_id: str) -> Protocol:
        found = next((protocol for protocol in self.protocols if protocol.id == protocol_id), None)
        if found is None:
            raise AtlasError(f"Unknown protocol ID: {protocol_id}")
        return found

    def protocol_name(self, protocol_id: str | None) -> str:
        return NO_PROTOCOL_LABEL if protocol_id is None else self.protocol(protocol_id).name

    def layer_index(self, layer_id: LayerId) -> int:
        return self.layers.index(self.layer(layer_id))

    @property
    def z_base(self) -> float:
        return -len(self.layers) / 2

    def block_label(self, node: Node) -> str:
        if self.label_mode == "title":
            return node.name
        coordinates = f"{self.layer(node.layer).name} · {self.protocol_name(node.protocol)}"
        return coordinates if self.label_mode == "coordinates" else f"{node.name} · {coordinates}"

    def to_dict(self) -> dict[str, Any]:
        return {"layers": [{"id": e.id, "name": e.name, "color": e.color} for e in self.layers],
                "protocols": [{"id": e.id, "name": e.name} for e in self.protocols],
                "layer_caption": self.layer_caption, "protocol_caption": self.protocol_caption, "label_mode": self.label_mode}

    @classmethod
    def from_dict(cls, data: Any) -> Design:
        if not isinstance(data, dict) or not isinstance(data.get("layers"), list) or not isinstance(data.get("protocols"), list):
            raise AtlasError("The file needs a design with layer and protocol lists.")
        if not 1 <= len(data["layers"]) <= 64 or not 0 <= len(data["protocols"]) <= 256:
            raise AtlasError("A design needs 1–64 layers and 0–256 protocols.")
        try:
            if not all(isinstance(e, dict) for e in data["layers"] + data["protocols"]):
                raise AtlasError("Design entries must be objects.")
            return cls(tuple(Layer(e["id"], e["name"], e["color"]) for e in data["layers"]),
                       tuple(Protocol(e["id"], e["name"]) for e in data["protocols"]),
                       data["layer_caption"], data["protocol_caption"], data["label_mode"])
        except KeyError as exc:
            raise AtlasError(f"The design is missing {exc.args[0]!r}.") from exc


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    name: str
    layer: LayerId
    protocol: str | None
    depth: int
    notes: str = ""
    slot: int = 0
    span: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id or len(self.id) > 100:
            raise AtlasError("A node needs a nonempty ID of at most 100 characters.")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 120:
            raise AtlasError("Use a name between 1 and 120 characters.")
        if any(ord(c) < 32 for c in self.name):
            raise AtlasError("The name must be a single line without control characters.")
        _layer_id(self.layer)
        if self.protocol is not None:
            _text(self.protocol, "Protocol ID", 100)
        if type(self.depth) is not int or not CENTER_DEPTH <= self.depth < len(BANDS):
            raise AtlasError("Choose Center (-1) or a radial band from 0 to 4.")
        if not isinstance(self.notes, str) or len(self.notes) > 100_000:
            raise AtlasError("Notes must be text, with at most 100,000 characters.")
        if "\x00" in self.notes:
            raise AtlasError("Notes cannot contain a null character.")
        if type(self.slot) is not int or not 0 <= self.slot < ANGULAR_SLOTS:
            raise AtlasError("Choose a start slot from 1 to 16.")
        if type(self.span) is not int or self.span not in BLOCK_SIZES.values():
            raise AtlasError("Choose a block size: 1/16, 1/8, 1/4, 1/2 or Full.")

    @property
    def coordinate(self) -> tuple[LayerId, str | None, int]:
        return self.layer, self.protocol, self.depth

    @property
    def position(self) -> tuple[LayerId, int]:
        """Blocks at the same layer and depth share one ring (or center disk)."""
        return self.layer, self.depth

    @property
    def occupied_slots(self) -> frozenset[int]:
        return frozenset((self.slot + offset) % ANGULAR_SLOTS for offset in range(self.span))

    @property
    def is_layer_center(self) -> bool:
        return self.depth == CENTER_DEPTH and self.span == ANGULAR_SLOTS

    @classmethod
    def create(cls, name: str, layer: LayerId, protocol: str | None, depth: int, notes: str = "", *, slot: int = 0, span: int = 1) -> Node:
        return cls(uuid4().hex, name.strip(), layer, protocol, depth, notes, slot, span)

    def to_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in ("id", "name", "layer", "protocol", "depth", "notes", "slot", "span")}


def validate_occupancy(nodes: tuple[Node, ...], layer_names: dict[LayerId, str]) -> None:
    """Check placement even while a design draft has unresolved references."""
    occupied: dict[tuple[LayerId, int], set[int]] = {}
    for node in nodes:
        ring = occupied.setdefault(node.position, set())
        if ring.intersection(node.occupied_slots):
            position = "Center" if node.depth == CENTER_DEPTH else f"band {node.depth:02d}"
            name = layer_names.get(node.layer, str(node.layer))
            raise AtlasError(f"This block overlaps another block on {name} / {position}. Choose a free start slot or a smaller size.")
        ring.update(node.occupied_slots)


@dataclass(frozen=True, slots=True)
class Subconcept:
    """A concept in a stable local orbit; it has no grid footprint of its own."""
    id: str
    parent_id: str
    name: str
    notes: str = ""
    orbit_slot: int = 0
    relationship: str = "type_of"

    def __post_init__(self) -> None:
        _text(self.id, "Subconcept ID", 100)
        _text(self.parent_id, "Parent ID", 100)
        _text(self.name, "Subconcept name", 120)
        if not isinstance(self.notes, str) or len(self.notes) > 100_000 or "\x00" in self.notes:
            raise AtlasError("Subconcept notes must be text without null characters, at most 100,000 characters.")
        if type(self.orbit_slot) is not int or not 0 <= self.orbit_slot < ORBIT_SLOTS:
            raise AtlasError("Choose an orbit position from 1 to 8.")
        if self.relationship != "type_of":
            raise AtlasError("This version supports the Is a type of relationship.")

    @classmethod
    def create(cls, parent_id: str, name: str, notes: str = "", *, orbit_slot: int = 0) -> Subconcept:
        return cls(uuid4().hex, parent_id, name.strip(), notes, orbit_slot)

    def to_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in ("id", "parent_id", "name", "notes", "orbit_slot", "relationship")}


@dataclass(frozen=True, slots=True)
class InformationEntry:
    """One explicit recorded item belonging to a grid node or subconcept."""
    id: str
    concept_id: str
    title: str
    body: str

    def __post_init__(self) -> None:
        _text(self.id, "Information entry ID", 100)
        _text(self.concept_id, "Information concept ID", 100)
        _text(self.title, "Information title", 120)
        if not isinstance(self.body, str) or not self.body.strip() or len(self.body) > 100_000 or "\x00" in self.body:
            raise AtlasError("Information needs nonempty text without null characters, at most 100,000 characters.")

    @classmethod
    def create(cls, concept_id: str, title: str, body: str) -> InformationEntry:
        return cls(uuid4().hex, concept_id, title.strip(), body)

    def to_dict(self) -> dict[str, str]:
        return {key: getattr(self, key) for key in ("id", "concept_id", "title", "body")}


@dataclass(frozen=True, slots=True)
class FlowStep:
    """One occurrence of a concept; name is a fallback for a deleted reference."""
    id: str
    concept_id: str
    title: str
    concept_name: str = ""
    explanation: str = ""
    question: str = ""

    def __post_init__(self):
        _text(self.id, "Flow step ID", 100)
        _text(self.concept_id, "Referenced concept ID", 100)
        _text(self.title, "Step title", 120)
        if not isinstance(self.concept_name, str) or len(self.concept_name) > 120 or any(ord(c) < 32 for c in self.concept_name):
            raise AtlasError("The saved concept name must be a single line of at most 120 characters.")
        for content, label, limit in ((self.explanation, "Step explanation", 100_000), (self.question, "Recall prompt", 10_000)):
            if not isinstance(content, str) or len(content) > limit or "\x00" in content:
                raise AtlasError(f"{label} must be text without null characters, at most {limit:,} characters.")

    @classmethod
    def create(cls, concept_id, title, concept_name="", **values):
        return cls(uuid4().hex, concept_id, title.strip(), concept_name, **values)

    def to_dict(self):
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class FlowConnection:
    id: str
    source_id: str
    target_id: str | None
    label: str = ""

    def __post_init__(self):
        _text(self.id, "Flow connection ID", 100)
        _text(self.source_id, "Source step ID", 100)
        if self.target_id is not None:
            _text(self.target_id, "Destination step ID", 100)
        if not isinstance(self.label, str) or len(self.label) > 100 or any(ord(c) < 32 for c in self.label):
            raise AtlasError("Connection labels must be single lines of at most 100 characters.")

    @classmethod
    def create(cls, source_id, target_id, label=""):
        return cls(uuid4().hex, source_id, target_id, label.strip())

    def to_dict(self):
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class FlowNote:
    id: str
    title: str
    introduction: str = ""
    steps: tuple[FlowStep, ...] = ()
    connections: tuple[FlowConnection, ...] = ()
    start_step_id: str | None = None

    def __post_init__(self):
        _text(self.id, "Flow ID", 100)
        _text(self.title, "Flow title", 120)
        if not isinstance(self.introduction, str) or len(self.introduction) > 100_000 or "\x00" in self.introduction:
            raise AtlasError("Flow introductions must be text without null characters, at most 100,000 characters.")
        if not isinstance(self.steps, tuple) or len(self.steps) > MAX_FLOW_STEPS or not all(isinstance(s, FlowStep) for s in self.steps):
            raise AtlasError(f"A flow supports at most {MAX_FLOW_STEPS} valid steps.")
        ids = {step.id for step in self.steps}
        if len(ids) != len(self.steps):
            raise AtlasError("Each flow step needs its own unique ID, even when reusing a concept.")
        if self.start_step_id is None and self.steps:
            object.__setattr__(self, "start_step_id", self.steps[0].id)
        if self.start_step_id is not None:
            _text(self.start_step_id, "Starting step ID", 100)
        if self.start_step_id is not None and self.start_step_id not in ids:
            raise AtlasError("The starting step must belong to this flow.")
        if (not isinstance(self.connections, tuple) or len(self.connections) > MAX_FLOW_CONNECTIONS
                or not all(isinstance(c, FlowConnection) for c in self.connections)):
            raise AtlasError(f"A flow supports at most {MAX_FLOW_CONNECTIONS} valid connections.")
        connection_ids, edges, labels = set(), set(), {}
        for connection in self.connections:
            if connection.id in connection_ids:
                raise AtlasError("Duplicate flow connection ID.")
            connection_ids.add(connection.id)
            if connection.source_id not in ids or connection.target_id is not None and connection.target_id not in ids:
                raise AtlasError("Flow connections must reference steps in their own flow.")
            key = connection.source_id, connection.target_id, connection.label.strip().casefold()
            if key in edges:
                raise AtlasError("That flow connection already exists.")
            edges.add(key)
            labels.setdefault(connection.source_id, []).append(connection.label.strip().casefold())
        for names in labels.values():
            if len(names) > 1 and (not all(names) or len(set(names)) != len(names)):
                raise AtlasError("Give each outgoing branch a distinct, nonempty label.")

    @classmethod
    def create(cls, title="New flow", **values):
        return cls(uuid4().hex, title.strip(), **values)

    def step(self, identity):
        return next((step for step in self.steps if step.id == identity), None)

    def outgoing(self, step_id):
        return tuple(c for c in self.connections if c.source_id == step_id)

    def to_dict(self):
        return {"id": self.id, "title": self.title, "introduction": self.introduction,
                "start_step_id": self.start_step_id, "steps": [s.to_dict() for s in self.steps],
                "connections": [c.to_dict() for c in self.connections]}

    @classmethod
    def from_dict(cls, raw):
        if not isinstance(raw, dict):
            raise AtlasError("Each flow must be an object.")
        steps, connections = raw.get("steps"), raw.get("connections")
        if (not isinstance(steps, list) or len(steps) > MAX_FLOW_STEPS or not all(isinstance(s, dict) for s in steps)
                or not isinstance(connections, list) or len(connections) > MAX_FLOW_CONNECTIONS
                or not all(isinstance(c, dict) for c in connections)):
            raise AtlasError("Each flow needs bounded step and connection lists.")
        try:
            return cls(raw["id"], raw["title"], raw.get("introduction", ""),
                       tuple(FlowStep(s["id"], s["concept_id"], s["title"], s.get("concept_name", ""),
                                      s.get("explanation", ""), s.get("question", "")) for s in steps),
                       tuple(FlowConnection(c["id"], c["source_id"], c["target_id"], c.get("label", "")) for c in connections),
                       raw.get("start_step_id"))
        except KeyError as exc:
            raise AtlasError(f"Flow data is missing {exc.args[0]!r}.") from exc


@dataclass(frozen=True, slots=True)
class Atlas:
    nodes: tuple[Node, ...] = ()
    design: Design = Design()
    subconcepts: tuple[Subconcept, ...] = ()
    information_entries: tuple[InformationEntry, ...] = ()
    flows: tuple[FlowNote, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.design, Design):
            raise AtlasError("An atlas needs a valid design.")
        if not isinstance(self.nodes, tuple) or not all(isinstance(n, Node) for n in self.nodes):
            raise AtlasError("An atlas contains a tuple of valid nodes.")
        if len(self.nodes) > MAX_NODES:
            raise AtlasError(f"An atlas can contain at most {MAX_NODES:,} blocks.")
        ids: set[str] = set()
        for node in self.nodes:
            self.design.layer(node.layer)
            if node.protocol is not None:
                self.design.protocol(node.protocol)
            if node.id in ids:
                raise AtlasError(f"Duplicate node ID: {node.id}")
            ids.add(node.id)
        validate_occupancy(self.nodes, {layer.id: layer.name for layer in self.design.layers})
        if not isinstance(self.subconcepts, tuple) or not all(isinstance(child, Subconcept) for child in self.subconcepts):
            raise AtlasError("An atlas contains a tuple of valid subconcepts.")
        if len(self.nodes) + len(self.subconcepts) > MAX_NODES:
            raise AtlasError(f"An atlas can contain at most {MAX_NODES:,} concepts including children.")
        parents = set(ids)
        occupied_orbits = set()
        for child in self.subconcepts:
            if child.id in ids:
                raise AtlasError(f"Duplicate concept ID: {child.id}")
            if child.parent_id not in parents:
                raise AtlasError("Each subconcept needs an existing grid node as its parent; nested orbits are not supported.")
            position = child.parent_id, child.orbit_slot
            if position in occupied_orbits:
                raise AtlasError("That orbit position already contains a subconcept.")
            ids.add(child.id)
            occupied_orbits.add(position)
        if (not isinstance(self.information_entries, tuple)
                or len(self.information_entries) > MAX_INFORMATION_ENTRIES
                or not all(isinstance(entry, InformationEntry) for entry in self.information_entries)):
            raise AtlasError(f"An atlas needs at most {MAX_INFORMATION_ENTRIES:,} valid information entries.")
        entry_ids = set()
        contents = set()
        for entry in self.information_entries:
            if entry.id in entry_ids:
                raise AtlasError("Duplicate information entry ID.")
            if entry.concept_id not in ids:
                raise AtlasError("Every information entry needs an existing node or subconcept.")
            content = entry.concept_id, entry.title.strip().casefold(), entry.body.strip()
            if content in contents:
                raise AtlasError("An identical information entry already exists for this concept.")
            entry_ids.add(entry.id)
            contents.add(content)
        if not isinstance(self.flows, tuple) or len(self.flows) > MAX_FLOWS or not all(isinstance(f, FlowNote) for f in self.flows):
            raise AtlasError(f"An atlas supports at most {MAX_FLOWS} valid flows.")
        if len({flow.id for flow in self.flows}) != len(self.flows):
            raise AtlasError("Duplicate flow ID.")
        # Missing concept references remain repairable after deletion/import.

    def concept(self, identity):
        return self.get(identity) or self.child(identity)

    def flow(self, identity):
        return next((flow for flow in self.flows if flow.id == identity), None)

    def with_flow(self, flow):
        return replace(self, flows=tuple(flow if old.id == flow.id else old for old in self.flows)
                       if self.flow(flow.id) else self.flows + (flow,))

    def without_flow(self, identity):
        if self.flow(identity) is None:
            raise AtlasError("The selected flow no longer exists.")
        return replace(self, flows=tuple(flow for flow in self.flows if flow.id != identity))

    def flows_referencing(self, identities):
        return tuple(flow for flow in self.flows if any(step.concept_id in identities for step in flow.steps))

    def get(self, node_id: str | None) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def layer_center(self, layer_id: LayerId) -> Node | None:
        return next((node for node in self.nodes if node.layer == layer_id and node.is_layer_center), None)

    def with_layer_centers(self, layer_ids=None) -> Atlas:
        """Create ordinary notes at unoccupied layer centers, preserving saved content."""
        occupied = {node.layer for node in self.nodes if node.depth == CENTER_DEPTH}
        additions = tuple(Node.create(layer.name, layer.id, None, CENTER_DEPTH, span=ANGULAR_SLOTS)
                          for layer in self.design.layers
                          if layer.id not in occupied and (layer_ids is None or layer.id in layer_ids))
        # Older files can contain several partial center blocks. Never replace
        # those blocks, their positions or references with a new full center.
        return replace(self, nodes=self.nodes + additions) if additions else self

    @property
    def has_content(self) -> bool:
        """Fresh, unnamed-by-the-user layer centers alone are an empty workspace."""
        return bool(self.subconcepts or self.information_entries or self.flows or any(
            not node.is_layer_center or node.name != self.design.layer(node.layer).name
            or node.notes or node.protocol is not None for node in self.nodes))

    def with_node(self, node: Node) -> Atlas:
        """Return a validated copy; never mutate the current document on failure."""
        previous = self.get(node.id)
        if previous is None:
            return replace(self, nodes=self.nodes + (node,))
        if previous.is_layer_center and (node.layer, node.depth, node.slot, node.span) != (
                previous.layer, previous.depth, previous.slot, previous.span):
            raise AtlasError("A layer's central concept stays on its axis. Use Edit layer to reorder the layer.")
        return replace(self, nodes=tuple(node if old.id == node.id else old for old in self.nodes))

    def free_starts(self, layer: LayerId, depth: int, span: int = 1, *, exclude_id: str | None = None) -> tuple[int, ...]:
        # Reuse coordinate validation even for an empty atlas.
        self.design.layer(layer)
        Node("placement", "Placement", layer, None, depth, span=span)
        occupied = set().union(*(n.occupied_slots for n in self.nodes
                                 if n.position == (layer, depth) and n.id != exclude_id))
        return tuple(slot for slot in range(ANGULAR_SLOTS)
                     if all((slot + offset) % ANGULAR_SLOTS not in occupied for offset in range(span)))

    def next_free(self, layer: LayerId, depth: int, span: int = 1, *, start: int = 0, exclude_id: str | None = None) -> int | None:
        free = set(self.free_starts(layer, depth, span, exclude_id=exclude_id))
        return next(((start + step) % ANGULAR_SLOTS for step in range(ANGULAR_SLOTS)
                     if (start + step) % ANGULAR_SLOTS in free), None)

    def children(self, parent_id: str | None) -> tuple[Subconcept, ...]:
        return tuple(sorted((child for child in self.subconcepts if child.parent_id == parent_id), key=lambda child: child.orbit_slot))

    def child(self, child_id: str | None) -> Subconcept | None:
        return next((child for child in self.subconcepts if child.id == child_id), None)

    def with_child(self, child: Subconcept) -> Atlas:
        old = self.child(child.id)
        children = tuple(child if entry.id == child.id else entry for entry in self.subconcepts) if old else self.subconcepts + (child,)
        return replace(self, subconcepts=children)

    def without_child(self, child_id: str) -> Atlas:
        if self.child(child_id) is None:
            raise AtlasError("The selected subconcept no longer exists.")
        return replace(self, subconcepts=tuple(child for child in self.subconcepts if child.id != child_id),
                       information_entries=tuple(entry for entry in self.information_entries if entry.concept_id != child_id))

    def entries_for(self, concept_id: str | None) -> tuple[InformationEntry, ...]:
        return tuple(entry for entry in self.information_entries if entry.concept_id == concept_id)

    def with_entry(self, entry: InformationEntry) -> Atlas:
        old = next((item for item in self.information_entries if item.id == entry.id), None)
        if old is not None and old.concept_id != entry.concept_id:
            raise AtlasError("An information entry cannot change its owning concept.")
        entries = tuple(entry if item.id == entry.id else item for item in self.information_entries) if old else self.information_entries + (entry,)
        return replace(self, information_entries=entries)

    def without_entry(self, entry_id: str) -> Atlas:
        if not any(entry.id == entry_id for entry in self.information_entries):
            raise AtlasError("The information entry no longer exists.")
        return replace(self, information_entries=tuple(entry for entry in self.information_entries if entry.id != entry_id))

    def without_node(self, node_id: str, *, remove_children: bool = False) -> Atlas:
        if self.get(node_id) is None:
            raise AtlasError("The selected node no longer exists.")
        if self.children(node_id) and not remove_children:
            raise AtlasError("This node has subconcepts. Confirm deleting the whole cluster first.")
        removed = {node_id} | {child.id for child in self.children(node_id)}
        return replace(self, nodes=tuple(n for n in self.nodes if n.id != node_id),
                       subconcepts=tuple(child for child in self.subconcepts if child.parent_id != node_id),
                       information_entries=tuple(entry for entry in self.information_entries if entry.concept_id not in removed))

    def with_design(self, design: Design, layer_moves: dict | None = None, protocol_moves: dict | None = None) -> Atlas:
        """Apply explicit reassignments atomically; overlaps and orphan IDs fail."""
        layer_moves, protocol_moves = layer_moves or {}, protocol_moves or {}
        return Atlas(tuple(replace(n, layer=layer_moves.get(n.layer, n.layer),
                                   protocol=protocol_moves.get(n.protocol, n.protocol)) for n in self.nodes), design, self.subconcepts, self.information_entries, self.flows)

    def without_protocols(self) -> Atlas:
        """Clear optional metadata while preserving blocks and all geometry."""
        if not self.design.protocols:
            return self
        return Atlas(tuple(replace(n, protocol=None) for n in self.nodes), replace(self.design, protocols=()), self.subconcepts, self.information_entries, self.flows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": SCHEMA, "version": VERSION,
            "layout": LAYOUT, "center_depth": CENTER_DEPTH, "radial_bands": list(BANDS),
            "angular_slots": ANGULAR_SLOTS,
            "design": self.design.to_dict(),
            "nodes": [n.to_dict() for n in self.nodes],
            "subconcepts": [child.to_dict() for child in self.subconcepts],
            "information_entries": [entry.to_dict() for entry in self.information_entries],
            "flows": [flow.to_dict() for flow in self.flows],
        }

    @classmethod
    def from_dict(cls, data: Any) -> Atlas:
        if not isinstance(data, dict) or data.get("type") != SCHEMA:
            raise AtlasError("This is not a Cyber Atlas JSON document.")
        version = data.get("version")
        if type(version) is not int or not 1 <= version <= VERSION:
            raise AtlasError(f"Supported atlas file versions are 1 through {VERSION}.")
        if version < 11 and data.get("flows", []) != []:
            raise AtlasError("FlowNotes require atlas file version 11.")
        if version < 10 and data.get("information_entries", []) != []:
            raise AtlasError("Information entries require atlas file version 10.")
        if version < 9 and data.get("subconcepts", []) != []:
            raise AtlasError("Subconcepts require atlas file version 9.")
        if version == 4 and (
            data.get("sector_order") != list(PROTOCOLS) or data.get("radial_bands") != list(BANDS)
        ):
            raise AtlasError("This file uses a different grid. Import was stopped to preserve coordinates.")
        if version >= 5 and (
            data.get("layout") != ("equal-rings" if version == 5 else LAYOUT) or data.get("radial_bands") != list(BANDS)
            or type(data.get("center_depth")) is not int or data.get("center_depth") != CENTER_DEPTH
        ):
            raise AtlasError("This file uses an unsupported radial layout.")
        if version >= 6 and (type(data.get("angular_slots")) is not int or data.get("angular_slots") != ANGULAR_SLOTS):
            raise AtlasError("This file must use 16 angular slots per ring.")
        raw_nodes = data.get("nodes")
        if not isinstance(raw_nodes, list) or len(raw_nodes) > MAX_NODES:
            raise AtlasError(f"The file must contain a node list of at most {MAX_NODES:,} entries.")
        nodes = []
        legacy_slots: dict[tuple[int, int], int] = {}
        for index, raw in enumerate(raw_nodes, 1):
            if not isinstance(raw, dict):
                raise AtlasError(f"Node {index} must be an object.")
            try:
                node_id = raw["id"]
                # The HTML prototypes used integer IDs. Preserve them as strings.
                if version < 4 and type(node_id) is int:
                    node_id = str(node_id)
                node = Node(node_id, raw["name"], raw["layer"], raw["protocol"], raw["depth"], raw.get("notes", ""),
                            raw["slot"] if version >= 6 else 0, raw["span"] if version >= 6 else 1)
                if version < 8 and node.protocol is None:
                    raise AtlasError("Unassigned protocols require atlas file version 8.")
                if version < 5 and node.depth == CENTER_DEPTH:
                    raise AtlasError("Center is supported starting with atlas file version 5.")
                if version < 6:
                    slot = legacy_slots.get(node.position, 0)
                    if slot >= ANGULAR_SLOTS:
                        raise AtlasError(f"L{node.layer} / depth {node.depth} contains more than 16 legacy blocks. Move some to another radial depth in the older app before importing. No notes were imported or removed.")
                    node = replace(node, slot=slot)
                    legacy_slots[node.position] = slot + 1
            except KeyError as exc:
                raise AtlasError(f"Node {index} is missing {exc.args[0]!r}.") from exc
            nodes.append(node)
        design = Design.from_dict(data.get("design")) if version >= 7 else Design()
        if version == 7 and not design.protocols:
            raise AtlasError("Empty protocol lists require atlas file version 8.")
        children = []
        if version >= 9:
            raw_children = data.get("subconcepts")
            if not isinstance(raw_children, list) or len(raw_children) + len(nodes) > MAX_NODES:
                raise AtlasError("The file needs a valid subconcept list within the concept limit.")
            for index, raw in enumerate(raw_children, 1):
                if not isinstance(raw, dict):
                    raise AtlasError(f"Subconcept {index} must be an object.")
                try:
                    children.append(Subconcept(raw["id"], raw["parent_id"], raw["name"], raw.get("notes", ""),
                                               raw["orbit_slot"], raw["relationship"]))
                except KeyError as exc:
                    raise AtlasError(f"Subconcept {index} is missing {exc.args[0]!r}.") from exc
        entries = []
        if version >= 10:
            raw_entries = data.get("information_entries")
            if not isinstance(raw_entries, list) or len(raw_entries) > MAX_INFORMATION_ENTRIES:
                raise AtlasError("The file needs a valid information entry list within the entry limit.")
            for index, raw in enumerate(raw_entries, 1):
                if not isinstance(raw, dict):
                    raise AtlasError(f"Information entry {index} must be an object.")
                try:
                    entries.append(InformationEntry(raw["id"], raw["concept_id"], raw["title"], raw["body"]))
                except KeyError as exc:
                    raise AtlasError(f"Information entry {index} is missing {exc.args[0]!r}.") from exc
        raw_flows = data.get("flows") if version >= 11 else []
        if not isinstance(raw_flows, list) or len(raw_flows) > MAX_FLOWS:
            raise AtlasError(f"The file needs a flow list of at most {MAX_FLOWS} entries.")
        return cls(tuple(nodes), design, tuple(children), tuple(entries), tuple(FlowNote.from_dict(raw) for raw in raw_flows))


def example_atlas() -> Atlas:
    """Starter content mirrors the HTML prototype; every note is editable."""
    rows = (
        (1, "Ethernet", "Copper / fiber medium", 1, "Transmission media.\n\nLearning placeholder: explore the physical medium beneath Ethernet."),
        (2, "Ethernet", "Ethernet frame", 1, "Explore MAC addresses and local delivery.\n\nAdd an observation from your own lab."),
        (2, "ARP", "ARP resolution", 2, "Explore address resolution.\n\nWhat question would you ask before inspecting an ARP table?"),
        (3, "IPv4", "IP routing", 1, "Explore routing and next-hop decisions.\n\nRecord what you predict, then what you observe."),
        (3, "ICMP", "Ping / Echo", 2, "Explore network diagnostics.\n\nWhat can a response establish? What can it not establish?"),
        (4, "TCP", "TCP connection", 1, "Explore connection establishment.\n\nAdd a packet trace and your explanation here."),
        (4, "UDP", "UDP datagram", 1, "Explore datagram transport.\n\nCompare a TCP and a UDP observation from your own lab."),
        (7, "DNS", "DNS resolver", 2, "Explore name resolution.\n\nTrace one query from your application to a resolver."),
        (7, "HTTP", "Web server", 2, "Explore requests and responses.\n\nRecord a request, its response, and what you learned."),
        (7, "HTTPS", "Web application", 3, "Explore the relationship between HTTP and TLS.\n\nThis is a learning map, not a strict protocol taxonomy."),
        (7, "SSH", "OpenSSH server", 2, "## What am I investigating?\nRemote access and authentication.\n\n## Trace the dependencies\nWhat has to work before a login can succeed?\n\n## Evidence\nAdd a command, observation, or lab finding.\n\n## Still unknown\nWrite the next question here."),
        (7, "FTP", "FTP service", 2, "Explore file transfer.\n\nWhat happens before a file can be retrieved?"),
        (7, "SMB", "File share", 2, "Explore network file access.\n\nSeparate connectivity, authentication, and permissions in your notes."),
        (6, "TLS", "TLS encryption", 1, "Learning-map placement only.\n\nTLS is not being asserted to occupy a strict OSI layer here. Use this block to investigate its relationship with application protocols and transport."),
    )
    slots: dict[tuple[int, int], int] = {}
    nodes = []
    for i, (layer, protocol, name, depth, notes) in enumerate(rows, 1):
        slot = slots.get((layer, depth), 0)
        nodes.append(Node(str(i), name, layer, protocol, depth, notes, slot))
        slots[layer, depth] = slot + 1
    return Atlas(tuple(nodes))
