"""Equal-width radial positions with explicitly sized, fixed angular blocks.

Z = layer order, radius = detail band, angle = saved start slot and block span.
Only occupied slots are rendered. Center uses the same sizing rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, cos, pi, sin

from .model import ANGULAR_SLOTS, CENTER_DEPTH, Design, Node

LAYER_HEIGHT = 1.0
RADIAL_WIDTH = 0.80
INNER_RADIUS = RADIAL_WIDTH
Z_BASE = -3.5
ARC_SEGMENTS = 128  # Resolution of a full circle, shared by the ring's blocks.

Point = tuple[float, float, float]
Face = tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Mesh:
    points: tuple[Point, ...]
    faces: tuple[Face, ...]
    center: Point
    label_anchor: Point


def layout_meshes(nodes: tuple[Node, ...], design: Design = Design()) -> dict[str, Mesh]:
    """Each mesh depends only on its own saved coordinates and size."""
    return {node.id: wedge_mesh(node, design=design) for node in nodes}


def node_position(node: Node, design: Design = Design()) -> Point:
    """Locate a note at the midpoint of its saved radial/angular footprint.

    Both render modes share these coordinates, so changing the presentation
    does not alter a note's layer, occupied slots, or radial detail level.
    """
    inner = INNER_RADIUS + node.depth * RADIAL_WIDTH if node.depth != CENTER_DEPTH else 0.0
    outer = inner + RADIAL_WIDTH
    angle = -pi / 2 + (node.slot + node.span / 2) * 2 * pi / ANGULAR_SLOTS
    radius = (inner + outer) / 2
    bottom = design.z_base + design.layer_index(node.layer) * LAYER_HEIGHT
    return radius * cos(angle), radius * sin(angle), bottom + LAYER_HEIGHT / 2


def wedge_mesh(node: Node, segments: int | None = None, *, design: Design = Design()) -> Mesh:
    if segments is None:
        segments = max(1, ceil(ARC_SEGMENTS * node.span / ANGULAR_SLOTS))
    if type(segments) is not int or segments < 1 or (node.span == ANGULAR_SLOTS and segments < 3):
        raise ValueError("A curved edge needs segments; a full circle needs at least three.")
    full = node.span == ANGULAR_SLOTS
    span = 2 * pi * node.span / ANGULAR_SLOTS
    start = -pi / 2 + node.slot * 2 * pi / ANGULAR_SLOTS
    inner = INNER_RADIUS + node.depth * RADIAL_WIDTH if node.depth != CENTER_DEPTH else 0.0
    outer = inner + RADIAL_WIDTH
    bottom = design.z_base + design.layer_index(node.layer) * LAYER_HEIGHT
    top = bottom + LAYER_HEIGHT
    sections = segments if full else segments + 1
    points: list[Point] = []
    faces: list[Face] = []
    if node.depth == CENTER_DEPTH:
        # Shared axis vertices avoid degenerate quads and coincident edges.
        points.extend(((0.0, 0.0, bottom), (0.0, 0.0, top)))
        for step in range(sections):
            angle = start + step * span / segments
            x, y = outer * cos(angle), outer * sin(angle)
            points.extend(((x, y, bottom), (x, y, top)))
        for step in range(segments):
            a = 2 + step * 2
            b = 2 + ((step + 1) % sections) * 2
            faces.extend(((0, b, a), (1, a + 1, b + 1), (a, b, b + 1, a + 1)))
        if not full:
            last = 2 + segments * 2
            faces.extend(((0, 2, 3, 1), (0, 1, last + 1, last)))
    else:
        for step in range(sections):
            angle = start + step * span / segments
            for radius, height in ((inner, bottom), (outer, bottom), (outer, top), (inner, top)):
                points.append((radius * cos(angle), radius * sin(angle), height))
        for step in range(segments):
            a, b = step * 4, ((step + 1) % sections) * 4
            faces.extend(((a, b, b + 1, a + 1),
                          (a + 1, b + 1, b + 2, a + 2),
                          (a + 3, a + 2, b + 2, b + 3),
                          (a, a + 3, b + 3, b)))
        if not full:
            last = segments * 4
            faces.extend(((0, 1, 2, 3), (last, last + 3, last + 2, last + 1)))
    center = node_position(node, design)
    return Mesh(tuple(points), tuple(faces), center, (center[0], center[1], top - 0.001))
