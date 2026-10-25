"""Spatial edges follow shared footprint boundaries, including large blocks."""
from dataclasses import replace
import unittest

from atlas.geometry import adjacent_node_pairs
from atlas.model import CENTER_DEPTH, Node


class AdjacencyTests(unittest.TestCase):
    def node(self, identity, slot=0, span=1, depth=0, layer=4):
        return Node(identity, identity, layer, None, depth, slot=slot, span=span)

    def test_empty_and_single_node_have_no_edges(self):
        self.assertEqual(adjacent_node_pairs(()), ())
        self.assertEqual(adjacent_node_pairs((self.node("alone"),)), ())

    def test_consecutive_angular_slots_share_an_edge(self):
        self.assertEqual(adjacent_node_pairs((self.node("a"), self.node("b", 1))), (("a", "b"),))

    def test_empty_angular_slots_break_connections(self):
        for slot in (2, 4, 8, 14):
            with self.subTest(slot=slot):
                self.assertEqual(adjacent_node_pairs((self.node("a"), self.node("b", slot))), ())

    def test_last_and_first_slots_are_neighbors(self):
        self.assertEqual(adjacent_node_pairs((self.node("last", 15), self.node("first"))),
                         (("first", "last"),))

    def test_wrapping_large_block_connects_only_at_its_boundaries(self):
        nodes = (self.node("wide", 14, 4), self.node("after", 2, 2),
                 self.node("before", 12, 2), self.node("isolated", 6))
        self.assertEqual(adjacent_node_pairs(nodes), (("after", "wide"), ("before", "wide")))

    def test_consecutive_bands_require_angular_overlap(self):
        inner = self.node("inner", 0, 4)
        overlap = self.node("outer", 3, 2, depth=1)
        disjoint = replace(overlap, slot=8)
        self.assertEqual(adjacent_node_pairs((inner, overlap)), (("inner", "outer"),))
        self.assertEqual(adjacent_node_pairs((inner, disjoint)), ())

    def test_corner_contact_is_not_an_edge(self):
        inner = self.node("inner", 0, 2)
        for slot in (2, 15):
            with self.subTest(slot=slot):
                self.assertEqual(adjacent_node_pairs((inner, self.node("outer", slot, depth=1))), ())

    def test_empty_radial_bands_break_connections(self):
        for depth in (2, 3, 4):
            with self.subTest(depth=depth):
                self.assertEqual(adjacent_node_pairs((self.node("a"), self.node("b", depth=depth))), ())

    def test_different_layers_never_connect(self):
        nodes = (self.node("a"), self.node("b", 1, layer=3), self.node("c", depth=1, layer=3))
        self.assertEqual(adjacent_node_pairs(nodes), ())

    def test_full_center_connects_only_to_the_immediately_outer_band(self):
        nodes = (self.node("center", span=16, depth=CENTER_DEPTH), self.node("near", 7),
                 self.node("far", 7, depth=1), self.node("other", 0, depth=2))
        self.assertEqual(adjacent_node_pairs(nodes), (("center", "near"), ("far", "near")))

    def test_partial_center_sectors_meeting_only_at_origin_are_not_adjacent(self):
        nodes = (self.node("a", depth=CENTER_DEPTH), self.node("b", 8, depth=CENTER_DEPTH))
        self.assertEqual(adjacent_node_pairs(nodes), ())

    def test_two_shared_boundaries_produce_one_undirected_edge(self):
        nodes = (self.node("a", 0, 8), self.node("b", 8, 8))
        self.assertEqual(adjacent_node_pairs(nodes), (("a", "b"),))

    def test_pair_order_is_stable_for_custom_layers_and_mixed_footprints(self):
        nodes = (self.node("z", 14, 4, layer="custom"), self.node("a", 2, 2, layer="custom"),
                 self.node("m", 0, 16, depth=1, layer="custom"))
        expected = (("a", "m"), ("a", "z"), ("m", "z"))
        self.assertEqual(adjacent_node_pairs(nodes), expected)
        self.assertEqual(adjacent_node_pairs(tuple(reversed(nodes))), expected)


if __name__ == "__main__":
    unittest.main()
