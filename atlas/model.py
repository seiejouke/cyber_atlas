"""Knowledge and coordinates. No GUI or rendering dependencies live here."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

LAYERS = ("Physical", "Data Link", "Network", "Transport", "Session", "Presentation", "Application")
# This ordering is part of the file format. Reordering it would move existing blocks.
PROTOCOLS = (
    "Ethernet", "ARP", "IPv4", "IPv6", "ICMP", "TCP", "UDP", "DNS", "HTTP",
    "HTTPS", "SSH", "FTP", "SMB", "TLS", "DHCP", "Wi-Fi", "Other",
)
BANDS = ("Overview", "Protocol function", "Service", "Implementation", "Detailed example")
COLORS = ("#65b6a1", "#65b6a1", "#9c8bdb", "#70cbd8", "#8ca9da", "#cb96ba", "#edbb69")
CAPACITY = len(LAYERS) * len(PROTOCOLS) * len(BANDS)
SCHEMA = "cyber-knowledge-atlas"
VERSION = 4


class AtlasError(ValueError):
    """An invalid note, coordinate, or atlas file."""


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    name: str
    layer: int
    protocol: str
    depth: int
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id or len(self.id) > 100:
            raise AtlasError("A node needs a nonempty ID of at most 100 characters.")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 120:
            raise AtlasError("Use a name between 1 and 120 characters.")
        if any(ord(c) < 32 for c in self.name):
            raise AtlasError("The name must be a single line without control characters.")
        if type(self.layer) is not int or not 1 <= self.layer <= len(LAYERS):
            raise AtlasError("The OSI layer must be an integer from 1 to 7.")
        if not isinstance(self.protocol, str) or self.protocol not in PROTOCOLS:
            raise AtlasError("Choose one of the existing protocol sectors.")
        if type(self.depth) is not int or not 0 <= self.depth < len(BANDS):
            raise AtlasError("The radial band must be an integer from 0 to 4.")
        if not isinstance(self.notes, str) or len(self.notes) > 100_000:
            raise AtlasError("Notes must be text, with at most 100,000 characters.")
        if "\x00" in self.notes:
            raise AtlasError("Notes cannot contain a null character.")

    @property
    def coordinate(self) -> tuple[int, str, int]:
        return self.layer, self.protocol, self.depth

    @classmethod
    def create(cls, name: str, layer: int, protocol: str, depth: int, notes: str = "") -> Node:
        return cls(uuid4().hex, name.strip(), layer, protocol, depth, notes)

    def to_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in ("id", "name", "layer", "protocol", "depth", "notes")}


@dataclass(frozen=True, slots=True)
class Atlas:
    nodes: tuple[Node, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.nodes, tuple) or not all(isinstance(n, Node) for n in self.nodes):
            raise AtlasError("An atlas contains a tuple of valid nodes.")
        if len(self.nodes) > CAPACITY:
            raise AtlasError(f"This grid holds at most {CAPACITY} occupied coordinates.")
        ids: set[str] = set()
        coords: set[tuple[int, str, int]] = set()
        for node in self.nodes:
            if node.id in ids:
                raise AtlasError(f"Duplicate node ID: {node.id}")
            if node.coordinate in coords:
                raise AtlasError(f"Coordinate already occupied: L{node.layer} / {node.protocol} / band {node.depth}.")
            ids.add(node.id)
            coords.add(node.coordinate)

    def get(self, node_id: str | None) -> Node | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def with_node(self, node: Node) -> Atlas:
        """Return a validated copy; never mutate the current document on failure."""
        previous = self.get(node.id)
        if previous is None:
            return Atlas(self.nodes + (node,))
        return Atlas(tuple(node if old.id == node.id else old for old in self.nodes))

    def without_node(self, node_id: str) -> Atlas:
        if self.get(node_id) is None:
            raise AtlasError("The selected node no longer exists.")
        return Atlas(tuple(n for n in self.nodes if n.id != node_id))

    def next_free(self, layer: int = 7, protocol: str = "SSH") -> tuple[int, str, int] | None:
        """Prefer the current protocol/layer, then look through the remaining grid."""
        if type(layer) is not int or not 1 <= layer <= 7 or protocol not in PROTOCOLS:
            raise AtlasError("Choose a valid layer and protocol when finding a free coordinate.")
        occupied = {n.coordinate for n in self.nodes}
        preferred = [(layer, protocol, d) for d in range(len(BANDS))]
        all_coords = [(l, p, d) for l in range(7, 0, -1) for p in PROTOCOLS for d in range(5)]
        return next((c for c in preferred + all_coords if c not in occupied), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": SCHEMA, "version": VERSION,
            "sector_order": list(PROTOCOLS), "radial_bands": list(BANDS),
            "nodes": [n.to_dict() for n in self.nodes],
        }

    @classmethod
    def from_dict(cls, data: Any) -> Atlas:
        if not isinstance(data, dict) or data.get("type") != SCHEMA:
            raise AtlasError("This is not a Cyber Atlas JSON document.")
        version = data.get("version")
        if type(version) is not int or version not in (1, 2, 3, 4):
            raise AtlasError("Supported atlas file versions are 1, 2, 3 and 4.")
        if version == 4 and (
            data.get("sector_order") != list(PROTOCOLS) or data.get("radial_bands") != list(BANDS)
        ):
            raise AtlasError("This file uses a different grid. Import was stopped to preserve coordinates.")
        raw_nodes = data.get("nodes")
        if not isinstance(raw_nodes, list) or len(raw_nodes) > CAPACITY:
            raise AtlasError(f"The file must contain a node list of at most {CAPACITY} entries.")
        nodes = []
        for index, raw in enumerate(raw_nodes, 1):
            if not isinstance(raw, dict):
                raise AtlasError(f"Node {index} must be an object.")
            try:
                node_id = raw["id"]
                # The HTML prototypes used integer IDs. Preserve them as strings.
                if version < 4 and type(node_id) is int:
                    node_id = str(node_id)
                node = Node(node_id, raw["name"], raw["layer"], raw["protocol"], raw["depth"], raw.get("notes", ""))
            except KeyError as exc:
                raise AtlasError(f"Node {index} is missing {exc.args[0]!r}.") from exc
            nodes.append(node)
        return cls(tuple(nodes))


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
    return Atlas(tuple(Node(str(i), name, layer, protocol, depth, notes)
                       for i, (layer, protocol, name, depth, notes) in enumerate(rows, 1)))
