import io
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import main
from atlas.runtime import LOGGER, configure_logging, show_error


class DesktopRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.previous_handlers = LOGGER.handlers[:]
        LOGGER.handlers.clear()
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.restore_handlers)
        self.folder = Path(self.directory.name)

    def restore_handlers(self):
        for handler in LOGGER.handlers[:]:
            handler.close()
            LOGGER.removeHandler(handler)
        LOGGER.handlers.extend(self.previous_handlers)

    def test_windowed_errors_show_a_dialog_and_write_a_log_without_stderr(self):
        logfile = configure_logging(self.folder / "logs")
        with patch.object(sys, "stderr", None), patch("tkinter.messagebox.showerror") as dialog:
            show_error("A required library could not be loaded.")
        self.assertIn("A required library could not be loaded.", logfile.read_text(encoding="utf-8"))
        self.assertIn("A required library could not be loaded.", dialog.call_args.args)

    def test_unwritable_log_directory_does_not_prevent_error_reporting(self):
        with patch.object(Path, "mkdir", side_effect=PermissionError("Read only")):
            self.assertIsNone(configure_logging(self.folder))
        with patch.object(sys, "stderr", None), patch("tkinter.messagebox.showerror") as dialog:
            show_error("Startup failed.")
        dialog.assert_called_once()

    def test_self_test_refuses_default_or_existing_user_data(self):
        saved = self.folder / "atlas.json"
        saved.write_text("Keep this user's data", encoding="utf-8")
        report = self.folder / "report.json"
        for arguments in (("--self-test", str(report)),
                          ("--file", str(saved), "--self-test", str(report)),
                          ("--file", str(report), "--self-test", str(report))):
            with self.subTest(arguments=arguments), patch.object(sys, "argv", ["CyberAtlas", *arguments]), \
                 patch.object(sys, "stderr", io.StringIO()), patch("main.configure_logging") as logging:
                with self.assertRaises(SystemExit) as error:
                    main.main()
                self.assertEqual(error.exception.code, 2)
                logging.assert_not_called()
        self.assertEqual(saved.read_text(encoding="utf-8"), "Keep this user's data")
        self.assertFalse(report.exists())

    def test_missing_dependencies_produce_a_visible_error_before_creating_an_atlas(self):
        atlas = self.folder / "atlas.json"
        with patch.object(sys, "argv", ["CyberAtlas", "--file", str(atlas)]), \
             patch.dict(sys.modules, {"atlas.ui": None}), patch("main.show_error") as dialog:
            self.assertEqual(main.main(), 1)
        self.assertIn("dependency could not be loaded", dialog.call_args.args[0])
        self.assertFalse(atlas.exists())


if __name__ == "__main__":
    unittest.main()
