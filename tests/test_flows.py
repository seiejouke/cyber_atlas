from dataclasses import replace
from contextlib import closing
import json
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from atlas.design_draft import DesignDraft
from atlas.flow import FlowRun, flow_curve
from atlas.heat import information_heat
from atlas.history import HistoryStore, describe_changes
from atlas.model import Atlas, AtlasError, FlowNote, FlowStep, FlowConnection, Node, Subconcept, example_atlas
from atlas.storage import read_atlas, write_atlas
from atlas.study_text import concept_link, study_spans


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.atlas = example_atlas()
        self.a = FlowStep('a', self.atlas.nodes[0].id, 'Receive', self.atlas.nodes[0].name)
        self.b = FlowStep('b', self.atlas.nodes[1].id, 'Inspect', self.atlas.nodes[1].name,
                          '## Mechanism\nRead **the destination**.', 'What changes?')
        self.c = replace(self.a, id='c', title='Send')
        self.ab = FlowConnection('ab', 'a', 'b')
        self.bc = FlowConnection('bc', 'b', 'c', 'Allowed')
        self.end = FlowConnection('end', 'b', None, 'Blocked')
        self.flow = FlowNote('flow', 'Packet path', 'An introduction', (self.a, self.b, self.c), (self.ab, self.bc, self.end))
        self.document = self.atlas.with_flow(self.flow)

    def test_repeated_concepts_have_distinct_steps_and_one_canonical_note(self):
        self.assertEqual(self.a.concept_id, self.c.concept_id)
        self.assertNotEqual(self.a.id, self.c.id)
        self.assertEqual(self.document.nodes, self.atlas.nodes)
        self.assertEqual(self.document.concept(self.a.concept_id), self.atlas.nodes[0])

    def test_storage_export_backup_roundtrip(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'atlas.json'
            write_atlas(path, self.atlas)
            write_atlas(path, self.document)
            self.assertEqual(read_atlas(path), self.document)
            self.assertEqual(read_atlas(path.with_suffix('.json.bak')), self.atlas)
            self.assertEqual(json.loads(path.read_text())['version'], 11)

    def test_legacy_atlas_loads_without_flows_and_cannot_claim_old_version_with_flows(self):
        for version in (9, 10):
            data = self.atlas.to_dict()
            data.update(version=version)
            data.pop('flows')
            self.assertEqual(Atlas.from_dict(data), self.atlas)
        data = self.document.to_dict()
        data['version'] = 10
        with self.assertRaisesRegex(AtlasError, 'version 11'):
            Atlas.from_dict(data)

    def test_rename_move_and_delete_preserve_repairable_references(self):
        parent = self.atlas.nodes[0]
        moved = self.document.with_node(replace(parent, name='Renamed', depth=4))
        self.assertEqual(moved.flows, self.document.flows)
        deleted = moved.without_node(parent.id)
        self.assertEqual(deleted.flows, moved.flows)
        self.assertIsNone(deleted.concept(self.a.concept_id))
        self.assertEqual(deleted.flows[0].steps[0].concept_name, parent.name)
        self.assertEqual(Atlas.from_dict(deleted.to_dict()), deleted)

    def test_subconcept_references_survive_parent_movement_and_child_deletion(self):
        child = Subconcept('child', self.a.concept_id, 'Subtype', 'Child note')
        flow = replace(self.flow, steps=(replace(self.a, concept_id='child', concept_name=child.name), self.b, self.c))
        atlas = self.atlas.with_child(child).with_flow(flow)
        self.assertEqual(atlas.concept('child'), child)
        self.assertEqual(atlas.without_child('child').flows, atlas.flows)
        self.assertEqual(atlas.without_node(child.parent_id, remove_children=True).flows, atlas.flows)

    def test_design_edits_and_protocol_clearing_keep_flows(self):
        self.assertEqual(DesignDraft(self.document).to_atlas(), self.document)
        self.assertEqual(self.document.with_design(self.document.design).flows, self.document.flows)
        self.assertEqual(self.document.without_protocols().flows, self.document.flows)

    def test_flow_references_never_add_heat(self):
        self.assertEqual(information_heat(self.document), information_heat(self.atlas))

    def test_canonical_note_edit_is_read_through_each_reference(self):
        changed = self.document.with_node(replace(self.atlas.nodes[0], notes='One updated explanation'))
        self.assertEqual(changed.concept(self.a.concept_id).notes, changed.concept(self.c.concept_id).notes)
        self.assertEqual(changed.flows, self.document.flows)

    def test_missing_references_are_explicitly_retained_on_import(self):
        flow = replace(self.flow, steps=(replace(self.a, concept_id='missing'), self.b, self.c))
        self.assertEqual(Atlas.from_dict(self.atlas.with_flow(flow).to_dict()).flows, (flow,))

    def test_invalid_step_and_edge_identity_and_endpoints_are_rejected(self):
        for changes in ({'steps': (self.a, self.a)}, {'start_step_id': 'absent'},
                        {'connections': (replace(self.ab, target_id='outside'),)},
                        {'connections': (self.ab, self.ab)}):
            with self.subTest(changes=changes), self.assertRaises(AtlasError):
                replace(self.flow, **changes)

    def test_branch_labels_are_required_and_case_insensitively_distinct(self):
        for label in ('', 'allowed', 'Allowed '):
            with self.subTest(label=label), self.assertRaises(AtlasError):
                replace(self.flow, connections=(self.bc, replace(self.end, label=label)))

    def test_raw_lists_malformed_text_and_oversized_flows_are_rejected(self):
        for field, value in (('steps', {}), ('connections', [None]), ('start_step_id', []), ('title', 2)):
            data = self.flow.to_dict()
            data[field] = value
            with self.subTest(field=field), self.assertRaises(AtlasError):
                FlowNote.from_dict(data)
        with self.assertRaises(AtlasError):
            FlowStep('a', 'x', 'Title', explanation='\x00')
        with self.assertRaises(AtlasError):
            replace(self.flow, steps=tuple(replace(self.a, id=str(i)) for i in range(257)))

    def test_duplicate_flow_ids_and_unknown_delete_rejected(self):
        with self.assertRaises(AtlasError):
            replace(self.document, flows=(self.flow, self.flow))
        with self.assertRaises(AtlasError):
            self.document.without_flow('unknown')
        self.assertEqual(self.document.without_flow('flow'), self.atlas)

    def test_format_11_requires_an_explicit_valid_flow_list(self):
        for value in (None, {}, 'bad'):
            data = self.atlas.to_dict()
            data['flows'] = value
            with self.subTest(value=value), self.assertRaises(AtlasError):
                Atlas.from_dict(data)
        data = self.atlas.to_dict()
        data.pop('flows')
        with self.assertRaises(AtlasError):
            Atlas.from_dict(data)

    def test_opening_legacy_history_does_not_record_a_schema_only_content_change(self):
        import hashlib
        import sqlite3
        import zlib
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'atlas.json'
            legacy = self.atlas.to_dict()
            legacy['version'] = 10
            legacy.pop('flows')
            path.write_text(json.dumps(legacy), encoding='utf-8')
            saved = path.read_bytes()
            store = HistoryStore(path)
            store.initialize(self.atlas)
            content = json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
            with closing(sqlite3.connect(store.path)) as connection, connection:
                connection.execute('UPDATE revisions SET format_version=10,content_hash=?,snapshot=?',
                                   (hashlib.sha256(content).hexdigest(), zlib.compress(content)))
            revisions = store.revisions()
            store.initialize(read_atlas(path))
            self.assertEqual(store.revisions(), revisions)
            self.assertEqual(path.read_bytes(), saved)
            store.save(self.document, expected=self.atlas, writer=write_atlas)
            self.assertEqual(len(store.revisions()), len(revisions)+1)
            self.assertEqual(store.revisions()[0].changes[0]['entity'], 'flow')
            self.assertEqual(store.load(revisions[0].id), self.atlas)

    def test_history_restores_flows_and_archives_full_process_content(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'atlas.json'
            write_atlas(path, self.atlas)
            store = HistoryStore(path)
            store.initialize(self.atlas)
            store.save(self.document, expected=self.atlas, writer=write_atlas)
            latest = store.revisions()[0]
            self.assertEqual(store.load(latest.id), self.document)
            self.assertTrue(any(change['entity'] == 'flow' for change in latest.changes))
            changed = self.document.with_flow(replace(self.flow, steps=(self.a, replace(self.b, explanation='New explanation'), self.c)))
            self.assertEqual(describe_changes(self.document, changed)[0]['fields'], ['steps'])
            archive = Path(folder) / 'history.zip'
            store.export(archive)
            import zipfile
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(Atlas.from_dict(json.loads(bundle.read('atlas.json'))), self.document)

    def test_manual_branching_and_previous_retraces_the_chosen_route(self):
        run = FlowRun(self.flow)
        run.next()
        self.assertEqual(run.current, 'b')
        with self.assertRaisesRegex(AtlasError, 'Choose a branch'):
            run.next()
        run.next('bc')
        self.assertEqual(run.current, 'c')
        run.previous()
        self.assertEqual((run.current, run.arrival), ('b', 'ab'))
        run.next('end')
        self.assertTrue(run.finished)
        self.assertEqual(run.choices, ())
        run.previous()
        self.assertEqual(run.current, 'b')
        self.assertFalse(run.finished)

    def test_terminal_step_and_empty_flow_complete_without_fabricating_connections(self):
        run = FlowRun(self.flow, 'c')
        run.next()
        self.assertTrue(run.finished)
        run.previous()
        self.assertFalse(run.finished)
        empty = FlowRun(FlowNote.create())
        empty.next()
        self.assertIsNone(empty.current)

    def test_loops_self_links_repeated_concepts_and_jump(self):
        flow = replace(self.flow, connections=(self.ab, FlowConnection('ba', 'b', 'a')))
        run = FlowRun(flow)
        for _ in range(4):
            run.next()
        self.assertEqual(run.current, 'a')
        self.assertEqual(len(run.trail), 4)
        run.jump('b')
        self.assertEqual(run.trail, [])
        with self.assertRaises(AtlasError):
            run.jump('absent')
        with self.assertRaises(AtlasError):
            run.next('ab')

    def test_curves_are_finite_trimmed_and_support_same_position(self):
        curve = flow_curve((0, 0, 0), (3, 1, 5))
        self.assertEqual(len(curve), 32)
        self.assertNotEqual(curve[0], (0, 0, 0))
        self.assertNotEqual(curve[-1], (3, 1, 5))
        self.assertTrue(all(isfinite(v) for p in curve for v in p))
        loop = flow_curve((1, 2, 3), (1, 2, 3))
        self.assertTrue(all(isfinite(v) for p in loop for v in p))
        self.assertNotEqual(loop[0], loop[-1])

    def test_study_markup_is_readable_inert_and_links_use_stable_encoded_ids(self):
        link = concept_link('concept with spaces/1', 'A concept')
        spans = study_spans('## Definition\n- **Strong** and *emphasis* and `code`\n' + link + '\n<script>literal</script>')
        self.assertTrue(any('h2' in span.tags for span in spans))
        self.assertTrue(any('bold' in span.tags for span in spans))
        self.assertTrue(any('italic' in span.tags for span in spans))
        self.assertTrue(any('code' in span.tags for span in spans))
        self.assertEqual(next(span.concept_id for span in spans if span.concept_id), 'concept with spaces/1')
        self.assertIn('<script>literal</script>', ''.join(span.text for span in spans))
