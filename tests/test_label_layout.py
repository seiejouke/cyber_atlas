"""Label stability, sparse coverage, priority and crowded viewport limits."""
from dataclasses import replace
import unittest

from atlas.label_layout import LabelLayout, LabelRequest, inside, overlaps


class LabelLayoutTests(unittest.TestCase):
    BOUNDS = (8, 36, 792, 518)

    def request(self, key, x=300, y=250, priority=0):
        return LabelRequest(key, (x, y), (150, 40), priority=priority)

    def test_four_close_nodes_all_get_readable_labels(self):
        requests = [self.request(str(i), 400+i*12, 300+i*3) for i in range(4)]
        placed = LabelLayout().place(requests, self.BOUNDS)
        self.assertEqual(set(placed), {request.key for request in requests})
        for a, box in placed.items():
            self.assertTrue(inside(box, self.BOUNDS))
            for b, other in placed.items():
                if a != b:
                    self.assertFalse(overlaps(box, other))

    def test_crossing_screen_centre_keeps_the_same_relative_position(self):
        layout = LabelLayout()
        request = self.request("one", 200)
        layout.place([request], self.BOUNDS)
        before = layout.offsets[request.key]
        self.assertLess(before[0], 0)
        moved = replace(request, anchor=(550, 250))
        layout.place([moved], self.BOUNDS)
        self.assertEqual(layout.offsets[request.key], before)

    def test_camera_motion_follows_anchor_without_relayout(self):
        layout = LabelLayout()
        requests = [self.request("one", 220, 180), self.request("two", 540, 350)]
        first = layout.place(requests, self.BOUNDS)
        moved = [replace(request, anchor=(request.anchor[0]+20, request.anchor[1]+12)) for request in requests]
        after = layout.place(moved, self.BOUNDS, moving=True)
        for key in first:
            self.assertEqual(tuple(b-a for a, b in zip(first[key], after[key])), (20, 12, 20, 12))

    def test_temporary_overlap_during_motion_resolves_when_settled(self):
        layout = LabelLayout()
        a = LabelRequest("a", (200, 150), (100, 30))
        b = LabelRequest("b", (500, 150), (100, 30))
        layout.place([a, b], self.BOUNDS)
        b = replace(b, anchor=(100, 150))
        moving = layout.place([a, b], self.BOUNDS, moving=True)
        self.assertTrue(overlaps(moving["a"], moving["b"]))
        settled = layout.place([a, b], self.BOUNDS)
        self.assertFalse(overlaps(settled["a"], settled["b"]))

    def test_selected_and_hovered_labels_get_space_before_ordinary_labels(self):
        bounds = (0, 0, 220, 100)
        requests = [LabelRequest(str(i), (100, 50), (90, 30)) for i in range(12)]
        requests.extend((LabelRequest("selected", (100, 50), (90, 30), priority=3),
                         LabelRequest("hovered", (100, 50), (90, 30), priority=2)))
        placed = LabelLayout().place(requests, bounds)
        self.assertIn("selected", placed)
        self.assertIn("hovered", placed)
        self.assertLess(len(placed), len(requests))
        self.assertFalse(overlaps(placed["selected"], placed["hovered"]))

    def test_priority_callout_can_displace_decorations_but_never_the_navigation_panel(self):
        reserved = [(600, 36, 792, 500)]
        obstacles = [self.BOUNDS]
        requests = [self.request("ordinary"), self.request("selected", priority=3)]
        placed = LabelLayout().place(requests, self.BOUNDS, reserved, obstacles)
        self.assertNotIn("ordinary", placed)
        self.assertIn("selected", placed)
        self.assertFalse(overlaps(placed["selected"], reserved[0]))

    def test_nearby_obstacles_use_farther_free_space_instead_of_dropping_label(self):
        layout = LabelLayout()
        request = self.request("one", 400, 270)
        obstacles = [(150, 100, 650, 440)]
        placed = layout.place([request], self.BOUNDS, obstacles=obstacles)
        self.assertIn("one", placed)
        self.assertFalse(overlaps(placed["one"], obstacles[0]))

    def test_label_near_viewport_edge_stays_inside(self):
        for point in ((10, 38), (790, 38), (10, 516), (790, 516)):
            request = replace(self.request("edge"), anchor=point)
            self.assertTrue(inside(LabelLayout().place([request], self.BOUNDS)["edge"], self.BOUNDS))

    def test_source_order_does_not_change_placement(self):
        requests = [self.request(str(i), 350+i*10) for i in range(8)]
        self.assertEqual(LabelLayout().place(requests, self.BOUNDS),
                         LabelLayout().place(list(reversed(requests)), self.BOUNDS))

    def test_new_selection_takes_priority_over_an_existing_cached_label(self):
        layout = LabelLayout()
        a, b = self.request("a"), self.request("b")
        layout.place([a, b], self.BOUNDS)
        placed = layout.place([a, replace(b, priority=3)], self.BOUNDS)
        self.assertIn("b", placed)
        self.assertFalse(overlaps(placed["a"], placed["b"]))

    def test_removed_nodes_can_be_pruned_without_losing_surviving_positions(self):
        layout = LabelLayout()
        layout.place([self.request("a"), self.request("b")], self.BOUNDS)
        before = layout.offsets["a"]
        layout.prune({"a"})
        self.assertEqual(layout.offsets, {"a": before})

    def test_impossible_size_returns_no_placement(self):
        request = LabelRequest("too large", (200, 200), (1000, 50))
        self.assertEqual(LabelLayout().place([request], self.BOUNDS), {})

    def test_priority_fallback_keeps_its_own_node_uncovered(self):
        request = LabelRequest("selected", (110, 90), (100, 40), priority=3)
        bounds = (0, 0, 220, 180)
        box = LabelLayout().place([request], bounds, obstacles=[bounds])["selected"]
        self.assertFalse(overlaps(box, (106, 86, 114, 94), padding=0))


if __name__ == "__main__":
    unittest.main()
