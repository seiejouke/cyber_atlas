from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from atlas import __version__
from atlas import updates


def release_data(version="99.0.0", content=b"verified installer", kind="windows"):
    name = {"windows": f"CyberAtlas-{version}-Setup.exe", "appimage": f"CyberAtlas-{version}-x86_64.AppImage",
            "deb": f"cyber-atlas_{version}_amd64.deb"}[kind]
    return {"tag_name": "v" + version, "html_url": f"{updates.RELEASES_URL}/tag/v{version}",
            "body": "Changes in this release", "draft": False, "prerelease": False,
            "assets": [{"name": name, "browser_download_url": f"{updates.RELEASES_URL}/download/v{version}/{name}",
                        "state": "uploaded", "size": len(content), "digest": "sha256:" + hashlib.sha256(content).hexdigest()}]}


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.context = updates.UpdateContext("windows", self.directory / "App with spaces" / "CyberAtlas.exe")
        self.content = b"verified installer"
        self.release = updates.parse_release(release_data(), self.context)

    def test_versions_compare_numerically_and_only_newer_versions_are_offered(self):
        self.assertGreater(updates.version_tuple("0.10.0"), updates.version_tuple("0.9.9"))
        self.assertTrue(self.release.newer)
        self.assertFalse(updates.parse_release(release_data(__version__), self.context).newer)
        self.assertFalse(updates.parse_release(release_data("0.0.1"), self.context).newer)

    def test_prereleases_and_invalid_versions_are_not_installable(self):
        for version in ("v1.2", "1.2.3-beta", "../1.2.3", "01.2.3", "1.2.3.4", None):
            with self.subTest(version=version), self.assertRaises(updates.UpdateError):
                updates.version_tuple(version)
        for flag in ("draft", "prerelease"):
            data = release_data()
            data[flag] = True
            with self.assertRaises(updates.UpdateError):
                updates.parse_release(data, self.context)

    def test_release_and_package_must_belong_to_this_repository(self):
        for key in ("html_url", "browser_download_url"):
            data = release_data()
            if key == "html_url":
                data[key] = "https://github.com/someone/else/releases/tag/v99.0.0"
            else:
                data["assets"][0][key] = "https://example.com/installer.exe"
            with self.subTest(key=key), self.assertRaises(updates.UpdateError):
                updates.parse_release(data, self.context)

    def test_matching_platform_package_requires_a_digest_and_valid_size(self):
        for changed in ({"digest": None}, {"digest": "sha256:" + "z" * 64}, {"size": -1},
                        {"size": True}, {"size": updates.MAX_DOWNLOAD + 1}, {"state": "starter"}):
            data = release_data()
            data["assets"][0].update(changed)
            with self.subTest(changed=changed), self.assertRaises(updates.UpdateError):
                updates.parse_release(data, self.context)

    def test_missing_or_duplicate_packages_fail_without_falling_back_to_a_different_platform(self):
        for assets in ([], release_data()["assets"] * 2, release_data(kind="deb")["assets"]):
            data = release_data()
            data["assets"] = assets
            with self.assertRaises(updates.UpdateError):
                updates.parse_release(data, self.context)

    def test_portable_and_source_copies_get_release_notifications_without_an_installer(self):
        for kind in ("portable", "source", "manual"):
            release = updates.parse_release(release_data(), updates.UpdateContext(kind))
            self.assertTrue(release.newer)
            self.assertIsNone(release.asset)

    def test_linux_selects_the_correct_package(self):
        data = release_data(kind="deb")
        data["assets"].extend(release_data(kind="appimage")["assets"])
        self.assertTrue(updates.parse_release(data, updates.UpdateContext("deb")).asset.name.endswith(".deb"))
        self.assertTrue(updates.parse_release(data, updates.UpdateContext("appimage")).asset.name.endswith(".AppImage"))

    def test_malformed_release_data_produces_an_actionable_error(self):
        for data in (None, [], {}, {"tag_name": "v1.0.0", "html_url": "bad"}):
            with self.subTest(data=data), self.assertRaises(updates.UpdateError):
                updates.parse_release(data, self.context)

    def test_preferences_default_to_off_and_never_require_network_access(self):
        path = self.directory / "updates.json"
        with patch("atlas.updates._open") as network:
            self.assertEqual(updates.load_settings(path), updates.UpdateSettings())
            network.assert_not_called()
        self.assertFalse(path.exists())

    def test_automatic_checks_are_limited_to_once_per_day(self):
        self.assertFalse(updates.UpdateSettings(False, 0).due(100000))
        self.assertFalse(updates.UpdateSettings(True, 100000).due(100000 + updates.CHECK_INTERVAL - 1))
        self.assertTrue(updates.UpdateSettings(True, 100000).due(100000 + updates.CHECK_INTERVAL))
        self.assertTrue(updates.UpdateSettings(True, 200000).due(100000))

    def test_preferences_roundtrip_separately_from_atlas_data(self):
        path, atlas = self.directory / "updates.json", self.directory / "atlas.json"
        atlas.write_bytes(b"notes stay unchanged")
        setting = updates.UpdateSettings(True, 123456)
        updates.save_settings(path, setting)
        self.assertEqual(updates.load_settings(path), setting)
        self.assertEqual(atlas.read_bytes(), b"notes stay unchanged")
        self.assertEqual(list(self.directory.glob(".updates-*")), [])

    def test_corrupt_or_untrusted_preferences_do_not_opt_users_in(self):
        path = self.directory / "updates.json"
        for text in ("broken", "[]", '{"automatic":"yes"}', '{"automatic":true,"last_check":NaN}',
                     '{"automatic":true,"last_check":-1}', " " * 32769):
            path.write_text(text)
            with self.subTest(text=text[:60]):
                self.assertFalse(updates.load_settings(path).automatic)

    def test_metadata_response_is_parsed_without_downloading_a_package(self):
        with patch("atlas.updates._open", return_value=io.BytesIO(json.dumps(release_data()).encode())) as request:
            self.assertEqual(updates.check_release(self.context), self.release)
        request.assert_called_once_with(updates.LATEST_API, metadata=True)

    def test_oversized_metadata_is_rejected(self):
        with patch("atlas.updates._open", return_value=io.BytesIO(b" " * (1024 * 1024 + 1))):
            with self.assertRaises(updates.UpdateError):
                updates.check_release(self.context)

    def test_offline_and_rate_limited_checks_have_clear_errors(self):
        for error, expected in ((OSError("offline"), "connection"),
                                (urllib.error.HTTPError(updates.LATEST_API, 429, "Limited", {}, None), "limiting")):
            with patch("atlas.updates._open", side_effect=error), self.assertRaisesRegex(updates.UpdateError, expected):
                updates.check_release(self.context)

    def test_redirects_cannot_downgrade_https_or_leave_release_download_hosts(self):
        request = urllib.request.Request(self.release.asset.url)
        handler = updates._ReleaseRedirects()
        for url in ("http://release-assets.githubusercontent.com/file", "https://example.com/file",
                    "https://github.com.evil.example/file", "https://user:password@github.com/file"):
            with self.subTest(url=url), self.assertRaises(updates.UpdateError):
                handler.redirect_request(request, None, 302, "Found", {}, url)

    def test_verified_download_is_published_atomically_and_can_be_reused(self):
        progress = []
        with patch("atlas.updates._open", return_value=io.BytesIO(self.content)) as request:
            path = updates.download_release(self.release, self.directory, threading.Event(), lambda a, b: progress.append((a, b)))
        self.assertTrue(updates.verify_download(path, self.release.asset))
        self.assertEqual(progress[-1], (len(self.content), len(self.content)))
        with patch("atlas.updates._open") as request:
            self.assertEqual(updates.download_release(self.release, self.directory, threading.Event()), path)
            request.assert_not_called()
        self.assertEqual(list(self.directory.rglob("*.part")), [])

    def test_truncated_changed_and_oversized_downloads_are_never_kept(self):
        for content in (self.content[:-1], b"x" * len(self.content), self.content + b"extra"):
            with patch("atlas.updates._open", return_value=io.BytesIO(content)), self.assertRaises(updates.UpdateError):
                updates.download_release(self.release, self.directory, threading.Event())
            self.assertFalse((self.directory / self.release.version / self.release.asset.name).exists())
            self.assertEqual(list(self.directory.rglob("*.part")), [])

    def test_cancelling_a_download_removes_the_partial_file(self):
        cancel = threading.Event()
        cancel.set()
        with patch("atlas.updates._open", return_value=io.BytesIO(self.content)), self.assertRaises(updates.DownloadCancelled):
            updates.download_release(self.release, self.directory, cancel)
        self.assertEqual(list(self.directory.rglob("*.part")), [])
        self.assertFalse((self.directory / self.release.version / self.release.asset.name).exists())

    def test_download_rejects_directory_traversal_and_foreign_urls(self):
        for asset in (replace(self.release.asset, name="../outside.exe"),
                      replace(self.release.asset, url="https://example.com/installer.exe")):
            with patch("atlas.updates._open") as request, self.assertRaises(updates.UpdateError):
                updates.download_release(replace(self.release, asset=asset), self.directory, threading.Event())
            request.assert_not_called()

    def test_modified_installer_cannot_launch_the_windows_helper(self):
        path = self.directory / "installer.exe"
        path.write_bytes(b"changed")
        with patch("atlas.updates.subprocess.Popen") as start, self.assertRaises(updates.UpdateError):
            updates.start_windows_update(path, self.release.asset, self.context, self.directory / "atlas.json", self.directory / "cache")
        start.assert_not_called()

    def test_windows_handoff_uses_data_not_shell_interpolation_and_preserves_the_atlas_path(self):
        path = self.directory / self.release.asset.name
        path.write_bytes(self.content)
        atlas = self.directory / "Notes with spaces and $symbols.json"
        atlas.write_bytes(b"saved notes")
        def started(command, **kwargs):
            data = json.loads(Path(command[-1]).read_text())
            Path(data["ready"]).touch()
            return SimpleNamespace(poll=lambda: None)

        with patch("atlas.updates.subprocess.Popen", side_effect=started) as start:
            updates.start_windows_update(path, self.release.asset, self.context, atlas, self.directory / "cache")
        command = start.call_args.args[0]
        self.assertIn("Hidden", command)
        self.assertNotIn("-Command", command)
        payload = json.loads(Path(command[-1]).read_text())
        self.assertIn(str(atlas.resolve()), payload["restart_arguments"])
        self.assertIn("/NOCLOSEAPPLICATIONS", payload["installer_arguments"])
        self.assertIn(str(self.context.executable.parent), payload["installer_arguments"])
        self.assertEqual(payload["sha256"], self.release.asset.sha256)
        self.assertEqual(atlas.read_bytes(), b"saved notes")

    def test_a_blocked_windows_helper_does_not_report_a_successful_handoff(self):
        path = self.directory / self.release.asset.name
        path.write_bytes(self.content)
        with patch("atlas.updates.subprocess.Popen", return_value=SimpleNamespace(poll=lambda: 1)), self.assertRaisesRegex(updates.UpdateError, "still open"):
            updates.start_windows_update(path, self.release.asset, self.context, self.directory / "notes.json", self.directory / "cache")

    def test_installed_detection_requires_the_registered_application_directory(self):
        executable = self.directory / "Installed app/CyberAtlas.exe"
        registry = SimpleNamespace(KEY_WOW64_64KEY=1, KEY_WOW64_32KEY=2, HKEY_CURRENT_USER=3, KEY_READ=4)
        from unittest.mock import MagicMock
        registry.OpenKey = MagicMock()
        registry.QueryValueEx = MagicMock(return_value=(str(executable.parent), 1))
        with patch.dict(sys.modules, {"winreg": registry}), patch.object(sys, "platform", "win32"), \
             patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", str(executable)):
            self.assertEqual(updates.update_context().kind, "windows")
            registry.QueryValueEx.return_value = (str(self.directory / "Different app"), 1)
            self.assertEqual(updates.update_context().kind, "portable")
            registry.QueryValueEx.return_value = (123, 1)
            self.assertEqual(updates.update_context().kind, "portable")

    def test_mid_download_cancellation_never_leaves_an_installable_partial_package(self):
        content = b"x" * (512 * 1024)
        release = updates.parse_release(release_data(content=content), self.context)
        cancel = threading.Event()
        with patch("atlas.updates._open", return_value=io.BytesIO(content)), self.assertRaises(updates.DownloadCancelled):
            updates.download_release(release, self.directory, cancel, lambda a, b: cancel.set())
        self.assertEqual(list(self.directory.rglob("*.part")), [])
        self.assertFalse((self.directory / release.version / release.asset.name).exists())

    def test_source_copies_never_offer_to_overwrite_their_python_interpreter(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(updates.update_context().kind, "source")

    def test_appimage_replacement_keeps_a_backup_and_restarts_with_the_same_atlas(self):
        release = updates.parse_release(release_data(kind="appimage"), updates.UpdateContext("appimage"))
        download, image, atlas = self.directory / release.asset.name, self.directory / "My Atlas.AppImage", self.directory / "notes.json"
        download.write_bytes(self.content)
        image.write_bytes(b"previous application")
        atlas.write_bytes(b"keep these notes")
        with patch("atlas.updates.subprocess.Popen") as start, patch.dict(os.environ, {"APPIMAGE": "old", "LD_LIBRARY_PATH": "old-bundle"}):
            updates.replace_appimage(download, release.asset, image, atlas)
        self.assertEqual(image.read_bytes(), self.content)
        self.assertEqual(image.with_name(image.name + ".previous").read_bytes(), b"previous application")
        self.assertIn(str(atlas.resolve()), start.call_args.args[0])
        self.assertNotIn("APPIMAGE", start.call_args.kwargs["env"])
        self.assertNotIn("LD_LIBRARY_PATH", start.call_args.kwargs["env"])
        self.assertEqual(atlas.read_bytes(), b"keep these notes")

    def test_appimage_restart_failure_restores_the_previous_application(self):
        release = updates.parse_release(release_data(kind="appimage"), updates.UpdateContext("appimage"))
        download, image = self.directory / release.asset.name, self.directory / "My Atlas.AppImage"
        download.write_bytes(self.content)
        image.write_bytes(b"previous application")
        with patch("atlas.updates.subprocess.Popen", side_effect=OSError("Cannot run")), self.assertRaises(updates.UpdateError):
            updates.replace_appimage(download, release.asset, image, self.directory / "notes.json")
        self.assertEqual(image.read_bytes(), b"previous application")
        self.assertEqual(list(self.directory.glob(".cyber-atlas-update-*")), [])


if __name__ == "__main__":
    unittest.main()
