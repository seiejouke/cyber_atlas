from dataclasses import replace
import unittest

from atlas.design_draft import DesignDraft
from atlas.model import Atlas, AtlasError, Design, Layer, Node, Protocol


class DesignDraftTests(unittest.TestCase):
    def setUp(self):
        design = Design((Layer("low", "Foundation", "#65b6a1"), Layer("high", "Services", "#9c8bdb"),
                         Layer("unused", "Unused", "#edbb69")),
                        (Protocol("one", "First"), Protocol("two", "Second")), "Tier", "Category", "combined")
        self.source = Atlas((Node("a", "A", "low", "one", 0, "Notes A", slot=0, span=2),
                             Node("b", "B", "high", "two", 0, "Notes B", slot=0, span=2),
                             Node("c", "C", "high", "one", 1, "Notes C", slot=5)), design)
        self.draft = DesignDraft(self.source)
        self.new_layers = (Layer("new-low", "New foundation", "#65b6a1"), Layer("new-high", "New services", "#9c8bdb"))
        self.new_protocols = (Protocol("new", "New protocol"),)

    def test_complete_draft_matches_original(self):
        self.assertTrue(self.draft.ready)
        self.assertEqual(self.draft.to_atlas(), self.source)

    def test_clear_layers_keeps_all_blocks_and_disables_apply(self):
        self.draft.clear("layers")
        self.assertEqual(self.draft.layers, ())
        self.assertEqual(self.draft.nodes, self.source.nodes)
        self.assertFalse(self.draft.ready)
        self.assertIn("Add at least one layer", self.draft.readiness_hint)
        with self.assertRaises(AtlasError):
            self.draft.to_atlas()

    def test_clear_protocols_unassigns_blocks_and_keeps_apply_enabled(self):
        self.draft.clear("protocols")
        self.assertEqual(self.draft.protocols, ())
        self.assertEqual(self.draft.nodes, tuple(replace(n, protocol=None) for n in self.source.nodes))
        self.assertEqual(self.draft.pending("protocols"), ())
        self.assertTrue(self.draft.ready)
        self.assertEqual(self.draft.to_atlas(), self.source.without_protocols())

    def test_clear_both_and_rebuild_requires_all_assignments(self):
        self.draft.clear("layers")
        self.draft.clear("protocols")
        self.draft.set_entries("layers", self.new_layers)
        self.draft.set_entries("protocols", self.new_protocols)
        self.assertFalse(self.draft.ready)
        self.draft.reassign("layers", {"low": "new-low", "high": "new-high"})
        self.assertTrue(self.draft.ready)
        candidate = self.draft.to_atlas()
        expected = tuple(replace(node, layer={"low": "new-low", "high": "new-high"}[node.layer], protocol=None)
                         for node in self.source.nodes)
        self.assertEqual(candidate.nodes, expected)
        self.assertEqual(candidate.design.layer_caption, "Tier")
        self.assertEqual(candidate.design.protocol_caption, "Category")
        self.assertEqual(Atlas.from_dict(candidate.to_dict()), candidate)
        self.assertEqual(self.source.nodes[0].layer, "low")

    def test_pending_groups_keep_names_and_counts(self):
        self.draft.clear("layers")
        self.assertEqual([(e.id, e.name, e.count) for e in self.draft.pending("layers")],
                         [("low", "Foundation", 1), ("high", "Services", 2)])
        self.assertEqual(self.draft.pending("protocols"), ())

    def test_incomplete_or_unknown_destinations_are_atomic(self):
        self.draft.clear("layers")
        self.draft.set_entries("layers", self.new_layers)
        for moves in ({}, {"low": "new-low"}, {"low": "new-low", "high": "missing"},
                      {"low": "new-low", "high": "new-high", "unused": "new-high"}):
            with self.subTest(moves=moves), self.assertRaises(AtlasError):
                self.draft.reassign("layers", moves)
            self.assertEqual(self.draft.nodes, self.source.nodes)

    def test_layer_merge_collision_is_atomic_even_without_protocols(self):
        self.draft.clear("layers")
        self.draft.clear("protocols")
        self.draft.set_entries("layers", self.new_layers)
        before = self.draft.nodes
        with self.assertRaisesRegex(AtlasError, "overlaps.*New foundation"):
            self.draft.reassign("layers", {"low": "new-low", "high": "new-low"})
        self.assertEqual(self.draft.nodes, before)
        self.draft.reassign("layers", {"low": "new-low", "high": "new-high"})
        self.assertTrue(self.draft.ready)
        self.assertEqual(self.draft.pending("layers"), ())

    def test_repeated_clearing_retains_the_latest_removed_names(self):
        entries = (replace(self.source.design.layers[0], name="Renamed"),) + self.source.design.layers[1:]
        self.draft.set_entries("layers", entries)
        self.draft.clear("layers")
        self.assertEqual(self.draft.pending("layers")[0].name, "Renamed")
        self.draft.set_entries("layers", self.new_layers)
        self.draft.reassign("layers", {"low": "new-low", "high": "new-high"})
        self.draft.clear("layers")
        self.draft.clear("layers")
        self.assertEqual([(e.name, e.count) for e in self.draft.pending("layers")],
                         [("New foundation", 1), ("New services", 2)])

    def test_empty_atlas_needs_replacements_without_reassignment(self):
        draft = DesignDraft(Atlas())
        draft.clear("layers")
        draft.clear("protocols")
        draft.set_entries("layers", self.new_layers[:1])
        self.assertTrue(draft.ready)
        draft.set_entries("protocols", self.new_protocols)
        self.assertTrue(draft.ready)
        self.assertEqual(draft.to_atlas().nodes, ())

    def test_invalid_entry_edits_preserve_lists(self):
        for entries in ([], (self.new_layers[0], self.new_layers[0]), (Protocol("bad", "Bad type"),)):
            with self.subTest(entries=entries), self.assertRaises(AtlasError):
                self.draft.set_entries("layers", entries)
            self.assertEqual(self.draft.layers, self.source.design.layers)
        with self.assertRaises(AtlasError):
            self.draft.clear("unknown")

    def test_single_remove_still_requires_safe_reassignment(self):
        with self.assertRaisesRegex(AtlasError, "replacement"):
            self.draft.remove("layers", "high")
        with self.assertRaisesRegex(AtlasError, "overlaps"):
            self.draft.remove("layers", "high", "low")
        self.assertEqual(self.draft.to_atlas(), self.source)
        self.draft.remove("layers", "high", "unused")
        self.assertEqual(self.draft.nodes[1], replace(self.source.nodes[1], layer="unused"))
        self.assertTrue(self.draft.ready)


if __name__ == "__main__":
    unittest.main()
