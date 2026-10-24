"""Presentation-independent coordinates for the alternative Nodes view."""
from dataclasses import replace
from math import atan2, hypot, pi
import unittest

from atlas.geometry import RADIAL_WIDTH, adjacent_node_pairs, layout_meshes, node_position
from atlas.model import ANGULAR_SLOTS, BLOCK_SIZES, CENTER_DEPTH, Design, Layer, Node


class NodePositionTests(unittest.TestCase):
    def test_node_positions_share_saved_block_centers(self):
        nodes = tuple(Node(f"{depth}-{slot}-{span}", "Note", 4, "TCP", depth,
                           slot=slot, span=span)
                      for depth in range(CENTER_DEPTH, 5)
                      for slot in (0, 7, 15)
                      for span in BLOCK_SIZES.values())
        meshes = layout_meshes(nodes)
        for node in nodes:
            with self.subTest(depth=node.depth, slot=node.slot, span=node.span):
                self.assertEqual(node_position(node), meshes[node.id].center)

    def test_all_radial_levels_are_equally_spaced_including_center(self):
        node = Node("note", "Note", 4, None, CENTER_DEPTH)
        radii = [hypot(*node_position(replace(node, depth=depth))[:2])
                 for depth in range(CENTER_DEPTH, 5)]
        self.assertAlmostEqual(radii[0], RADIAL_WIDTH / 2)
        for inner, outer in zip(radii, radii[1:]):
            self.assertAlmostEqual(outer - inner, RADIAL_WIDTH)

    def test_full_center_note_uses_the_layer_axis(self):
        layer = Layer("custom", "Custom", "#70cbd8")
        design = Design(layers=(layer,), protocols=())
        for slot in (0, 7, 15):
            node = Node(f"center-{slot}", "Center note", layer.id, None, CENTER_DEPTH,
                        "Editable notes", slot=slot, span=ANGULAR_SLOTS)
            self.assertEqual(node_position(node, design), (0.0, 0.0, design.z_base + .5))
            self.assertEqual(layout_meshes((node,), design)[node.id].center, node_position(node, design))

    def test_wrapping_footprints_keep_their_midpoint(self):
        for span in BLOCK_SIZES.values():
            node = Node("note", "Note", 2, None, 1, slot=15, span=span)
            x, y, _ = node_position(node)
            angle_slots = ((atan2(y, x) + pi / 2) % (2 * pi)) * ANGULAR_SLOTS / (2 * pi)
            difference = (angle_slots - (node.slot + span / 2) + ANGULAR_SLOTS / 2) % ANGULAR_SLOTS - ANGULAR_SLOTS / 2
            self.assertAlmostEqual(difference, 0)

    def test_custom_layer_order_controls_height_without_rewriting_note(self):
        bottom = Layer("custom-a", "First", "#70cbd8")
        top = Layer("custom-b", "Second", "#edbb69")
        design = Design(layers=(bottom, top), protocols=())
        node = Node("note", "Note", bottom.id, None, 1, slot=7, span=2)
        before = node.to_dict()
        original = node_position(node, design)
        reordered = node_position(node, replace(design, layers=(top, bottom)))
        self.assertEqual(original[:2], reordered[:2])
        self.assertEqual((original[2], reordered[2]), (-.5, .5))
        self.assertEqual(node.to_dict(), before)

    def test_adjacency_is_sparse_and_never_crosses_layers(self):
        ring = tuple(Node(name, name, 2, None, 0, slot=slot)
                     for name, slot in zip(("a", "b", "c", "d"), (0, 4, 8, 12)))
        outer = (Node("e", "e", 2, None, 2, slot=1), Node("f", "f", 2, None, 2, slot=9))
        other_layer = Node("g", "g", 3, None, 0, slot=0)
        pairs = set(adjacent_node_pairs(ring + outer + (other_layer,)))
        self.assertTrue({("a", "b"), ("b", "c"), ("c", "d"), ("a", "d")} <= pairs)
        self.assertNotIn(("a", "c"), pairs)
        self.assertNotIn(("b", "d"), pairs)
        self.assertFalse(any("g" in pair for pair in pairs))
        connected = set().union(*map(set, pairs))
        self.assertEqual(connected, {"a", "b", "c", "d", "e", "f"})


if __name__ == "__main__":
    unittest.main()
