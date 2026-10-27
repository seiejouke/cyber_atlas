import hashlib
import json
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from tools import release_legal


class ReleaseLegalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.prefix = self.root / "python"
        for name in ("LICENSE", "COPYRIGHT.txt", "THIRD_PARTY_NOTICES.md", "main.py",
                     "requirements.txt", "tools/build_windows.py", "tools/build_linux.py",
                     "tools/release_legal.py", "docs/DEVELOPMENT.md"):
            self.write(self.project / name, f"Project content: {name}\n")
        self.write(self.prefix / "LICENSE.txt", "Python runtime license\n")
        for directory, name, script in (("_tcl_data", "Tcl", "init.tcl"), ("_tk_data", "Tk", "tk.tcl")):
            self.write(self.bundle / "_internal" / directory / script, f"package require -exact {name} 8.6.13\n")
            self.write(self.bundle / "_internal" / directory / "license.terms", f"{name} runtime license\n")
        self.distributions = {}
        for name in ("vtk", "numpy", "pyinstaller"):
            relative = PurePosixPath(f"{name}-1.0.dist-info/licenses/LICENSE.txt")
            self.write(self.root / "installed" / relative, f"{name} primary license\n")
            self.distributions[name] = SimpleNamespace(
                version="1.0", files=[relative], locate_file=lambda item: self.root / "installed" / item)
        self.patch = patch.object(release_legal.metadata, "distribution", side_effect=self.distributions.__getitem__)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def collect(self):
        release_legal.include_legal_files(self.bundle, project=self.project, prefix=self.prefix)

    def test_bundle_has_verbatim_notices_versions_and_hashes(self):
        self.collect()
        self.assertEqual((self.bundle / "LICENSE").read_bytes(), (self.project / "LICENSE").read_bytes())
        directory = self.bundle / "Third-party notices"
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({item["name"] for item in manifest["components"]},
                         {"vtk", "numpy", "pyinstaller", "Python", "Tcl", "Tk"})
        self.assertEqual(len(manifest["sha256"]), 6)
        for name, expected in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), expected)
        self.assertEqual((directory / "Tk-license.txt").read_text(encoding="utf-8"), "Tk runtime license\n")

    def test_nested_wheel_notices_are_preserved_without_truncation(self):
        relative = PurePosixPath("numpy-1.0.dist-info/licenses/vendor/numerical/COPYING")
        text = "Additional numerical library terms\n" * 100
        self.write(self.root / "installed" / relative, text)
        self.distributions["numpy"].files.append(relative)
        self.collect()
        self.assertEqual((self.bundle / "Third-party notices/numpy/vendor/numerical/COPYING").read_text(encoding="utf-8"), text)

    def test_missing_dependency_license_stops_collection(self):
        self.distributions["vtk"].files = []
        with self.assertRaisesRegex(release_legal.NoticeError, "vtk distribution"):
            self.collect()

    def test_empty_or_missing_project_notice_stops_collection(self):
        (self.project / "COPYRIGHT.txt").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(release_legal.NoticeError, "Missing or empty"):
            self.collect()

    def test_license_metadata_cannot_escape_the_notice_directory(self):
        self.distributions["vtk"].files = [PurePosixPath("vtk-1.0.dist-info/licenses/../../outside.txt")]
        with self.assertRaisesRegex(release_legal.NoticeError, "Invalid license path"):
            self.collect()
        self.assertFalse((self.bundle / "outside.txt").exists())

    def test_only_reviewed_runtime_versions_can_use_fallback_notices(self):
        (self.bundle / "_internal/_tcl_data/license.terms").unlink()
        self.write(self.project / "packaging/licenses/Tcl-8.6.13.txt", "Reviewed Tcl license\n")
        self.collect()
        self.assertEqual((self.bundle / "Third-party notices/Tcl-license.txt").read_text(encoding="utf-8"),
                         "Reviewed Tcl license\n")

    def test_unknown_runtime_without_a_notice_fails(self):
        (self.bundle / "_internal/_tcl_data/license.terms").unlink()
        self.write(self.bundle / "_internal/_tcl_data/init.tcl", "package require -exact Tcl 9.0.0\n")
        self.write(self.project / "packaging/licenses/Tcl-8.6.13.txt", "Reviewed Tcl license\n")
        with self.assertRaisesRegex(release_legal.NoticeError, "No reviewed Tcl notice"):
            self.collect()

    def test_missing_runtime_version_is_not_silently_ignored(self):
        (self.bundle / "_internal/_tk_data/tk.tcl").unlink()
        with self.assertRaisesRegex(release_legal.NoticeError, "Cannot identify bundled Tk"):
            self.collect()

    def test_source_archive_includes_build_inputs_but_excludes_personal_data(self):
        self.write(self.project / "atlas/model.py", "SOURCE_BEING_BUILT = 'current working tree'\n")
        self.write(self.project / "atlas/__pycache__/model.pyc", "cache")
        self.write(self.project / "atlas.json", "private notes")
        self.write(self.project / "atlas.history.sqlite3", "history")
        self.write(self.project / ".venv/secret.txt", "environment")
        self.write(self.project / "dist/old-application.exe", "old release")
        self.collect()
        with zipfile.ZipFile(self.bundle / "Source code/CyberAtlas-source.zip") as archive:
            names = archive.namelist()
            self.assertIn("CyberAtlas/tools/build_linux.py", names)
            self.assertEqual(archive.read("CyberAtlas/atlas/model.py"), (self.project / "atlas/model.py").read_bytes())
            self.assertFalse(any("atlas.json" in name or "sqlite3" in name or "__pycache__" in name
                                 or ".venv" in name or "/dist/" in name for name in names))

    def test_missing_source_file_stops_collection(self):
        (self.project / "main.py").unlink()
        with self.assertRaisesRegex(release_legal.NoticeError, "Missing application source"):
            self.collect()

    def test_untracked_files_cannot_be_accidentally_included_in_a_release(self):
        (self.project / ".git").mkdir()
        result = SimpleNamespace(stdout=b"tools/private-signing-key.asc\0")
        with patch.object(release_legal.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(release_legal.NoticeError, "untracked files are never archived"):
                self.collect()
        self.assertFalse((self.bundle / "Source code/CyberAtlas-source.zip").exists())

    def test_collection_does_not_retain_stale_notices_from_an_earlier_build(self):
        self.write(self.bundle / "Third-party notices/obsolete.txt", "Old terms")
        with self.assertRaisesRegex(release_legal.NoticeError, "fresh bundle"):
            self.collect()

    def test_debian_copyright_contains_project_and_dependency_terms(self):
        self.collect()
        path = self.root / "debian/usr/share/doc/cyber-atlas/copyright"
        release_legal.write_debian_copyright(self.bundle, path)
        text = path.read_text(encoding="utf-8")
        for expected in ("Project content: LICENSE", "Project content: COPYRIGHT.txt", "vtk primary license",
                         "numpy primary license", "Python runtime license", "Tcl runtime license", "Tk runtime license"):
            self.assertIn(expected, text)
        self.assertFalse(path.is_symlink())


class UpstreamLicenseTests(unittest.TestCase):
    def test_reviewed_fallbacks_and_gpl_are_unchanged_upstream_texts(self):
        expected = {
            "LICENSE": "fb981668c18a279e285fc4d83fba1e836cc84dd4daa73c9697d3cfd2d8aca6e0",
            "packaging/licenses/Python-3.12.3.txt": "3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf",
            "packaging/licenses/Tcl-8.6.13.txt": "c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16",
            "packaging/licenses/Tk-8.6.13.txt": "2cde822b93ca16ae535c954b7dfe658b4ad10df2a193628d1b358f1765e8b198",
        }
        for name, digest in expected.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((release_legal.ROOT / name).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
