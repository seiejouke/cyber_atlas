"""Saved history, crash recovery, preservation and portable snapshot archives."""
from dataclasses import replace
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import zipfile

from atlas.history import HistoryError, HistoryStore, describe_changes
from atlas.model import Atlas, Design, InformationEntry, Layer, Subconcept, example_atlas
from atlas.storage import read_atlas, write_atlas


class Interrupted(BaseException):
    pass


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "atlas.json"
        self.original = example_atlas()
        write_atlas(self.path, self.original, backup=False)
        self.store = HistoryStore(self.path)
        self.store.initialize(self.original)

    def changed(self, text="New saved information"):
        return self.original.with_node(replace(self.original.nodes[0], notes=text))

    def test_baseline_observes_existing_content_without_rewriting_or_inventing_dates(self):
        before = self.path.read_bytes()
        revisions = self.store.revisions()
        self.assertEqual(len(revisions), 1)
        baseline = revisions[0]
        self.assertEqual(baseline.kind, "baseline")
        self.assertEqual(baseline.changes, ())
        self.assertIn("unknown creation dates", baseline.summary)
        self.assertIsNotNone(datetime.fromisoformat(baseline.recorded_at).utcoffset())
        self.assertEqual(self.store.load(baseline.id), self.original)
        self.store.initialize(self.original)
        self.assertEqual(self.store.revisions(), revisions)
        self.assertEqual(self.path.read_bytes(), before)

    def test_no_op_does_not_create_a_revision_or_replace_the_backup(self):
        writer = Mock()
        result = self.store.save(self.original, expected=self.original, writer=writer)
        self.assertFalse(result.changed)
        writer.assert_not_called()
        self.assertEqual(len(self.store.revisions()), 1)
        self.assertFalse(self.path.with_suffix(".json.bak").exists())

    def test_snapshots_preserve_nodes_children_entries_design_and_exact_coordinates(self):
        parent = self.original.nodes[0]
        child = Subconcept("child", parent.id, "Saved variant", "Independent notes", 3)
        changed = self.original.with_child(child).with_entry(InformationEntry("entry", child.id, "Finding", "Saved observation"))
        changed = changed.with_node(replace(parent, notes="Edited main note", slot=10))
        self.assertTrue(self.store.save(changed, expected=self.original).changed)
        revisions = self.store.revisions()
        self.assertEqual(revisions[0].parent_id, revisions[1].id)
        self.assertEqual(self.store.load(revisions[0].id), changed)
        self.assertEqual(self.store.load(revisions[1].id), self.original)
        self.assertEqual(read_atlas(self.path), changed)
        self.assertEqual(read_atlas(self.path.with_suffix(".json.bak")), self.original)
        self.assertEqual(json.loads(self.path.read_text())["version"], 10)
        self.assertEqual({c["entity"] for c in revisions[0].changes}, {"node", "subconcept", "entry"})

    def test_moves_and_design_reordering_are_identifiable(self):
        node = self.original.nodes[0]
        moved = self.original.with_node(replace(node, slot=10))
        self.assertEqual(describe_changes(self.original, moved)[0]["action"], "moved")
        reordered = replace(self.original, design=replace(self.original.design, layers=tuple(reversed(self.original.design.layers))))
        self.assertEqual(describe_changes(self.original, reordered)[0]["fields"], ["layer order"])

    def test_integer_and_text_layer_ids_stay_distinct_in_change_summaries(self):
        design = Design(layers=(Layer(1, "Numeric layer", "#112233"), Layer("1", "Text layer", "#445566")), protocols=())
        before = Atlas(design=design)
        after = Atlas(design=replace(design, layers=(replace(design.layers[0], name="Changed numeric"), replace(design.layers[1], name="Changed text"))))
        changes = [c for c in describe_changes(before, after) if c["entity"] == "layer"]
        self.assertEqual({c["id"] for c in changes}, {1, "1"})

    def test_initial_recording_can_browse_the_previous_backup_without_inventing_its_save_date(self):
        path = self.path.with_name("pre-history.json")
        write_atlas(path, self.original)
        write_atlas(path, self.changed())
        before, backup = path.read_bytes(), path.with_suffix(".json.bak").read_bytes()
        store = HistoryStore(path)
        store.initialize(self.changed())
        revisions = store.revisions()
        self.assertEqual([r.kind for r in revisions], ["baseline", "backup"])
        self.assertIn("original save date is unknown", revisions[1].summary)
        self.assertEqual(store.load(revisions[1].id), self.original)
        self.assertEqual(store.load(revisions[0].id), self.changed())
        self.assertEqual((path.read_bytes(), path.with_suffix(".json.bak").read_bytes()), (before, backup))

    def test_invalid_previous_backup_does_not_prevent_recording_a_valid_baseline(self):
        path = self.path.with_name("invalid-backup.json")
        write_atlas(path, self.original)
        backup = path.with_suffix(".json.bak")
        backup.write_bytes(b"invalid old backup")
        store = HistoryStore(path)
        store.initialize(self.original)
        self.assertEqual(len(store.revisions()), 1)
        self.assertEqual(backup.read_bytes(), b"invalid old backup")

    def test_deletion_keeps_the_older_full_cluster(self):
        parent = self.original.nodes[0]
        cluster = self.original.with_child(Subconcept("child", parent.id, "Variant", "Saved child", 0))
        self.store.save(cluster)
        previous = self.store.revisions()[0]
        deleted = cluster.without_node(parent.id, remove_children=True)
        self.store.save(deleted)
        self.assertEqual(self.store.load(previous.id), cluster)
        self.assertEqual({c["entity"] for c in self.store.revisions()[0].changes}, {"node", "subconcept"})

    def test_restore_appends_a_revision_and_keeps_the_intervening_states(self):
        baseline = self.store.revisions()[0]
        changed = self.changed()
        self.store.save(changed)
        edit = self.store.revisions()[0]
        self.store.save(self.store.load(baseline.id), expected=changed, kind="restore", summary="Restored revision #1")
        revisions = self.store.revisions()
        self.assertEqual(len(revisions), 3)
        self.assertEqual(revisions[0].kind, "restore")
        self.assertEqual(revisions[0].parent_id, edit.id)
        self.assertEqual(self.store.load(edit.id), changed)
        self.assertEqual(read_atlas(self.path), self.original)

    def test_failed_json_save_has_no_completed_revision(self):
        before = self.path.read_bytes()
        with self.assertRaises(OSError):
            self.store.save(self.changed(), writer=Mock(side_effect=OSError("Disk full")))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(self.store.revisions()), 1)
        self.store.initialize(self.original)
        self.assertEqual(len(self.store.revisions()), 1)

    def test_history_prepare_failure_prevents_overwriting_the_atlas(self):
        writer = Mock()
        with patch.object(self.store, "_insert", side_effect=HistoryError("History disk full")):
            with self.assertRaises(HistoryError):
                self.store.save(self.changed(), writer=writer)
        writer.assert_not_called()
        self.assertEqual(read_atlas(self.path), self.original)

    def test_crash_before_json_replacement_discards_the_unfinished_revision(self):
        with self.assertRaises(Interrupted):
            self.store.save(self.changed(), writer=Mock(side_effect=Interrupted()))
        self.assertEqual(len(self.store.revisions()), 1)
        reopened = HistoryStore(self.path)
        reopened.initialize(self.original)
        self.assertEqual(len(reopened.revisions()), 1)
        self.assertEqual(read_atlas(self.path), self.original)

    def test_crash_after_json_replacement_recovers_the_same_revision_once(self):
        changed = self.changed()
        def crash(path, document):
            write_atlas(path, document)
            raise Interrupted()
        with self.assertRaises(Interrupted):
            self.store.save(changed, writer=crash)
        self.assertEqual(len(self.store.revisions()), 1)
        reopened = HistoryStore(self.path)
        reopened.initialize(changed)
        revisions = reopened.revisions()
        self.assertEqual(len(revisions), 2)
        self.assertEqual(reopened.load(revisions[0].id), changed)
        reopened.initialize(changed)
        self.assertEqual(reopened.revisions(), revisions)

    def test_finalize_failure_reports_a_saved_atlas_and_is_recoverable(self):
        changed = self.changed()
        with patch.object(self.store, "_finish", side_effect=HistoryError("Temporarily locked")):
            result = self.store.save(changed)
        self.assertTrue(result.changed)
        self.assertIsNotNone(result.warning)
        self.assertEqual(read_atlas(self.path), changed)
        self.store.initialize(changed)
        self.assertEqual(len(self.store.revisions()), 2)

    def test_writer_error_after_replacement_does_not_falsely_report_an_unsaved_atlas(self):
        changed = self.changed()
        def late_error(path, document):
            write_atlas(path, document)
            raise OSError("Interrupted after replacement")
        result = self.store.save(changed, writer=late_error)
        self.assertTrue(result.changed)
        self.assertIsNotNone(result.warning)
        self.assertEqual(read_atlas(self.path), changed)
        self.assertEqual(len(self.store.revisions()), 2)

    def test_changes_from_an_older_app_are_observed_without_claiming_original_dates(self):
        changed = self.changed()
        write_atlas(self.path, changed)
        self.store.initialize(self.original)  # Persisted JSON is authoritative.
        revision = self.store.revisions()[0]
        self.assertEqual(revision.kind, "external")
        self.assertEqual(self.store.load(revision.id), changed)
        self.assertIn("Observed", revision.summary)

    def test_stale_application_cannot_overwrite_external_changes(self):
        external = self.changed("External edit")
        write_atlas(self.path, external)
        with self.assertRaisesRegex(HistoryError, "changed on disk"):
            self.store.save(self.changed("Stale app"), expected=self.original)
        self.assertEqual(read_atlas(self.path), external)

    def test_revisions_are_ordered_by_sequence_even_if_the_clock_moves_back(self):
        self.store.save(self.changed())
        latest = self.store.revisions()[0]
        with closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.execute("UPDATE revisions SET recorded_at='2000-01-01T00:00:00+00:00' WHERE id=?", (latest.id,))
        self.assertEqual(self.store.revisions()[0].id, latest.id)

    def test_damaged_snapshot_does_not_damage_other_history_or_current_notes(self):
        baseline = self.store.revisions()[0]
        self.store.save(self.changed())
        with closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.execute("UPDATE revisions SET snapshot=? WHERE id=?", (b"broken", baseline.id))
        with self.assertRaisesRegex(HistoryError, "damaged"):
            self.store.load(baseline.id)
        self.assertEqual(self.store.load(self.store.revisions()[0].id), self.changed())
        self.assertEqual(read_atlas(self.path), self.changed())

    def test_corrupt_database_is_preserved_and_cannot_cause_a_save_without_history(self):
        self.store.path.write_bytes(b"not a SQLite database")
        with self.assertRaises(HistoryError):
            self.store.save(self.changed())
        self.assertEqual(self.store.path.read_bytes(), b"not a SQLite database")
        self.assertEqual(read_atlas(self.path), self.original)

    def test_newer_history_format_is_preserved(self):
        with closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.execute("PRAGMA user_version=99")
        with self.assertRaisesRegex(HistoryError, "newer"):
            self.store.save(self.changed())
        self.assertEqual(read_atlas(self.path), self.original)

    def test_independent_atlas_files_have_independent_histories(self):
        other = HistoryStore(self.path.with_name("second.json"))
        other.initialize(self.original)
        self.store.save(self.changed())
        self.assertEqual(len(other.revisions()), 1)
        self.assertNotEqual(self.store.path, other.path)
        self.assertNotEqual(self.store.revisions()[-1].id, other.revisions()[0].id)

    def test_export_contains_independently_loadable_json_states_and_metadata(self):
        self.store.save(self.changed())
        revisions, before = self.store.revisions(), self.path.read_bytes()
        archive = self.path.with_name("history.zip")
        self.store.export(archive)
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(bundle.read("history.json"))
            self.assertEqual(manifest["type"], "cyber-atlas-history")
            self.assertEqual(len(manifest["revisions"]), 2)
            self.assertEqual(Atlas.from_dict(json.loads(bundle.read("atlas.json"))), self.changed())
            for revision in manifest["revisions"]:
                self.assertEqual(Atlas.from_dict(json.loads(bundle.read(revision["file"]))), self.store.load(revision["id"]))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.revisions(), revisions)

    def test_failed_export_preserves_the_previous_archive_and_cleans_the_temp_file(self):
        archive = self.path.with_name("history.zip")
        archive.write_bytes(b"previous archive")
        with patch("atlas.history.zipfile.ZipFile.writestr", side_effect=OSError("Export disk full")):
            with self.assertRaises(OSError):
                self.store.export(archive)
        self.assertEqual(archive.read_bytes(), b"previous archive")
        self.assertFalse(list(self.path.parent.glob(".history-export-*")))

    def test_export_cannot_overwrite_the_current_atlas_history_or_backup(self):
        for target in (self.path, self.store.path, self.path.with_suffix(".json.bak"),
                       *(self.store.path.with_name(self.store.path.name + suffix) for suffix in ("-journal", "-wal", "-shm"))):
            with self.assertRaisesRegex(HistoryError, "separate ZIP"):
                self.store.export(target)
        self.assertEqual(read_atlas(self.path), self.original)


if __name__ == "__main__":
    unittest.main()
