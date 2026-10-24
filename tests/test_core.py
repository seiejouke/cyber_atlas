from collections import Counter
from dataclasses import replace
from math import cos, pi, sin
import unittest
from unittest.mock import patch

from atlas.geometry import INNER_RADIUS, LAYER_HEIGHT, RADIAL_WIDTH, layout_meshes, wedge_mesh
from atlas.model import ANGULAR_SLOTS, Atlas, AtlasError, BANDS, BLOCK_SIZES, CENTER_DEPTH, Node, PROTOCOLS, example_atlas


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.atlas = example_atlas()
        self.node = self.atlas.get("11")

    def test_example_has_fourteen_distinct_notes(self):
        self.assertEqual(len(self.atlas.nodes), 14)
        self.assertEqual(len({n.id for n in self.atlas.nodes}), 14)
        self.assertTrue(all(n.span == 1 for n in self.atlas.nodes))

    def test_add_keeps_every_existing_node_and_mesh(self):
        added = Node.create("Another note", 7, "SSH", 2, slot=8, span=2)
        updated = self.atlas.with_node(added)
        self.assertEqual(len(updated.nodes), 15)
        self.assertEqual(len(self.atlas.nodes), 14)
        before, after = layout_meshes(self.atlas.nodes), layout_meshes(updated.nodes)
        for node in self.atlas.nodes:
            self.assertEqual(updated.get(node.id), node)
            self.assertEqual(before[node.id], after[node.id])

    def test_duplicate_coordinates_allowed_at_different_slots(self):
        other = replace(self.node, id="other", slot=8)
        self.assertEqual(Atlas((self.node, other)).nodes[1].coordinate, self.node.coordinate)

    def test_protocol_is_metadata(self):
        updated = self.atlas.with_node(replace(self.node, protocol="DNS"))
        self.assertEqual(layout_meshes(updated.nodes), layout_meshes(self.atlas.nodes))

    def test_edit_keeps_identity_order_and_placement(self):
        changed = replace(self.node, name="Edited", notes="A finding")
        updated = self.atlas.with_node(changed)
        self.assertEqual(updated.get(self.node.id), changed)
        self.assertEqual([n.id for n in updated.nodes], [n.id for n in self.atlas.nodes])
        self.assertEqual(changed.slot, self.node.slot)

    def test_move_changes_only_selected_note(self):
        changed = replace(self.node, layer=5, depth=CENTER_DEPTH, slot=12, span=2)
        updated = self.atlas.with_node(changed)
        for node in self.atlas.nodes:
            self.assertEqual(updated.get(node.id), changed if node.id == changed.id else node)
        self.assertEqual([n.id for n in updated.nodes], [n.id for n in self.atlas.nodes])

    def test_overlap_rejected_even_with_different_protocol(self):
        with self.assertRaisesRegex(AtlasError, "overlaps"):
            self.atlas.with_node(replace(self.node, id="overlap", protocol="Other"))

    def test_growing_block_into_neighbor_is_rejected(self):
        a, b = Node("a", "A", 7, "SSH", 0), Node("b", "B", 7, "Other", 0, slot=1)
        atlas = Atlas((a, b))
        with self.assertRaisesRegex(AtlasError, "overlaps"):
            atlas.with_node(replace(a, span=2))
        self.assertEqual(atlas.nodes, (a, b))

    def test_resize_into_free_adjacent_slots(self):
        a = Node("a", "A", 7, "SSH", 0, slot=4)
        atlas = Atlas((a,)).with_node(replace(a, span=4))
        self.assertEqual(atlas.get("a").occupied_slots, frozenset((4, 5, 6, 7)))

    def test_same_slots_allowed_in_different_depths_and_layers(self):
        a = Node("a", "A", 7, "SSH", 0, span=4)
        self.assertEqual(len(Atlas((a, replace(a, id="b", depth=1), replace(a, id="c", layer=6))).nodes), 3)

    def test_wrapping_blocks_reserve_slots_across_zero(self):
        node = Node("wrap", "Wrap", 7, "SSH", 0, slot=15, span=2)
        atlas = Atlas((node,))
        self.assertEqual(node.occupied_slots, frozenset((15, 0)))
        self.assertNotIn(0, atlas.free_starts(7, 0))
        self.assertNotIn(15, atlas.free_starts(7, 0))
        self.assertEqual(atlas.next_free(7, 0, start=15), 1)

    def test_full_ring_has_no_free_start_and_does_not_move_outward(self):
        atlas = Atlas(tuple(Node(str(i), str(i), 7, "SSH", 0, slot=i) for i in range(16)))
        self.assertIsNone(atlas.next_free(7, 0))
        self.assertEqual(atlas.next_free(7, 1), 0)
        self.assertEqual(len(atlas.nodes), 16)

    def test_fragmented_free_space_cannot_hold_large_block(self):
        atlas = Atlas(tuple(Node(str(i), str(i), 7, "SSH", 0, slot=i) for i in range(0, 16, 2)))
        self.assertEqual(len(atlas.free_starts(7, 0)), 8)
        self.assertIsNone(atlas.next_free(7, 0, 2))

    def test_delete_leaves_reusable_hole_and_keeps_neighbors(self):
        nodes = tuple(Node(str(i), str(i), 7, "SSH", 0, slot=i) for i in range(4))
        atlas = Atlas(nodes).without_node("1")
        self.assertEqual(atlas.next_free(7, 0), 1)
        self.assertEqual(atlas.get("2").slot, 2)
        self.assertEqual(atlas.get("3").slot, 3)
        self.assertIsNone(atlas.get("1"))

    def test_free_start_excludes_selected_note_for_resize(self):
        node = Node("a", "A", 7, "SSH", 0, slot=3, span=2)
        atlas = Atlas((node,))
        self.assertNotIn(3, atlas.free_starts(7, 0, 4))
        self.assertIn(3, atlas.free_starts(7, 0, 4, exclude_id="a"))

    def test_center_uses_same_explicit_size_and_placement(self):
        a = Node("a", "A", 2, "Other", CENTER_DEPTH, slot=2, span=2)
        b = replace(a, id="b", slot=8, span=1)
        self.assertEqual(Atlas.from_dict(Atlas((a, b)).to_dict()).nodes, (a, b))

    def test_explicit_full_block_only_fits_empty_position(self):
        node = Node("full", "Full", 3, "IPv4", CENTER_DEPTH, slot=7, span=16)
        self.assertEqual(len(node.occupied_slots), 16)
        self.assertEqual(Atlas((node,)).free_starts(3, CENTER_DEPTH), ())
        self.assertEqual(Atlas().free_starts(3, CENTER_DEPTH, 16), tuple(range(16)))

    def test_duplicate_id_rejected(self):
        with self.assertRaisesRegex(AtlasError, "Duplicate"):
            Atlas((self.node, replace(self.node, slot=8)))

    def test_missing_delete_rejected(self):
        with self.assertRaises(AtlasError):
            self.atlas.without_node("missing")

    def test_invalid_fields_rejected(self):
        fields = ({"layer": 0}, {"layer": ""}, {"layer": True}, {"depth": -2}, {"depth": 5},
                  {"depth": False}, {"depth": 1.0}, {"name": " "}, {"name": "x" * 121}, {"name": "a\nb"},
                  {"protocol": ""}, {"notes": None}, {"notes": "\x00"}, {"id": 4},
                  {"slot": -1}, {"slot": 16}, {"slot": True}, {"slot": 1.5},
                  {"span": 0}, {"span": 3}, {"span": 32}, {"span": True}, {"span": 2.0})
        for field in fields:
            with self.subTest(field=field), self.assertRaises(AtlasError):
                replace(self.node, **field)

    def test_placement_queries_validate_coordinates(self):
        for args in ((0, 0, 1), (7, 5, 1), (7, 0, 3), (True, 0, 1)):
            with self.subTest(args=args), self.assertRaises(AtlasError):
                Atlas().free_starts(*args)

    def test_note_limit_rejected_without_mutation(self):
        with patch("atlas.model.MAX_NODES", 14):
            with self.assertRaises(AtlasError):
                self.atlas.with_node(Node.create("Extra", 5, "Other", 0))
        self.assertEqual(len(self.atlas.nodes), 14)

    def test_roundtrip_keeps_sizes_slots_gaps_and_order(self):
        nodes = (Node("z", "Z", 7, "SSH", 2, slot=11, span=4), Node("a", "A", 7, "SSH", 2, slot=2, span=2))
        atlas = Atlas(nodes)
        self.assertEqual(Atlas.from_dict(atlas.to_dict()), atlas)
        self.assertEqual(atlas.to_dict()["version"], 8)
        self.assertEqual(atlas.to_dict()["angular_slots"], 16)

    def test_empty_roundtrip(self):
        self.assertEqual(Atlas.from_dict(Atlas().to_dict()), Atlas())

    def legacy(self, version, nodes=None):
        rows = [n.to_dict() for n in (nodes or self.atlas.nodes)]
        for row in rows:
            row.pop("slot")
            row.pop("span")
            if version < 4:
                row["id"] = int(row["id"])
        return {"type": "cyber-knowledge-atlas", "version": version, "sector_order": list(PROTOCOLS),
                "radial_bands": list(BANDS), "layout": "equal-rings", "center_depth": -1, "nodes": rows}

    def test_versions_one_through_five_preserve_every_note(self):
        for version in range(1, 6):
            with self.subTest(version=version):
                restored = Atlas.from_dict(self.legacy(version))
                self.assertEqual(restored, self.atlas)
                self.assertEqual(Atlas.from_dict(restored.to_dict()), restored)

    def test_v5_center_migrates_to_compact_slots(self):
        nodes = tuple(Node(str(i), str(i), 3, "Other", CENTER_DEPTH, slot=i) for i in range(3))
        restored = Atlas.from_dict(self.legacy(5, nodes))
        self.assertEqual(restored.nodes, nodes)

    def test_v5_dense_ring_is_rejected_without_dropping_notes(self):
        data = self.legacy(5)
        data["nodes"] = [{"id": str(i), "name": str(i), "layer": 7, "protocol": "SSH", "depth": 2} for i in range(17)]
        with self.assertRaisesRegex(AtlasError, "more than 16"):
            Atlas.from_dict(data)
        self.assertEqual(len(data["nodes"]), 17)

    def test_old_formats_cannot_introduce_center(self):
        for version in range(1, 5):
            data = self.legacy(version)
            data["nodes"][0]["depth"] = CENTER_DEPTH
            with self.subTest(version=version), self.assertRaises(AtlasError):
                Atlas.from_dict(data)

    def test_incompatible_legacy_grid_rejected(self):
        data = self.legacy(4)
        data["sector_order"].reverse()
        with self.assertRaisesRegex(AtlasError, "different grid"):
            Atlas.from_dict(data)

    def test_incompatible_layout_metadata_rejected(self):
        for key, value in (("layout", "unknown"), ("center_depth", -1.0), ("radial_bands", []),
                           ("angular_slots", 32), ("angular_slots", 16.0)):
            data = self.atlas.to_dict()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(AtlasError):
                Atlas.from_dict(data)

    def test_fixed_slot_formats_require_size_and_slot(self):
        for version in (6, 7, 8):
            for key in ("slot", "span"):
                data = self.atlas.to_dict()
                data["version"] = version
                data["nodes"][0].pop(key)
                with self.subTest(version=version, key=key), self.assertRaises(AtlasError):
                    Atlas.from_dict(data)

    def test_fixed_slot_formats_reject_overlapping_import(self):
        for version in (6, 7, 8):
            data = self.atlas.to_dict()
            data["version"] = version
            data["nodes"].append({**data["nodes"][0], "id": "duplicate-placement"})
            with self.subTest(version=version), self.assertRaisesRegex(AtlasError, "overlaps"):
                Atlas.from_dict(data)

    def test_unknown_format_rejected(self):
        for data in (None, [], {}, {"type": "other", "version": 6},
                     {"type": "cyber-knowledge-atlas", "version": True},
                     {"type": "cyber-knowledge-atlas", "version": 99}):
            with self.subTest(data=data), self.assertRaises(AtlasError):
                Atlas.from_dict(data)


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.node = Node("geometry", "Geometry", 7, "SSH", 2)

    def assert_closed(self, mesh):
        directed = Counter()
        for face in mesh.faces:
            self.assertEqual(len(face), len(set(face)))
            for i, a in enumerate(face):
                directed[a, face[(i + 1) % len(face)]] += 1
        for (a, b), count in directed.items():
            self.assertEqual(count, 1)
            self.assertEqual(directed[b, a], 1)

    @staticmethod
    def volume(mesh):
        total = 0
        for face in mesh.faces:
            a = mesh.points[face[0]]
            for i in range(1, len(face) - 1):
                b, c = mesh.points[face[i]], mesh.points[face[i + 1]]
                total += (a[0] * (b[1] * c[2] - b[2] * c[1])
                          + a[1] * (b[2] * c[0] - b[0] * c[2])
                          + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
        return total

    def test_all_sizes_and_wrapping_meshes_are_closed(self):
        for depth in range(CENTER_DEPTH, 5):
            for span in BLOCK_SIZES.values():
                for slot in (0, 7, 15):
                    with self.subTest(depth=depth, span=span, slot=slot):
                        self.assert_closed(wedge_mesh(replace(self.node, depth=depth, span=span, slot=slot)))

    def test_block_occupies_chosen_fraction_of_ring_or_center(self):
        for depth in (CENTER_DEPTH, 0, 2, 4):
            for span in BLOCK_SIZES.values():
                mesh = wedge_mesh(replace(self.node, depth=depth, slot=15, span=span))
                inner = (depth + 1) * RADIAL_WIDTH
                expected = pi * ((inner + RADIAL_WIDTH) ** 2 - inner ** 2) * LAYER_HEIGHT * span / 16
                with self.subTest(depth=depth, span=span):
                    self.assertAlmostEqual(self.volume(mesh), expected, delta=expected * .001)

    def test_centers_follow_saved_slot_and_span(self):
        for slot in (0, 7, 15):
            for span in (1, 2, 4, 8):
                mesh = wedge_mesh(replace(self.node, slot=slot, span=span))
                angle = -pi / 2 + (slot + span / 2) * 2 * pi / 16
                radius = INNER_RADIUS + 2.5 * RADIAL_WIDTH
                self.assertAlmostEqual(mesh.center[0], radius * cos(angle))
                self.assertAlmostEqual(mesh.center[1], radius * sin(angle))

    def test_mixed_sizes_do_not_fill_unused_circle(self):
        nodes = (replace(self.node, id="a", span=2), replace(self.node, id="b", slot=2), replace(self.node, id="c", slot=3))
        meshes = layout_meshes(nodes)
        total = sum(self.volume(m) for m in meshes.values())
        full = self.volume(wedge_mesh(replace(self.node, span=16)))
        self.assertAlmostEqual(total, full / 4)

    def test_add_delete_move_do_not_reposition_or_resize_neighbors(self):
        a = self.node
        b = replace(a, id="b", slot=4, span=2)
        atlas = Atlas((a, b))
        before = layout_meshes(atlas.nodes)
        extra = replace(a, id="extra", slot=8, span=4)
        added = atlas.with_node(extra)
        for node in atlas.nodes:
            self.assertEqual(before[node.id], layout_meshes(added.nodes)[node.id])
        deleted = added.without_node(a.id)
        self.assertEqual(before[b.id], layout_meshes(deleted.nodes)[b.id])
        moved = deleted.with_node(replace(extra, depth=3))
        self.assertEqual(before[b.id], layout_meshes(moved.nodes)[b.id])

    def test_resizing_changes_only_that_block(self):
        a, b = self.node, replace(self.node, id="b", slot=8)
        before = layout_meshes((a, b))
        after = layout_meshes((replace(a, span=4), b))
        self.assertNotEqual(before[a.id], after[a.id])
        self.assertEqual(before[b.id], after[b.id])

    def test_list_order_does_not_change_geometry(self):
        a, b = self.node, replace(self.node, id="b", slot=8)
        self.assertEqual(layout_meshes((a, b)), layout_meshes((b, a)))

    def test_equal_layer_heights(self):
        for layer in range(1, 8):
            mesh = wedge_mesh(replace(self.node, layer=layer))
            heights = [p[2] for p in mesh.points]
            self.assertAlmostEqual(max(heights) - min(heights), LAYER_HEIGHT)
            self.assertAlmostEqual(mesh.center[2], layer - 4)

    def test_equal_radial_widths_including_center(self):
        previous_outer = 0
        for depth in range(CENTER_DEPTH, 5):
            mesh = wedge_mesh(replace(self.node, depth=depth))
            radii = [(x*x + y*y) ** .5 for x, y, _ in mesh.points]
            self.assertAlmostEqual(min(radii), previous_outer)
            self.assertAlmostEqual(max(radii) - min(radii), RADIAL_WIDTH)
            previous_outer = max(radii)

    def test_neighbor_layers_share_boundaries(self):
        lower = wedge_mesh(replace(self.node, layer=3))
        upper = wedge_mesh(replace(self.node, layer=4))
        self.assertEqual(max(p[2] for p in lower.points), min(p[2] for p in upper.points))

    def test_more_arc_segments_preserve_coordinates(self):
        a, b = wedge_mesh(self.node, 4), wedge_mesh(self.node, 24)
        self.assertEqual(a.center, b.center)
        self.assertGreater(len(b.points), len(a.points))

    def test_invalid_segment_counts_rejected(self):
        for value in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                wedge_mesh(self.node, value)
        with self.assertRaises(ValueError):
            wedge_mesh(replace(self.node, span=16), 2)


if __name__ == "__main__":
    unittest.main()
