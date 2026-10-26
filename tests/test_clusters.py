"""Persisted orbit relationships, migrations, and stable local geometry."""
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from atlas.design_draft import DesignDraft
from atlas.geometry import ORBIT_RADIUS, node_position, orbit_position
from atlas.model import ANGULAR_SLOTS, Atlas, AtlasError, Design, Node, Subconcept
from atlas.storage import read_atlas, write_atlas


class ClusterTests(unittest.TestCase):
    def setUp(self):
        self.parent = Node('parent', 'Firewall', 3, 'IPv4', 1, 'Parent notes', slot=2, span=4)
        self.child = Subconcept('child', self.parent.id, 'Packet filtering', 'Independent notes', 2)
        self.atlas = Atlas((self.parent,), subconcepts=(self.child,))

    def test_json_roundtrip_preserves_both_kinds_of_notes(self):
        self.assertEqual(Atlas.from_dict(json.loads(json.dumps(self.atlas.to_dict()))), self.atlas)
        self.assertEqual(self.atlas.to_dict()['version'], 11)

    def test_version_eight_migration_preserves_exact_nodes_and_design(self):
        original = Atlas((self.parent,))
        data = original.to_dict()
        data['version'] = 8
        del data['subconcepts']
        self.assertEqual(Atlas.from_dict(data), original)
        self.assertEqual(Atlas.from_dict(data).nodes[0], self.parent)

    def test_cannot_hide_children_in_an_older_file_version(self):
        data = self.atlas.to_dict()
        data['version'] = 8
        with self.assertRaisesRegex(AtlasError, 'version 9'):
            Atlas.from_dict(data)

    def test_orphans_nested_parents_and_self_parent_are_rejected(self):
        for parent in ('missing', self.child.id, 'self'):
            with self.subTest(parent=parent), self.assertRaises(AtlasError):
                self.atlas.with_child(Subconcept('self', parent, 'Invalid'))

    def test_ids_are_unique_across_children_and_grid_nodes(self):
        with self.assertRaisesRegex(AtlasError, 'Duplicate'):
            self.atlas.with_child(replace(self.child, id=self.parent.id))
        with self.assertRaisesRegex(AtlasError, 'Duplicate'):
            replace(self.atlas, subconcepts=(self.child, self.child))

    def test_eight_unique_slots_are_allowed_without_consuming_grid_space(self):
        children = tuple(Subconcept(str(i), self.parent.id, f'Type {i}', orbit_slot=i) for i in range(8))
        atlas = replace(self.atlas, subconcepts=children)
        self.assertEqual(atlas.free_starts(3, 1), Atlas((self.parent,)).free_starts(3, 1))
        with self.assertRaisesRegex(AtlasError, 'already contains'):
            atlas.with_child(Subconcept('ninth', self.parent.id, 'Extra'))

    def test_child_move_rejects_an_occupied_slot_atomically(self):
        atlas = self.atlas.with_child(Subconcept('second', 'parent', 'Other', orbit_slot=4))
        with self.assertRaises(AtlasError):
            atlas.with_child(replace(self.child, orbit_slot=4))
        self.assertEqual(atlas.child('child').orbit_slot, 2)

    def test_children_can_share_local_slots_on_different_parents(self):
        other = replace(self.parent, id='other', layer=4)
        atlas = self.atlas.with_node(other).with_child(replace(self.child, id='other-child', parent_id='other'))
        self.assertEqual(len(atlas.subconcepts), 2)

    def test_deleting_a_parent_requires_explicit_cluster_deletion(self):
        with self.assertRaisesRegex(AtlasError, 'Confirm'):
            self.atlas.without_node('parent')
        self.assertEqual(self.atlas.without_node('parent', remove_children=True), Atlas())

    def test_deleting_one_child_keeps_parent_and_siblings(self):
        sibling = replace(self.child, id='sibling', orbit_slot=4)
        atlas = self.atlas.with_child(sibling).without_child('child')
        self.assertEqual(atlas.nodes, (self.parent,))
        self.assertEqual(atlas.subconcepts, (sibling,))

    def test_renaming_or_moving_parent_keeps_child_identity_notes_and_local_slot(self):
        parent = replace(self.parent, name='New title', layer=4, depth=2, slot=5)
        atlas = self.atlas.with_node(parent)
        self.assertEqual(atlas.child('child'), self.child)

    def test_design_reassignment_and_protocol_removal_keep_children(self):
        atlas = self.atlas.with_design(self.atlas.design, {3: 4}).without_protocols()
        self.assertEqual(atlas.subconcepts, (self.child,))
        self.assertEqual(atlas.get('parent').layer, 4)
        self.assertIsNone(atlas.get('parent').protocol)
        draft = DesignDraft(self.atlas)
        draft.clear('protocols')
        self.assertEqual(draft.to_atlas().subconcepts, (self.child,))

    def test_malformed_imports_do_not_silently_drop_child_data(self):
        for value in (None, {}, 'invalid', [None], [{}]):
            data = self.atlas.to_dict()
            data['subconcepts'] = value
            with self.subTest(value=value), self.assertRaises(AtlasError):
                Atlas.from_dict(data)

    def test_invalid_local_slots_and_relationships_are_rejected(self):
        for slot in (-1, 8, True, 1.5, '1'):
            with self.subTest(slot=slot), self.assertRaises(AtlasError):
                replace(self.child, orbit_slot=slot)
        with self.assertRaises(AtlasError):
            replace(self.child, relationship='unknown')

    def test_invalid_child_content_is_rejected(self):
        for field, value in (('id', ''), ('parent_id', ''), ('name', ''), ('name', 'line\nbreak'), ('notes', '\x00'), ('notes', 1)):
            with self.subTest(field=field), self.assertRaises(AtlasError):
                replace(self.child, **{field: value})

    def test_orbit_slots_are_unique_evenly_spaced_and_on_the_parent_layer(self):
        from math import dist
        center = node_position(self.parent)
        points = [orbit_position(self.parent, slot) for slot in range(8)]
        self.assertEqual(len(set(points)), 8)
        for index, point in enumerate(points):
            self.assertEqual(point[2], center[2])
            self.assertAlmostEqual(dist(point, center), ORBIT_RADIUS)
            self.assertAlmostEqual(dist(point, points[(index+1) % 8]), dist(points[0], points[1]))

    def test_parent_movement_translates_orbit_without_changing_local_positions(self):
        moved = replace(self.parent, layer=4, depth=2, slot=9)
        before, after = node_position(self.parent), node_position(moved)
        for slot in range(8):
            old, new = orbit_position(self.parent, slot), orbit_position(moved, slot)
            for axis in range(3):
                self.assertAlmostEqual(new[axis]-old[axis], after[axis]-before[axis])

    def test_orbit_radius_is_independent_of_parent_block_size(self):
        from math import dist
        for span in (1, 2, 4, 8, 16):
            parent = replace(self.parent, span=span)
            self.assertAlmostEqual(dist(node_position(parent), orbit_position(parent, 0)), ORBIT_RADIUS)

    def test_migrated_first_save_keeps_original_file_as_backup(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'atlas.json'
            data = Atlas((self.parent,)).to_dict()
            data['version'] = 8
            del data['subconcepts']
            path.write_text(json.dumps(data), encoding='utf-8')
            original = path.read_bytes()
            write_atlas(path, read_atlas(path).with_child(self.child))
            self.assertEqual(read_atlas(path), self.atlas)
            self.assertEqual(path.with_suffix('.json.bak').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
