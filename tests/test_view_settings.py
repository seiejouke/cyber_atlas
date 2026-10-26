"""View preferences cannot alter the atlas or an existing preference on failure."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from atlas.view_settings import navigation_collapsed, save_navigation_collapsed


class ViewSettingsTests(unittest.TestCase):
    def test_missing_preferences_start_expanded_without_creating_a_file(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "view-settings.json"
            self.assertFalse(navigation_collapsed(path))
            self.assertFalse(path.exists())

    def test_round_trip_preserves_other_preferences(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "view-settings.json"
            path.write_text(json.dumps({"future_preference": "retain"}), encoding="utf-8")
            for state in (True, False):
                save_navigation_collapsed(path, state)
                self.assertEqual(navigation_collapsed(path), state)
                self.assertEqual(json.loads(path.read_text())["future_preference"], "retain")

    def test_bad_preferences_fall_back_to_expanded(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "view-settings.json"
            for content in ("{broken", "null", "[]", "true", '{"navigation_collapsed": "true"}',
                            '{"navigation_collapsed": 1}', "x" * 32769):
                path.write_text(content, encoding="utf-8")
                self.assertFalse(navigation_collapsed(path), content[:50])
            path.write_bytes(b"\xff\xfe")
            self.assertFalse(navigation_collapsed(path))

    def test_failed_replace_keeps_the_previous_file_and_cleans_up(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "view-settings.json"
            save_navigation_collapsed(path, True)
            original = path.read_bytes()
            with patch("atlas.storage.os.replace", side_effect=OSError("read only")):
                with self.assertRaises(OSError):
                    save_navigation_collapsed(path, False)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_creates_a_new_preferences_directory(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "settings" / "view-settings.json"
            save_navigation_collapsed(path, True)
            self.assertTrue(navigation_collapsed(path))


if __name__ == "__main__":
    unittest.main()
