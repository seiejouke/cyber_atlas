"""Layer concepts use ordinary, persistent notes without changing old files."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from atlas.geometry import node_position
from atlas.design_draft import DesignDraft
from atlas.heat import information_heat
from atlas.model import (ANGULAR_SLOTS, CENTER_DEPTH, Atlas, AtlasError, Design,
                         FlowNote, FlowStep, InformationEntry, Layer, Node, Subconcept)
from atlas.storage import read_atlas, write_atlas


class LayerCenterTests(unittest.TestCase):
    def setUp(self):
        self.design = Design((Layer("base", "Foundations", "#65b6a1"),
                              Layer("top", "Applications", "#edbb69")), ())

    def test_each_new_center_has_its_own_persistent_identity(self):
        original = Atlas(design=self.design)
        document = original.with_layer_centers()
        self.assertEqual(len(document.nodes), 2)
        self.assertEqual(len({node.id for node in document.nodes}), 2)
        self.assertTrue(all(node.is_layer_center and node.slot == 0 and node.protocol is None
                            for node in document.nodes))
        self.assertEqual([node.name for node in document.nodes], [layer.name for layer in self.design.layers])
        self.assertIs(document.with_layer_centers(), document)
        self.assertEqual(Atlas.from_dict(document.to_dict()), document)
        self.assertEqual(original.nodes, ())
        self.assertTrue({node.id for node in original.with_layer_centers().nodes}.isdisjoint(
            node.id for node in document.nodes))

    def test_saved_center_and_all_its_references_are_reused(self):
        center = Node("existing", "My overview", "base", None, CENTER_DEPTH,
                      "Keep this explanation", span=ANGULAR_SLOTS)
        child = Subconcept("child", center.id, "Variant", "Child notes")
        entry = InformationEntry("entry", center.id, "Observation", "More information")
        flow = FlowNote("flow", "Study", steps=(FlowStep("step", center.id, "Begin"),))
        original = Atlas((center,), self.design, (child,), (entry,), (flow,))
        updated = original.with_layer_centers()
        self.assertEqual(updated.layer_center("base"), center)
        self.assertEqual((updated.subconcepts, updated.information_entries, updated.flows),
                         (original.subconcepts, original.information_entries, original.flows))
        self.assertEqual(information_heat(updated)[center.id].blended, 3)
        self.assertEqual(len(updated.nodes), 2)

    def test_only_requested_new_layers_get_centers(self):
        updated = Atlas(design=self.design).with_layer_centers({"top"})
        self.assertIsNone(updated.layer_center("base"))
        self.assertEqual(updated.nodes, (updated.layer_center("top"),))

    def test_legacy_split_centers_keep_their_notes_and_occupied_slots(self):
        partial = Node("old", "Legacy center wedge", "base", None, CENTER_DEPTH,
                       "Preserve", slot=4, span=2)
        updated = Atlas((partial,), self.design).with_layer_centers()
        self.assertEqual(updated.nodes[0], partial)
        self.assertIsNone(updated.layer_center("base"))
        self.assertEqual(len(updated.nodes), 2)

    def test_notes_and_titles_edit_normally_but_center_stays_on_its_layer(self):
        document = Atlas(design=self.design).with_layer_centers()
        center = document.layer_center("base")
        edited = replace(center, name="A personal title", notes="An explanation")
        self.assertEqual(document.with_node(edited).get(center.id), edited)
        for change in ({"layer": "top"}, {"depth": 0}, {"slot": 1}, {"span": 1}):
            with self.subTest(change=change), self.assertRaisesRegex(AtlasError, "stays on its axis"):
                document.with_node(replace(center, **change))

    def test_layer_rename_and_reorder_preserve_node_content_and_identity(self):
        document = Atlas(design=self.design).with_layer_centers()
        center = document.layer_center("base")
        design = replace(self.design, layers=(self.design.layers[1],
                                              replace(self.design.layers[0], name="Renamed layer")))
        updated = document.with_design(design)
        self.assertEqual(updated.nodes, document.nodes)
        self.assertNotEqual(node_position(center, document.design)[2], node_position(center, design)[2])

    def test_fresh_centers_are_empty_but_user_content_requires_reset_confirmation(self):
        document = Atlas(design=self.design).with_layer_centers()
        center = document.nodes[0]
        self.assertFalse(document.has_content)
        self.assertTrue(document.with_node(replace(center, notes="Written notes")).has_content)
        self.assertTrue(document.with_node(replace(center, name="Custom title")).has_content)
        self.assertTrue(document.with_child(Subconcept("child", center.id, "Type")).has_content)
        self.assertTrue(document.with_entry(InformationEntry("entry", center.id, "Title", "Text")).has_content)
        self.assertTrue(document.with_flow(FlowNote("flow", "Guide")).has_content)

    def test_enriching_an_old_document_does_not_write_until_saved(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "atlas.json"
            original = Atlas(design=self.design)
            write_atlas(path, original, backup=False)
            original_bytes = path.read_bytes()
            updated = read_atlas(path).with_layer_centers()
            self.assertEqual(path.read_bytes(), original_bytes)
            write_atlas(path, updated)
            self.assertEqual(read_atlas(path), updated)
            self.assertEqual(read_atlas(path.with_suffix(".json.bak")), original)

    def test_center_creation_respects_the_combined_concept_limit_atomically(self):
        original = Atlas(design=self.design)
        with patch("atlas.model.MAX_NODES", 1), self.assertRaises(AtlasError):
            original.with_layer_centers()
        self.assertEqual(original.nodes, ())

    def test_an_unused_center_leaves_with_its_removed_layer(self):
        original = Atlas(design=self.design).with_layer_centers()
        draft = DesignDraft(original)
        draft.remove("layers", "top")
        self.assertEqual(draft.to_atlas().nodes, (original.layer_center("base"),))
        self.assertEqual(len(original.nodes), 2)

    def test_layer_removal_never_discards_center_content_or_references(self):
        original = Atlas(design=self.design).with_layer_centers()
        center = original.layer_center("top")
        documents = (
            original.with_node(replace(center, notes="Keep these notes")),
            original.with_node(replace(center, name="Custom title")),
            original.with_child(Subconcept("child", center.id, "Type")),
            original.with_entry(InformationEntry("entry", center.id, "Title", "Text")),
            original.with_flow(FlowNote("flow", "Guide", steps=(FlowStep("step", center.id, "Start"),))),
        )
        for document in documents:
            with self.subTest(document=document):
                draft = DesignDraft(document)
                self.assertEqual(draft.unused_centers("top"), set())
                with self.assertRaises(AtlasError):
                    draft.remove("layers", "top")
                self.assertEqual(draft.to_atlas(), document)

    def test_rebuilding_layers_omits_only_unused_default_centers(self):
        original = Atlas(design=self.design).with_layer_centers()
        center = original.layer_center("base")
        original = original.with_node(replace(center, notes="Keep this overview"))
        draft = DesignDraft(original)
        draft.clear("layers")
        self.assertEqual(draft.nodes, (original.get(center.id),))
        self.assertEqual([(entry.id, entry.count) for entry in draft.pending("layers")], [("base", 1)])
        self.assertEqual(len(original.nodes), 2)


if __name__ == "__main__":
    unittest.main()
