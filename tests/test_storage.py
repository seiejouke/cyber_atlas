from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from atlas.model import Atlas, AtlasError, example_atlas
from atlas.storage import read_atlas, write_atlas


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "data" / "atlas.json"
        self.atlas = example_atlas()

    def test_creates_parent_folder(self):
        write_atlas(self.path, self.atlas)
        self.assertEqual(read_atlas(self.path), self.atlas)

    def test_backup_retains_previous_document(self):
        write_atlas(self.path, self.atlas)
        changed = self.atlas.with_node(replace(self.atlas.get("11"), notes="New finding"))
        write_atlas(self.path, changed)
        self.assertEqual(read_atlas(self.path), changed)
        self.assertEqual(read_atlas(self.path.with_suffix(".json.bak")), self.atlas)

    def test_unicode_notes_roundtrip(self):
        changed = self.atlas.with_node(replace(self.atlas.get("11"), notes="Nederlands: priv\u00e9. Symbol: \u2192."))
        write_atlas(self.path, changed)
        self.assertEqual(read_atlas(self.path), changed)

    def test_empty_document_roundtrip(self):
        write_atlas(self.path, Atlas())
        self.assertEqual(read_atlas(self.path), Atlas())

    def test_malformed_json_rejected(self):
        self.path.parent.mkdir()
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(AtlasError):
            read_atlas(self.path)

    def test_corrupt_atlas_does_not_replace_good_backup(self):
        write_atlas(self.path, self.atlas)
        write_atlas(self.path, Atlas())
        backup = self.path.with_suffix(".json.bak")
        backup_bytes = backup.read_bytes()
        self.path.write_text("corrupt", encoding="utf-8")
        with self.assertRaises(AtlasError):
            write_atlas(self.path, self.atlas)
        self.assertEqual(backup.read_bytes(), backup_bytes)
        self.assertEqual(self.path.read_text(), "corrupt")

    def test_failed_atomic_replace_leaves_original_untouched(self):
        write_atlas(self.path, self.atlas)
        before = self.path.read_bytes()
        with patch("atlas.storage.os.replace", side_effect=PermissionError("Read-only test")):
            with self.assertRaises(PermissionError):
                write_atlas(self.path, Atlas(), backup=False)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(list(self.path.parent.glob(".atlas.json.*")))

    def test_file_size_limit(self):
        write_atlas(self.path, self.atlas)
        with patch("atlas.storage.MAX_FILE_BYTES", 20):
            with self.assertRaises(AtlasError):
                read_atlas(self.path)
            with self.assertRaises(AtlasError):
                write_atlas(self.path, self.atlas)

    def test_byte_order_mark_supported(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps(self.atlas.to_dict()), encoding="utf-8-sig")
        self.assertEqual(read_atlas(self.path), self.atlas)

    def test_first_save_of_v5_preserves_original_backup_and_all_notes(self):
        data = self.atlas.to_dict()
        data.update(version=5, layout="equal-rings")
        data.pop("angular_slots")
        for node in data["nodes"]:
            node.pop("slot")
            node.pop("span")
        self.path.parent.mkdir()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        original = self.path.read_bytes()
        migrated = read_atlas(self.path)
        self.assertEqual(migrated, self.atlas)
        write_atlas(self.path, migrated)
        self.assertEqual(self.path.with_suffix(".json.bak").read_bytes(), original)
        self.assertEqual(json.loads(self.path.read_text())["version"], 9)
        self.assertEqual(read_atlas(self.path), migrated)

    def test_overfull_legacy_ring_load_leaves_file_untouched(self):
        data = {"type": "cyber-knowledge-atlas", "version": 5, "layout": "equal-rings",
                "center_depth": -1, "radial_bands": self.atlas.to_dict()["radial_bands"],
                "nodes": [{"id": str(i), "name": str(i), "layer": 7, "protocol": "SSH", "depth": 2}
                          for i in range(17)]}
        self.path.parent.mkdir()
        self.path.write_text(json.dumps(data), encoding="utf-8")
        original = self.path.read_bytes()
        with self.assertRaisesRegex(AtlasError, "more than 16"):
            read_atlas(self.path)
        self.assertEqual(self.path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
