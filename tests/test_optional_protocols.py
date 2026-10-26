from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from atlas.geometry import layout_meshes
from atlas.model import Atlas, AtlasError, Design, Node, Protocol, example_atlas
from atlas.storage import read_atlas, write_atlas


class OptionalProtocolTests(unittest.TestCase):
    def setUp(self):
        self.source = example_atlas()
        self.cleared = self.source.without_protocols()

    def test_clear_keeps_notes_ids_positions_sizes_and_design_settings(self):
        self.assertEqual(self.cleared.nodes, tuple(replace(n, protocol=None) for n in self.source.nodes))
        self.assertEqual(self.cleared.design, replace(self.source.design, protocols=()))
        self.assertEqual(layout_meshes(self.cleared.nodes), layout_meshes(self.source.nodes))
        self.assertEqual(len(self.source.design.protocols), 17)

    def test_unassigned_blocks_roundtrip_with_json_null(self):
        data = self.cleared.to_dict()
        self.assertEqual(data["version"], 11)
        self.assertEqual(data["design"]["protocols"], [])
        self.assertTrue(all(n["protocol"] is None for n in data["nodes"]))
        self.assertEqual(Atlas.from_dict(json.loads(json.dumps(data))), self.cleared)

    def test_clear_and_reload_keeps_backup_of_original_protocol_assignments(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "atlas.json"
            write_atlas(path, self.source)
            write_atlas(path, self.cleared)
            self.assertEqual(read_atlas(path), self.cleared)
            self.assertEqual(read_atlas(path.with_suffix(".json.bak")), self.source)

    def test_no_protocol_required_for_new_blocks_and_free_slot_queries(self):
        empty = Atlas(design=replace(Design(), protocols=()))
        node = Node.create("Untyped block", 7, None, 2, "New notes", slot=4, span=2)
        updated = empty.with_node(node)
        self.assertEqual(updated.get(node.id).protocol, None)
        self.assertNotIn(4, updated.free_starts(7, 2))
        self.assertEqual(updated.next_free(7, 2, start=4), 6)
        self.assertEqual(Atlas.from_dict(updated.to_dict()), updated)

    def test_adding_protocols_does_not_automatically_assign_existing_blocks(self):
        protocol = Protocol("new", "New protocol")
        updated = self.cleared.with_design(replace(self.cleared.design, protocols=(protocol,)))
        self.assertEqual(updated.nodes, self.cleared.nodes)
        node = updated.nodes[0]
        assigned = updated.with_node(replace(node, protocol="new"))
        self.assertEqual(assigned.nodes[1:], self.cleared.nodes[1:])
        self.assertEqual(layout_meshes(assigned.nodes), layout_meshes(self.cleared.nodes))

    def test_label_modes_show_no_protocol_without_a_fake_entry(self):
        node = self.cleared.nodes[0]
        self.assertEqual(replace(self.cleared.design, label_mode="coordinates").block_label(node), "Physical · No protocol")
        self.assertIn("No protocol", replace(self.cleared.design, label_mode="combined").block_label(node))
        self.assertEqual(self.cleared.design.protocols, ())

    def test_empty_atlas_and_repeated_clear_stay_empty(self):
        empty = Atlas().without_protocols()
        self.assertEqual(Atlas.from_dict(empty.to_dict()), empty)
        self.assertIs(empty.without_protocols(), empty)

    def test_old_versions_do_not_accept_unassigned_references(self):
        for version in (6, 7):
            data = self.source.to_dict()
            data["version"] = version
            data["nodes"][0]["protocol"] = None
            with self.subTest(version=version), self.assertRaisesRegex(AtlasError, "version 8"):
                Atlas.from_dict(data)
        data = Atlas().without_protocols().to_dict()
        data["version"] = 7
        with self.assertRaisesRegex(AtlasError, "version 8"):
            Atlas.from_dict(data)

    def test_version_seven_keeps_custom_design_and_protocol_assignments(self):
        design = replace(self.source.design, protocols=(Protocol("custom", "Custom protocol"),), layer_caption="Tier")
        atlas = Atlas((replace(self.source.nodes[0], protocol="custom"),), design)
        data = atlas.to_dict()
        data["version"] = 7
        self.assertEqual(Atlas.from_dict(data), atlas)


if __name__ == "__main__":
    unittest.main()
