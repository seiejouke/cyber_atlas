from collections import Counter
from dataclasses import replace
from math import cos, pi, sin
import unittest

from atlas.geometry import INNER_RADIUS, LAYER_HEIGHT, RADIAL_WIDTH, SECTOR_ANGLE, wedge_mesh
from atlas.model import Atlas, AtlasError, CAPACITY, Node, PROTOCOLS, example_atlas


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.atlas = example_atlas()
        self.node = self.atlas.get("11")

    def test_example_has_fourteen_distinct_nodes(self):
        self.assertEqual(len(self.atlas.nodes), 14)
        self.assertEqual(len({n.coordinate for n in self.atlas.nodes}), 14)

    def test_add_does_not_mutate_original(self):
        node = Node.create("New note", 5, "Other", 0)
        updated = self.atlas.with_node(node)
        self.assertEqual(len(updated.nodes), 15)
        self.assertEqual(len(self.atlas.nodes), 14)

    def test_edit_preserves_identity(self):
        changed = replace(self.node, name="Edited name", notes="A finding")
        updated = self.atlas.with_node(changed)
        self.assertEqual(len(updated.nodes), 14)
        self.assertEqual(updated.get("11").notes, "A finding")

    def test_move_does_not_rearrange_other_nodes(self):
        moved = replace(self.node, layer=5, protocol="Other", depth=4)
        updated = self.atlas.with_node(moved)
        self.assertEqual(updated.get("11").coordinate, (5, "Other", 4))
        for node in self.atlas.nodes:
            if node.id != "11":
                self.assertEqual(node, updated.get(node.id))

    def test_duplicate_coordinate_rejected(self):
        with self.assertRaisesRegex(AtlasError, "already occupied"):
            self.atlas.with_node(Node.create("Duplicate", 7, "SSH", 2))

    def test_move_into_existing_coordinate_rejected(self):
        with self.assertRaises(AtlasError):
            self.atlas.with_node(replace(self.node, protocol="DNS"))

    def test_duplicate_id_rejected(self):
        with self.assertRaises(AtlasError):
            Atlas((self.node, replace(self.node, depth=4)))

    def test_delete_frees_coordinate(self):
        updated = self.atlas.without_node("11")
        self.assertEqual(len(updated.nodes), 13)
        self.assertIsNone(updated.get("11"))
        updated.with_node(Node.create("Replacement", 7, "SSH", 2))

    def test_delete_missing_rejected(self):
        with self.assertRaises(AtlasError):
            self.atlas.without_node("missing")

    def test_invalid_node_fields_rejected(self):
        bad_fields = ({"layer": 0}, {"layer": 8}, {"layer": True}, {"depth": -1}, {"depth": 5},
                      {"depth": 1.0}, {"name": "  "}, {"name": "x" * 121}, {"name": "a\nb"},
                      {"protocol": "Unknown"}, {"notes": None}, {"notes": "\x00"}, {"id": 4})
        for fields in bad_fields:
            with self.subTest(fields=fields):
                with self.assertRaises(AtlasError):
                    replace(self.node, **fields)

    def test_next_free_prefers_current_sector(self):
        self.assertEqual(self.atlas.next_free(7, "SSH"), (7, "SSH", 0))

    def test_full_grid_has_595_positions(self):
        atlas = Atlas(tuple(Node(f"{l}-{p}-{d}", "Filled", l, p, d)
                            for l in range(1, 8) for p in PROTOCOLS for d in range(5)))
        self.assertEqual(len(atlas.nodes), CAPACITY)
        self.assertEqual(CAPACITY, 595)
        self.assertIsNone(atlas.next_free())

    def test_roundtrip(self):
        self.assertEqual(Atlas.from_dict(self.atlas.to_dict()), self.atlas)

    def test_empty_roundtrip(self):
        self.assertEqual(Atlas.from_dict(Atlas().to_dict()), Atlas())

    def test_original_html_formats_supported(self):
        for version in (1, 2, 3):
            data = {"type": "cyber-knowledge-atlas", "version": version,
                    "nodes": [{**n.to_dict(), "id": int(n.id)} for n in self.atlas.nodes]}
            self.assertEqual(Atlas.from_dict(data), self.atlas)

    def test_sector_reordering_rejected(self):
        data = self.atlas.to_dict()
        data["sector_order"].reverse()
        with self.assertRaisesRegex(AtlasError, "different grid"):
            Atlas.from_dict(data)

    def test_unknown_format_rejected(self):
        for data in (None, [], {}, {"type": "other", "version": 4},
                     {"type": "cyber-knowledge-atlas", "version": True},
                     {"type": "cyber-knowledge-atlas", "version": 99}):
            with self.subTest(data=data), self.assertRaises(AtlasError):
                Atlas.from_dict(data)

    def test_import_does_not_silently_drop_bad_nodes(self):
        data = self.atlas.to_dict()
        data["nodes"].append({"name": "broken"})
        with self.assertRaises(AtlasError):
            Atlas.from_dict(data)


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.node = Node("geometry", "Geometry", 7, "SSH", 2)

    def test_mesh_is_closed_and_consistently_wound(self):
        mesh = wedge_mesh(self.node)
        directed = Counter()
        for face in mesh.faces:
            for i, a in enumerate(face):
                directed[a, face[(i + 1) % len(face)]] += 1
        for (a, b), count in directed.items():
            self.assertEqual(count, 1)
            self.assertEqual(directed[b, a], 1)

    def test_equal_layer_heights(self):
        for layer in range(1, 8):
            mesh = wedge_mesh(replace(self.node, layer=layer))
            heights = [p[2] for p in mesh.points]
            self.assertAlmostEqual(max(heights) - min(heights), LAYER_HEIGHT)
            self.assertAlmostEqual(mesh.center[2], layer - 4)

    def test_equal_radial_widths(self):
        for depth in range(5):
            mesh = wedge_mesh(replace(self.node, depth=depth))
            radii = [(x*x + y*y) ** .5 for x, y, z in mesh.points]
            self.assertAlmostEqual(max(radii) - min(radii), RADIAL_WIDTH)
            self.assertAlmostEqual(min(radii), INNER_RADIUS + depth * RADIAL_WIDTH)

    def test_sectors_have_equal_angles(self):
        for i, protocol in enumerate(PROTOCOLS):
            mesh = wedge_mesh(replace(self.node, protocol=protocol))
            angle = -pi / 2 + (i + .5) * SECTOR_ANGLE
            radius = INNER_RADIUS + 2.5 * RADIAL_WIDTH
            self.assertAlmostEqual(mesh.center[0], radius * cos(angle))
            self.assertAlmostEqual(mesh.center[1], radius * sin(angle))

    def test_neighbor_layers_share_boundaries(self):
        lower = wedge_mesh(replace(self.node, layer=3))
        upper = wedge_mesh(replace(self.node, layer=4))
        self.assertEqual(max(p[2] for p in lower.points), min(p[2] for p in upper.points))

    def test_more_arc_segments_preserve_coordinates(self):
        a, b = wedge_mesh(self.node, 4), wedge_mesh(self.node, 24)
        self.assertEqual(a.center, b.center)
        self.assertGreater(len(b.points), len(a.points))

    def test_invalid_segment_count_rejected(self):
        for value in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                wedge_mesh(self.node, value)


if __name__ == "__main__":
    unittest.main()
