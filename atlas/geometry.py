"""Convert a logical coordinate into a closed, wedge-shaped 3D mesh.

Z = OSI layer, angle = protocol sector, radius = detail band.
Cells have equal height, angular width and radial width. Outer cells have
larger physical volumes: equal radial increments do not mean equal volumes.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin

from .model import Node, PROTOCOLS

LAYER_HEIGHT = 1.0
INNER_RADIUS = 0.70
RADIAL_WIDTH = 0.80
Z_BASE = -3.5
SECTOR_ANGLE = 2 * pi / len(PROTOCOLS)
ARC_SEGMENTS = 12

Point = tuple[float, float, float]
Face = tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Mesh:
    points: tuple[Point, ...]
    faces: tuple[Face, ...]
    center: Point
    label_anchor: Point


def wedge_mesh(node: Node, segments: int = ARC_SEGMENTS) -> Mesh:
    if type(segments) is not int or segments < 1:
        raise ValueError("A curved edge needs at least one segment.")
    start = -pi / 2 + PROTOCOLS.index(node.protocol) * SECTOR_ANGLE
    inner = INNER_RADIUS + node.depth * RADIAL_WIDTH
    outer = inner + RADIAL_WIDTH
    bottom = Z_BASE + (node.layer - 1) * LAYER_HEIGHT
    top = bottom + LAYER_HEIGHT
    points: list[Point] = []
    for step in range(segments + 1):
        angle = start + step * SECTOR_ANGLE / segments
        # Four corners of each radial cross-section, in a consistent order.
        for radius, height in ((inner, bottom), (outer, bottom), (outer, top), (inner, top)):
            points.append((radius * cos(angle), radius * sin(angle), height))
    faces: list[Face] = []
    for step in range(segments):
        a, b = step * 4, (step + 1) * 4
        faces.extend(((a, b, b + 1, a + 1),             # bottom
                      (a + 1, b + 1, b + 2, a + 2),   # outer curve
                      (a + 3, a + 2, b + 2, b + 3),   # top
                      (a, a + 3, b + 3, b)))          # inner curve
    faces.append((0, 1, 2, 3))
    last = segments * 4
    faces.append((last, last + 3, last + 2, last + 1))
    mid_angle = start + SECTOR_ANGLE / 2
    mid_radius = (inner + outer) / 2
    x, y = mid_radius * cos(mid_angle), mid_radius * sin(mid_angle)
    return Mesh(tuple(points), tuple(faces), (x, y, (bottom + top) / 2), (x, y, top - 0.001))
