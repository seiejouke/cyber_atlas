import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import linux_signing


FINGERPRINT = "A1" * 20


class LinuxSigningTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def artifact(self, name, data=b"release artifact"):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_fingerprint_requires_a_full_hexadecimal_key_fingerprint(self):
        self.assertEqual(linux_signing.signing_fingerprint(FINGERPRINT.lower()), FINGERPRINT)
        for value in ("A1" * 8, "Z1" * 20, " " + FINGERPRINT, None):
            with self.subTest(value=value), self.assertRaises(linux_signing.LinuxSigningError):
                linux_signing.signing_fingerprint(value)

    def test_manifest_is_sorted_and_covers_each_exact_artifact(self):
        appimage = self.artifact("CyberAtlas.AppImage", b"image")
        package = self.artifact("cyber-atlas.deb", b"package")
        manifest = self.root / "SHA256SUMS-linux.txt"
        entries = linux_signing.write_manifest([appimage, package], manifest)
        self.assertEqual(list(entries), ["CyberAtlas.AppImage", "cyber-atlas.deb"])
        self.assertEqual(manifest.read_text(encoding="ascii"),
                         f"{hashlib.sha256(b'image').hexdigest()}  CyberAtlas.AppImage\n"
                         f"{hashlib.sha256(b'package').hexdigest()}  cyber-atlas.deb\n")

    def test_manifest_rejects_duplicate_names_unsafe_paths_and_empty_input(self):
        artifact = self.artifact("CyberAtlas.AppImage")
        with self.assertRaises(linux_signing.LinuxSigningError):
            linux_signing.checksum_entries([artifact, artifact])
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(linux_signing.LinuxSigningError):
                linux_signing.checksum_entries([artifact])
        with self.assertRaises(linux_signing.LinuxSigningError):
            linux_signing.checksum_entries([])

    def test_manifest_verification_rejects_changed_or_unlisted_artifacts(self):
        appimage = self.artifact("CyberAtlas.AppImage", b"image")
        package = self.artifact("cyber-atlas.deb", b"package")
        manifest = self.root / "SHA256SUMS-linux.txt"
        linux_signing.write_manifest([appimage, package], manifest)
        linux_signing._read_manifest(manifest, [appimage, package])
        package.write_bytes(b"changed")
        with self.assertRaisesRegex(linux_signing.LinuxSigningError, "exactly match"):
            linux_signing._read_manifest(manifest, [appimage, package])
        package.write_bytes(b"package")
        manifest.write_text(manifest.read_text(encoding="ascii") + "0" * 64 + "  extra.deb\n", encoding="ascii")
        with self.assertRaisesRegex(linux_signing.LinuxSigningError, "exactly match"):
            linux_signing._read_manifest(manifest, [appimage, package])

    def test_verifier_uses_isolated_keyring_and_checks_both_signatures(self):
        appimage = self.artifact("CyberAtlas.AppImage")
        package = self.artifact("cyber-atlas.deb")
        manifest = self.root / "SHA256SUMS-linux.txt"
        signature = self.root / "SHA256SUMS-linux.txt.asc"
        public_key = self.root / "release-key.asc"
        public_key.write_text("public key", encoding="ascii")
        signature.write_text("detached signature", encoding="ascii")
        linux_signing.write_manifest([appimage, package], manifest)
        calls = []

        def run(arguments, **kwargs):
            calls.append((arguments, kwargs))
            if "--list-keys" in arguments:
                return SimpleNamespace(returncode=0, stdout=f"pub:::::::::\nfpr:::::::::{FINGERPRINT}:\n", stderr="")
            if "--verify" in arguments:
                return SimpleNamespace(returncode=0, stdout=f"[GNUPG:] VALIDSIG {FINGERPRINT} date time\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch.object(linux_signing.shutil, "which", return_value="C:/tools/validate"), \
             patch.object(linux_signing.subprocess, "run", side_effect=run):
            linux_signing.verify_signed_release(manifest, signature, [package, appimage], appimage,
                                                public_key, FINGERPRINT)

        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[-1][0], ["C:/tools/validate", str(appimage)])
        self.assertTrue(calls[-1][1]["env"]["GNUPGHOME"].endswith("gnupg"))
        self.assertNotEqual(calls[-1][1]["env"]["GNUPGHOME"], str(self.root))

    def test_wrong_signer_invalid_manifest_or_unverifiable_appimage_fails(self):
        appimage = self.artifact("CyberAtlas.AppImage")
        package = self.artifact("cyber-atlas.deb")
        manifest = self.root / "SHA256SUMS-linux.txt"
        signature = self.root / "SHA256SUMS-linux.txt.asc"
        public_key = self.artifact("release-key.asc")
        signature.write_text("signature", encoding="ascii")
        linux_signing.write_manifest([appimage, package], manifest)

        def run(arguments, **kwargs):
            if "--list-keys" in arguments:
                return SimpleNamespace(returncode=0, stdout=f"pub:::::::::\nfpr:::::::::{FINGERPRINT}:\n", stderr="")
            if "--verify" in arguments:
                return SimpleNamespace(returncode=0, stdout=f"[GNUPG:] VALIDSIG {'B2' * 20} date time\n", stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr="bad signature")

        with patch.object(linux_signing.shutil, "which", return_value="C:/tools/validate"), \
             patch.object(linux_signing.subprocess, "run", side_effect=run):
            with self.assertRaisesRegex(linux_signing.LinuxSigningError, "not made by"):
                linux_signing.verify_signed_release(manifest, signature, [package, appimage], appimage,
                                                    public_key, FINGERPRINT)
            signature_result = SimpleNamespace(returncode=0, stdout=f"[GNUPG:] VALIDSIG {FINGERPRINT} date time\n", stderr="")
            with patch.object(linux_signing.subprocess, "run", side_effect=[
                SimpleNamespace(returncode=0, stdout="", stderr=""),
                SimpleNamespace(returncode=0, stdout=f"pub:::::::::\nfpr:::::::::{FINGERPRINT}:\n", stderr=""),
                signature_result,
                SimpleNamespace(returncode=1, stdout="", stderr="invalid embedded signature"),
            ]):
                with self.assertRaisesRegex(linux_signing.LinuxSigningError, "Embedded AppImage"):
                    linux_signing.verify_signed_release(manifest, signature, [package, appimage], appimage,
                                                        public_key, FINGERPRINT)

    def test_signing_command_pins_full_fingerprint(self):
        manifest = self.artifact("SHA256SUMS-linux.txt")
        signature = self.root / "SHA256SUMS-linux.txt.asc"
        with patch.object(linux_signing.subprocess, "run") as run:
            linux_signing.sign_manifest(manifest, signature, FINGERPRINT.lower())
        self.assertEqual(run.call_args.args[0],
                         ["gpg", "--batch", "--yes", "--local-user", FINGERPRINT, "--armor", "--detach-sign",
                          "--output", str(signature), str(manifest)])


if __name__ == "__main__":
    unittest.main()
