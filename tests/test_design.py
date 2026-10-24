from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from atlas.geometry import layout_meshes, wedge_mesh
from atlas.model import Atlas, AtlasError, Design, Layer, Node, Protocol, example_atlas
from atlas.storage import read_atlas, write_atlas


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.design = Design((Layer("low", "Foundation", "#65b6a1"), Layer("high", "Services", "#edbb69")),
                             (Protocol("custom", "My protocol"),), "Tier", "Category", "combined")
        self.node = Node("box", "My block", "high", "custom", 0, "Keep my notes", slot=5, span=2)
        self.atlas = Atlas((self.node,), self.design)

    def test_custom_design_and_stable_refs_roundtrip(self):
        self.assertEqual(Atlas.from_dict(self.atlas.to_dict()), self.atlas)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "atlas.json"
            write_atlas(path, self.atlas)
            self.assertEqual(read_atlas(path), self.atlas)

    def test_renaming_entries_does_not_change_blocks_or_geometry(self):
        design = replace(self.design, layers=(self.design.layers[0], replace(self.design.layers[1], name="Renamed")),
                         protocols=(replace(self.design.protocols[0], name="Renamed protocol"),))
        updated = self.atlas.with_design(design)
        self.assertEqual(updated.nodes, self.atlas.nodes)
        self.assertEqual(layout_meshes(updated.nodes, design), layout_meshes(self.atlas.nodes, self.design))
        self.assertEqual(design.block_label(self.node), "My block · Renamed · Renamed protocol")

    def test_reordering_moves_layer_and_retains_block_identity(self):
        design = replace(self.design, layers=tuple(reversed(self.design.layers)))
        updated = self.atlas.with_design(design)
        before = wedge_mesh(self.node, design=self.design)
        after = wedge_mesh(updated.nodes[0], design=design)
        self.assertEqual(before.center[:2], after.center[:2])
        self.assertEqual(before.center[2] - after.center[2], 1)
        self.assertEqual(updated.nodes, self.atlas.nodes)

    def test_layer_count_centers_axis_and_keeps_equal_spacing(self):
        for count in (1, 3, 8, 16, 64):
            design = replace(self.design, layers=tuple(Layer(f"id-{i}", f"Tier {i}", "#123456") for i in range(count)))
            meshes = [wedge_mesh(replace(self.node, layer=layer.id), design=design) for layer in design.layers]
            self.assertEqual(min(p[2] for p in meshes[0].points), -count / 2)
            self.assertEqual(max(p[2] for p in meshes[-1].points), count / 2)
            self.assertTrue(all(b.center[2] - a.center[2] == 1 for a, b in zip(meshes, meshes[1:])))

    def test_node_operations_keep_custom_design(self):
        updated = self.atlas.with_node(replace(self.node, name="Edited"))
        self.assertEqual(updated.design, self.design)
        self.assertEqual(updated.without_node("box"), Atlas(design=self.design))
        self.assertNotIn(5, self.atlas.free_starts("high", 0))
        self.assertEqual(self.atlas.next_free("high", 0, start=5), 7)

    def test_missing_refs_rejected_by_atlas(self):
        for node in (replace(self.node, layer=8), replace(self.node, protocol="unknown")):
            with self.subTest(node=node), self.assertRaises(AtlasError):
                Atlas((node,), self.design)
        with self.assertRaises(AtlasError):
            self.atlas.free_starts("missing", 0)

    def test_removing_in_use_entry_requires_reassignment(self):
        design = replace(self.design, layers=self.design.layers[:1])
        with self.assertRaisesRegex(AtlasError, "Unknown layer"):
            self.atlas.with_design(design)
        updated = self.atlas.with_design(design, {"high": "low"})
        self.assertEqual(updated.nodes, (replace(self.node, layer="low"),))

    def test_protocol_removal_reassigns_without_repositioning(self):
        design = replace(self.design, protocols=(Protocol("replacement", "Replacement"),))
        updated = self.atlas.with_design(design, protocol_moves={"custom": "replacement"})
        self.assertEqual(updated.nodes, (replace(self.node, protocol="replacement"),))
        self.assertEqual(layout_meshes(updated.nodes, design), layout_meshes(self.atlas.nodes, self.design))

    def test_layer_reassignment_collision_is_atomic(self):
        other = replace(self.node, id="other", layer="low")
        atlas = self.atlas.with_node(other)
        with self.assertRaisesRegex(AtlasError, "overlaps"):
            atlas.with_design(replace(self.design, layers=self.design.layers[:1]), {"high": "low"})
        self.assertEqual(atlas.nodes, (self.node, other))
        self.assertEqual(atlas.design, self.design)

    def test_all_label_modes(self):
        for mode, label in (("title", "My block"), ("coordinates", "Services · My protocol"),
                            ("combined", "My block · Services · My protocol")):
            self.assertEqual(replace(self.design, label_mode=mode).block_label(self.node), label)

    def test_invalid_designs_rejected(self):
        changes = ({"layers": ()}, {"protocols": []}, {"layers": []}, {"label_mode": "unknown"},
                   {"layer_caption": ""}, {"protocol_caption": "a\nb"},
                   {"layers": (self.design.layers[0], self.design.layers[0])},
                   {"protocols": (Protocol("x", "Name"), Protocol("y", " name "))},
                   {"protocols": (Protocol("x", "A"), Protocol("x", "B"))})
        for change in changes:
            with self.subTest(change=change), self.assertRaises(AtlasError):
                replace(self.design, **change)
        for color in ("red", "#123", "#000000x", None):
            with self.subTest(color=color), self.assertRaises(AtlasError):
                Layer("x", "Layer", color)

    def test_invalid_design_json_raises_atlas_error(self):
        original = self.atlas.to_dict()
        for design in (None, {}, {**original["design"], "layers": [None]},
                       {**original["design"], "protocols": [{}]}, {**original["design"], "label_mode": []}):
            with self.subTest(design=design), self.assertRaises(AtlasError):
                Atlas.from_dict({**original, "design": design})

    def test_version_six_migrates_with_exact_placement(self):
        atlas = example_atlas()
        data = atlas.to_dict()
        data["version"] = 6
        del data["design"]
        self.assertEqual(Atlas.from_dict(json.loads(json.dumps(data))), atlas)
        for version in range(1, 7):
            # Custom IDs are never accepted in an old file with the OSI preset.
            data = self.atlas.to_dict()
            data["version"] = version
            if version == 4:
                continue  # Already rejected by its required fixed-grid metadata.
            if version == 5:
                data["layout"] = "equal-rings"
            with self.subTest(version=version), self.assertRaises(AtlasError):
                Atlas.from_dict(data)


if __name__ == "__main__":
    unittest.main()
