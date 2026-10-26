"""Automatic main notes, exact child totals, linear colors and lossless storage."""
from dataclasses import replace
import colorsys
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from atlas.design_draft import DesignDraft
from atlas.geometry import adjacent_node_pairs
from atlas.heat import DEFAULT_HEAT_MAX, HEAT_PRESETS, HEAT_STOPS, heat_color, information_heat
from atlas.model import Atlas, AtlasError, InformationEntry, Node, Subconcept
from atlas.storage import read_atlas, write_atlas


def entries(identity, count):
    return tuple(InformationEntry(f"{identity}-{i}", identity, f"Entry {i}", f"Recorded information {i}")
                 for i in range(count))


class InformationTests(unittest.TestCase):
    def setUp(self):
        self.parent = Node("parent", "Firewall", 3, None, 1, "Keep personal notes", slot=2, span=4)
        self.neighbor = Node("neighbor", "Spatial neighbor", 3, None, 1, slot=6)
        self.children = tuple(Subconcept(f"child-{i}", "parent", f"Child {i}", "Existing child notes", i)
                              for i in range(4))
        self.atlas = Atlas((self.parent, self.neighbor), subconcepts=self.children)

    def populated(self):
        return replace(self.atlas, information_entries=entries("parent", 8) + entries("neighbor", 100)
                       + sum((entries(child.id, count) for child, count in zip(self.children, (4, 2, 10, 0))), ()))

    def test_existing_main_notes_and_each_saved_child_count_automatically(self):
        metrics = information_heat(self.atlas)
        self.assertEqual((metrics["parent"].own, metrics["parent"].support, metrics["parent"].blended), (1, 4, 5))
        self.assertEqual(metrics["neighbor"].own, 1)
        self.assertTrue(all(metrics[child.id].own == 1 for child in self.children))
        self.assertFalse(self.atlas.information_entries)

    def test_own_entries_and_direct_child_support_are_separate(self):
        metric = information_heat(self.populated())
        self.assertEqual((metric["parent"].own, metric["parent"].support, metric["parent"].blended), (9, 20, 29))
        self.assertEqual(metric["child-1"].own, 3)
        self.assertEqual(metric["child-1"].support, 0)
        self.assertEqual(metric["neighbor"].blended, 101)

    def test_spatial_neighbors_do_not_supply_support(self):
        atlas = replace(self.atlas, information_entries=entries("neighbor", 100))
        self.assertEqual(information_heat(atlas)["parent"].blended, 5)

    def test_parent_support_does_not_flow_back_to_children(self):
        atlas = replace(self.atlas, information_entries=entries("parent", 100))
        for child in self.children:
            self.assertEqual(information_heat(atlas)[child.id].blended, 1)

    def test_exact_counts_are_not_capped_at_the_color_ceiling(self):
        children = tuple(Subconcept(f"c{i}", "parent", f"Child {i}", orbit_slot=i) for i in range(8))
        atlas = replace(self.atlas, subconcepts=children,
                        information_entries=sum((entries(child.id, 20) for child in children), ()))
        self.assertEqual(information_heat(atlas)["parent"].support, 168)
        self.assertEqual(information_heat(atlas)["parent"].blended, 169)

    def test_editing_entry_keeps_id_count_and_coordinates(self):
        entry = InformationEntry.create("parent", "Definition", "First explanation")
        atlas = self.atlas.with_entry(entry)
        updated = atlas.with_entry(replace(entry, body="A revised explanation"))
        self.assertEqual(information_heat(updated)["parent"].own, 2)
        self.assertEqual(updated.nodes, self.atlas.nodes)
        self.assertEqual(updated.entries_for("parent")[0].id, entry.id)

    def test_entries_require_real_owners_unique_ids_and_nonempty_content(self):
        entry = InformationEntry("entry", "parent", "Definition", "Explanation")
        for changes in ({"body": " "}, {"title": ""}, {"body": "bad\x00text"}, {"title": "bad\ntitle"}, {"body": "x" * 100_001}):
            with self.subTest(changes=changes), self.assertRaises(AtlasError):
                replace(entry, **changes)
        with self.assertRaises(AtlasError):
            self.atlas.with_entry(replace(entry, concept_id="missing"))
        with self.assertRaises(AtlasError):
            replace(self.atlas, information_entries=(entry, entry))

    def test_identical_entry_cannot_accidentally_inflate_a_count(self):
        entry = InformationEntry.create("parent", "Definition", "Explanation")
        with self.assertRaisesRegex(AtlasError, "identical"):
            self.atlas.with_entry(entry).with_entry(replace(entry, id="another"))

    def test_entry_ownership_cannot_be_changed_by_editing(self):
        entry = InformationEntry.create("parent", "Definition", "Explanation")
        with self.assertRaises(AtlasError):
            self.atlas.with_entry(entry).with_entry(replace(entry, concept_id="child-0"))

    def test_deleting_one_entry_preserves_its_concept_and_other_records(self):
        atlas = self.populated()
        updated = atlas.without_entry("parent-0")
        self.assertEqual(updated.nodes, atlas.nodes)
        self.assertEqual(len(updated.entries_for("parent")), 7)
        self.assertEqual(updated.entries_for("child-0"), atlas.entries_for("child-0"))

    def test_deleting_child_removes_only_its_owned_entries(self):
        atlas = self.populated()
        updated = atlas.without_child("child-1")
        self.assertFalse(updated.entries_for("child-1"))
        self.assertEqual(updated.entries_for("parent"), atlas.entries_for("parent"))
        self.assertEqual(information_heat(updated)["parent"].support, 17)

    def test_confirmed_cluster_deletion_removes_all_cluster_entries(self):
        atlas = self.populated()
        with self.assertRaises(AtlasError):
            atlas.without_node("parent")
        updated = atlas.without_node("parent", remove_children=True)
        self.assertEqual(updated.information_entries, atlas.entries_for("neighbor"))

    def test_design_edits_and_protocol_removal_preserve_entries(self):
        atlas = self.populated()
        self.assertEqual(atlas.with_design(atlas.design).information_entries, atlas.information_entries)
        self.assertEqual(atlas.without_protocols().information_entries, atlas.information_entries)
        self.assertEqual(DesignDraft(atlas).to_atlas().information_entries, atlas.information_entries)

    def test_schema_ten_roundtrip_preserves_notes_entries_and_children(self):
        atlas = self.populated()
        data = atlas.to_dict()
        self.assertEqual(data["version"], 11)
        self.assertEqual(Atlas.from_dict(json.loads(json.dumps(data))), atlas)

    def test_version_nine_import_preserves_existing_notes_without_inventing_entries(self):
        data = self.atlas.to_dict()
        data["version"] = 9
        data.pop("information_entries")
        self.assertEqual(Atlas.from_dict(data), self.atlas)

    def test_cannot_hide_new_entries_in_older_files_or_omit_current_list(self):
        data = self.populated().to_dict()
        data["version"] = 9
        with self.assertRaisesRegex(AtlasError, "version 10"):
            Atlas.from_dict(data)
        for value in (None, {}, "entries", [None]):
            data = self.atlas.to_dict()
            data["information_entries"] = value
            with self.assertRaises(AtlasError):
                Atlas.from_dict(data)

    def test_first_save_keeps_original_version_nine_backup(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "atlas.json"
            data = self.atlas.to_dict()
            data["version"] = 9
            data.pop("information_entries")
            original = json.dumps(data).encode()
            path.write_bytes(original)
            atlas = read_atlas(path).with_entry(InformationEntry.create("parent", "Definition", "Information"))
            write_atlas(path, atlas)
            self.assertEqual(path.with_suffix(".json.bak").read_bytes(), original)
            self.assertEqual(read_atlas(path), atlas)

    def test_palette_has_fixed_anchors_and_bounded_extremes(self):
        for count, color in HEAT_STOPS:
            self.assertEqual(heat_color(count), color)
        self.assertEqual(heat_color(10000), HEAT_STOPS[-1][1])
        self.assertEqual(heat_color(-1), HEAT_STOPS[0][1])
        self.assertNotEqual(heat_color(2.5), heat_color(2))

    def test_every_added_note_changes_color_until_each_preset_ceiling(self):
        self.assertEqual(DEFAULT_HEAT_MAX, 16)
        for ceiling in HEAT_PRESETS.values():
            colors = [heat_color(count, ceiling) for count in range(1, ceiling + 1)]
            self.assertEqual(len(set(colors)), ceiling)
            self.assertEqual(colors[0], "#2878ff")
            self.assertEqual(colors[-1], "#ef3f36")
            self.assertEqual(heat_color(ceiling + 100, ceiling), colors[-1])

    def test_palette_stays_saturated_without_white_or_green(self):
        for ceiling in HEAT_PRESETS.values():
            for step in range(501):
                color = heat_color(1 + (ceiling-1) * step / 500, ceiling)
                red, green, blue = (int(color[i:i+2], 16) for i in (1, 3, 5))
                self.assertLessEqual(green, max(red, blue), color)
                _, saturation, _ = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
                self.assertGreaterEqual(saturation, .7, color)

    def test_heat_does_not_modify_documents_or_depend_on_note_length(self):
        original = self.atlas.to_dict()
        edited = self.atlas.with_node(replace(self.parent, notes="A much longer explanation\n" * 100))
        self.assertEqual(information_heat(edited), information_heat(self.atlas))
        self.assertEqual(self.atlas.to_dict(), original)
        self.assertEqual(information_heat(Atlas()), {})

    def test_old_main_note_copies_are_preserved_and_counted_once(self):
        parent_copy = InformationEntry("old-parent-copy", self.parent.id, self.parent.name, self.parent.notes)
        child = self.children[0]
        child_copy = InformationEntry("old-child-copy", child.id, child.name, child.notes)
        atlas = self.atlas.with_entry(parent_copy).with_entry(child_copy)
        original = atlas.to_dict()
        self.assertEqual(information_heat(atlas), information_heat(self.atlas))
        self.assertEqual(atlas.to_dict(), original)
        self.assertEqual(len(atlas.information_entries), 2)
        renamed = atlas.with_node(replace(self.parent, name="Renamed parent"))
        self.assertEqual(information_heat(renamed), information_heat(atlas))

    def test_an_edited_main_note_copy_becomes_additional_information(self):
        child = self.children[0]
        entry = InformationEntry("old-copy", child.id, child.name, child.notes)
        atlas = self.atlas.with_entry(entry)
        edited = atlas.with_entry(replace(entry, body="A different worked example"))
        self.assertEqual(information_heat(edited)[child.id].own, 2)
        self.assertEqual(information_heat(edited)[self.parent.id].support, 5)
        self.assertEqual(edited.child(child.id).notes, child.notes)

    def test_heat_presets_reject_invalid_ceilings(self):
        for ceiling in (0, 1, -1, 10):
            with self.assertRaises(ValueError):
                heat_color(1, ceiling)

    def test_complete_atlas_example_has_real_entries_and_expected_firewall_metrics(self):
        atlas = read_atlas(Path(__file__).resolve().parents[1] / "examples/information_heat_atlas.json")
        self.assertEqual(len(atlas.nodes), 84)
        self.assertEqual(len(atlas.information_entries), 527)
        self.assertTrue(adjacent_node_pairs(atlas.nodes))
        metric = information_heat(atlas)["firewall"]
        self.assertEqual((metric.own, metric.support), (9, 20))


if __name__ == "__main__":
    unittest.main()
