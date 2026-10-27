import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from atlas import __version__
from tools import sign_windows as stages
from tools import windows_signing as signing

CERTIFICATE = "ab" * 32


def pe(payload=b"original application", *, signed=False, bits=64):
    """Synthetic PE-shaped data for byte-comparison tests; never executed or trusted."""
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x80 + 20, 240 if bits == 64 else 224)
    optional = 0x80 + 24
    struct.pack_into("<H", data, optional, 0x20B if bits == 64 else 0x10B)
    data.extend(payload)
    if signed:
        data.extend(b"\0" * ((-len(data)) % 8))
        directory = optional + (112 if bits == 64 else 96) + 32
        struct.pack_into("<II", data, directory, len(data), 32)
        struct.pack_into("<I", data, optional + 64, 12345)
        data.extend(b"SYNTHETIC CERTIFICATE".ljust(32, b"\0"))
    return bytes(data)


def signed_script(text=b"Write-Output 'original'\n"):
    return text + b"\n# SIG # Begin signature block\n# SYNTHETIC\n# SIG # End signature block\n"


class SigningChecks(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def pair(self, before, after, suffix=".exe"):
        original, result = self.root / ("input" + suffix), self.root / ("signed" + suffix)
        original.write_bytes(before)
        result.write_bytes(after)
        return original, result

    def test_pe_payload_comparison_accepts_only_signing_header_changes_and_alignment(self):
        for bits in (32, 64):
            with self.subTest(bits=bits):
                signing.verify_payload(*self.pair(pe(bits=bits), pe(signed=True, bits=bits)))

    def test_replaced_code_or_appended_payload_is_rejected(self):
        for replacement in (b"different application", b"original application plus extra code"):
            with self.subTest(replacement=replacement), self.assertRaises(signing.SigningError):
                signing.verify_payload(*self.pair(pe(), pe(replacement, signed=True)))

    def test_an_unsigned_result_or_previously_signed_input_is_rejected(self):
        for before, after in ((pe(), pe()), (pe(signed=True), pe(signed=True))):
            with self.subTest(), self.assertRaises(signing.SigningError):
                signing.verify_payload(*self.pair(before, after))

    def test_invalid_pe_headers_or_certificate_ranges_are_rejected(self):
        malformed = bytearray(pe(signed=True))
        struct.pack_into("<I", malformed, 0x80 + 24 + 112 + 32, 8)
        for data in (b"not an executable", b"MZ", pe(signed=True) + b"extra", bytes(malformed)):
            with self.subTest(length=len(data)), self.assertRaises(signing.SigningError):
                signing.verify_payload(*self.pair(pe(), data))

    def test_non_signing_header_changes_are_rejected(self):
        altered = bytearray(pe(signed=True))
        altered[0x80 + 24 + 72] = 23
        with self.assertRaises(signing.SigningError):
            signing.verify_payload(*self.pair(pe(), bytes(altered)))

    def test_powershell_allows_signature_append_and_equivalent_utf8_line_endings(self):
        original = b"Write-Output 'original'\n"
        result = b"\xef\xbb\xbf" + signed_script(original).replace(b"\n", b"\r\n")
        signing.verify_payload(*self.pair(original, result, ".ps1"))

    def test_powershell_code_changes_and_missing_signature_blocks_fail(self):
        original = b"Write-Output 'original'\n"
        for result in (signed_script(b"Write-Output 'changed'\n"), original,
                       signed_script(original) + b"Invoke-Expression 'extra'\n", signed_script(signed_script(original))):
            with self.subTest(), self.assertRaises(signing.SigningError):
                signing.verify_payload(*self.pair(original, result, ".ps1"))

    def test_certificate_requires_sha256_not_sha1_or_placeholder(self):
        self.assertEqual(signing.certificate_fingerprint(CERTIFICATE.upper()), CERTIFICATE)
        for value in ("a" * 40, "APPROVED_CERTIFICATE", "g" * 64, " " + CERTIFICATE, None):
            with self.subTest(value=value), self.assertRaises(signing.SigningError):
                signing.certificate_fingerprint(value)

    def test_verifier_treats_paths_as_arguments_not_powershell_code(self):
        path = self.root / "file with spaces $().exe"
        path.write_bytes(pe(signed=True))
        report = {"valid": True, "certificate_sha256": CERTIFICATE, "timestamp_subject": "Timestamp CA"}
        with patch.object(signing.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr="")) as run:
            result = signing.verify_signature(path, CERTIFICATE, self.root / "signtool.exe")
        arguments = run.call_args.args[0]
        self.assertIn("-File", arguments)
        self.assertIn(str(path.resolve()), arguments)
        self.assertNotIn("-Command", arguments)
        self.assertEqual(arguments[arguments.index("-ExecutionPolicy") + 1], "RemoteSigned")
        self.assertNotIn("Bypass", arguments)
        self.assertEqual(result["sha256"], signing.digest(path))

    def test_failed_or_incomplete_signature_verification_stops_processing(self):
        path = self.root / "app.exe"
        path.write_bytes(pe())
        responses = [SimpleNamespace(returncode=1, stdout="", stderr="Invalid signature"),
                     SimpleNamespace(returncode=0, stdout="{}", stderr=""),
                     SimpleNamespace(returncode=0, stdout="not JSON", stderr=""),
                     SimpleNamespace(returncode=0, stdout=json.dumps({"valid": True, "certificate_sha256": CERTIFICATE}), stderr="")]
        for response in responses:
            with self.subTest(response=response), patch.object(signing.subprocess, "run", return_value=response):
                with self.assertRaises(signing.SigningError):
                    signing.verify_signature(path, CERTIFICATE, self.root / "signtool.exe")

    def test_bundle_change_or_added_file_is_detected(self):
        directory = self.root / "bundle"
        directory.mkdir()
        (directory / "third-party.dll").write_bytes(b"upstream library")
        expected = signing.tree_hashes(directory)
        signing.verify_tree(directory, expected)
        (directory / "third-party.dll").write_bytes(b"modified library")
        with self.assertRaises(signing.SigningError):
            signing.verify_tree(directory, expected)
        (directory / "third-party.dll").write_bytes(b"upstream library")
        (directory / "unexpected.dll").write_bytes(b"extra")
        with self.assertRaises(signing.SigningError):
            signing.verify_tree(directory, expected)

    def test_signed_artifact_cannot_have_missing_extra_or_nested_files(self):
        directory = self.root / "signed"
        directory.mkdir()
        for name in ("app.exe", "other.exe"):
            (directory / name).write_bytes(b"data")
        with self.assertRaises(signing.SigningError):
            signing.exact_files(directory, {"app.exe"})
        with self.assertRaises(signing.SigningError):
            signing.exact_files(directory, {"app.exe", "other.exe", "missing.exe"})
        signing.exact_files(directory, {"app.exe", "other.exe"})


class SigningStages(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.work = self.root / "work"
        printer = patch("builtins.print")
        printer.start()
        self.addCleanup(printer.stop)
        self.destination = self.root / "dist"
        self.bundle = self.destination / "CyberAtlas"
        self.bundle.mkdir(parents=True)
        self.compiler = self.root / "ISCC.exe"
        self.compiler.write_bytes(b"compiler fixture")
        self.signtool = self.root / "signtool.exe"
        self.cache_name = "uninst-6.5-fixture.e32"
        for name in ("inputs", "uninstaller-cache", "installer-input"):
            (self.work / name).mkdir(parents=True, exist_ok=True)
        for name, data in (("CyberAtlas.exe", pe()), ("uninstaller.exe", pe(b"uninstaller")),
                           ("update_helper.ps1", b"Write-Output 'original'\n")):
            (self.work / "inputs" / name).write_bytes(data)
        for name, relative in stages.BUNDLE_PATHS.items():
            target = self.bundle / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((self.work / "inputs" / name).read_bytes())
        (self.bundle / "third-party.dll").write_bytes(b"upstream remains unsigned")
        (self.work / "uninstaller-cache" / self.cache_name).write_bytes(pe(b"uninstaller"))
        self.signed = self.root / "signed-inputs"
        self.signed.mkdir()
        (self.signed / "CyberAtlas.exe").write_bytes(pe(signed=True))
        (self.signed / "uninstaller.exe").write_bytes(pe(b"uninstaller", signed=True))
        (self.signed / "update_helper.ps1").write_bytes(signed_script())
        self.state = {"schema": 1, "version": __version__, "stage": "inputs-prepared", "certificate_sha256": CERTIFICATE,
                      "uninstaller_cache_name": self.cache_name, "compiler_sha256": signing.digest(self.compiler),
                      "recipe_sha256": signing.digest(stages.ROOT / "packaging/windows.iss"),
                      "input_hashes": signing.tree_hashes(self.work / "inputs"), "bundle_hashes": signing.tree_hashes(self.bundle),
                      "desktop_checks_deferred": True}
        stages.write_state(self.work, self.state)

    def signature(self, path, certificate, signtool):
        self.assertEqual(certificate, CERTIFICATE)
        return {"file": path.name, "valid": True, "certificate_sha256": certificate,
                "timestamp_subject": "Synthetic test result", "sha256": signing.digest(path)}

    def assemble(self):
        def compile_fixture(*args, **kwargs):
            (self.work / "installer-input" / f"CyberAtlas-{__version__}-Setup.exe").write_bytes(pe(b"installer"))
        with patch.object(stages, "verify_signature", side_effect=self.signature), patch.object(stages.subprocess, "run", side_effect=compile_fixture):
            stages.assemble(self.work, self.bundle, self.compiler, CERTIFICATE, self.signtool, self.signed)

    def installer_output(self, *, signed=True):
        directory = self.root / "signed-installer"
        directory.mkdir(exist_ok=True)
        (directory / f"CyberAtlas-{__version__}-Setup.exe").write_bytes(pe(b"installer", signed=signed))
        return directory

    def test_signing_state_rejects_version_certificate_stage_or_cache_path_changes(self):
        for key, value in (("version", "99.0.0"), ("certificate_sha256", "cd" * 32),
                           ("stage", "complete"), ("uninstaller_cache_name", "../uninst-malicious.e32"),
                           ("compiler_sha256", "invalid"), ("input_hashes", {}), ("bundle_hashes", {})):
            with self.subTest(key=key):
                stages.write_state(self.work, {**self.state, key: value})
                with self.assertRaises(signing.SigningError):
                    stages.read_state(self.work, "inputs-prepared", CERTIFICATE)

    def test_preparation_captures_only_the_expected_compiler_handoff(self):
        work = self.root / "fresh-staging"
        (self.bundle / "Read me.txt").write_text("This build is unsigned.\n", encoding="utf-8")
        def run_fixture(command, **kwargs):
            if command[0] != str(self.compiler):
                self.assertIn("--bundle-only", command)
                return SimpleNamespace(returncode=0)
            (work / "uninstaller-cache" / self.cache_name).write_bytes(pe(b"uninstaller"))
            return SimpleNamespace(returncode=2, stdout="Please attach your digital signature to the executable.", stderr="")
        with patch.object(stages.subprocess, "run", side_effect=run_fixture):
            stages.prepare(work, self.bundle, self.compiler, CERTIFICATE, True)
        state = stages.read_state(work, "inputs-prepared", CERTIFICATE)
        self.assertEqual(set(state["input_hashes"]), stages.INPUTS)
        self.assertFalse(any(self.destination.glob("*.zip")))
        self.assertFalse(any(self.destination.glob("*-Setup.exe")))

    def test_unexpected_compiler_failure_does_not_become_a_signing_request(self):
        work = self.root / "failed-staging"
        (self.bundle / "Read me.txt").write_text("This build is unsigned.\n", encoding="utf-8")
        def run_fixture(command, **kwargs):
            return SimpleNamespace(returncode=2, stdout="Unknown directive or source file missing", stderr="")
        with patch.object(stages.subprocess, "run", side_effect=run_fixture), self.assertRaises(signing.SigningError):
            stages.prepare(work, self.bundle, self.compiler, CERTIFICATE, True)
        self.assertFalse((work / "state.json").exists())

    def test_existing_staging_cannot_be_reused_for_a_new_request(self):
        with patch.object(stages.subprocess, "run") as run, self.assertRaises(signing.SigningError):
            stages.prepare(self.work, self.bundle, self.compiler, CERTIFICATE, True)
        run.assert_not_called()

    def test_modified_unsigned_inputs_are_detected(self):
        (self.work / "inputs/CyberAtlas.exe").write_bytes(pe(b"different"))
        with self.assertRaises(signing.SigningError):
            stages.read_state(self.work, "inputs-prepared", CERTIFICATE)

    def test_changed_compiler_or_third_party_library_cannot_be_assembled(self):
        self.compiler.write_bytes(b"changed compiler")
        with self.assertRaises(signing.SigningError), patch.object(stages.subprocess, "run") as run:
            stages.assemble(self.work, self.bundle, self.compiler, CERTIFICATE, self.signtool, self.signed)
        run.assert_not_called()
        self.compiler.write_bytes(b"compiler fixture")
        (self.bundle / "third-party.dll").write_bytes(b"modified library")
        with self.assertRaises(signing.SigningError):
            stages.assemble(self.work, self.bundle, self.compiler, CERTIFICATE, self.signtool, self.signed)

    def test_failed_signature_does_not_replace_any_original_file(self):
        original = signing.tree_hashes(self.bundle)
        with patch.object(stages, "verify_signature", side_effect=signing.SigningError("bad certificate")):
            with self.assertRaises(signing.SigningError):
                stages.assemble(self.work, self.bundle, self.compiler, CERTIFICATE, self.signtool, self.signed)
        self.assertEqual(signing.tree_hashes(self.bundle), original)

    def test_assembly_restores_signed_cache_and_leaves_third_party_binaries_untouched(self):
        self.assemble()
        state = stages.read_state(self.work, "installer-prepared", CERTIFICATE)
        self.assertEqual((self.work / "uninstaller-cache" / self.cache_name).read_bytes(), (self.signed / "uninstaller.exe").read_bytes())
        self.assertEqual((self.bundle / "third-party.dll").read_bytes(), b"upstream remains unsigned")
        self.assertEqual(len(state["signed_input_reports"]), 3)

    def test_unsigned_installer_never_produces_final_outputs(self):
        self.assemble()
        with self.assertRaises(signing.SigningError):
            stages.finalize(self.work, self.bundle, self.destination, CERTIFICATE, self.signtool,
                            self.installer_output(signed=False), True)
        self.assertFalse((self.destination / "SHA256SUMS.txt").exists())
        self.assertFalse(any(self.destination.glob("*.zip")))

    def test_finalize_verifies_all_files_before_archiving_and_marks_desktop_checks_pending(self):
        self.assemble()
        with patch.object(stages, "verify_signature", side_effect=self.signature) as verify:
            stages.finalize(self.work, self.bundle, self.destination, CERTIFICATE, self.signtool, self.installer_output(), True)
        self.assertEqual(verify.call_count, 4)
        report = json.loads((self.destination / "windows-signing-report.json").read_text(encoding="utf-8"))
        self.assertTrue(report["signatures_verified"])
        self.assertEqual(report["desktop_validation"], "pending")
        self.assertFalse(report["published"])
        for line in (self.destination / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
            expected, name = line.split("  ")
            self.assertEqual(signing.digest(self.destination / name), expected)
        with zipfile.ZipFile(self.destination / f"CyberAtlas-{__version__}-windows-x64.zip") as archive:
            self.assertEqual(archive.read("CyberAtlas/CyberAtlas.exe"), pe(signed=True))
        self.assertEqual(json.loads((self.work / "state.json").read_text(encoding="utf-8"))["stage"], "complete")

    def test_finalization_rejects_changed_bundle_and_existing_artifacts(self):
        self.assemble()
        signed = self.installer_output()
        (self.bundle / "unexpected.dll").write_bytes(b"extra")
        with self.assertRaises(signing.SigningError):
            stages.finalize(self.work, self.bundle, self.destination, CERTIFICATE, self.signtool, signed, True)
        (self.bundle / "unexpected.dll").unlink()
        existing = self.destination / f"CyberAtlas-{__version__}-Setup.exe"
        existing.write_bytes(b"preserve existing release")
        with patch.object(stages, "verify_signature", side_effect=self.signature), self.assertRaises(signing.SigningError):
            stages.finalize(self.work, self.bundle, self.destination, CERTIFICATE, self.signtool, signed, True)
        self.assertEqual(existing.read_bytes(), b"preserve existing release")

    def test_desktop_validation_cannot_claim_success_when_installer_check_is_skipped(self):
        self.assemble()
        with patch.object(stages, "verify_signature", side_effect=self.signature):
            stages.finalize(self.work, self.bundle, self.destination, CERTIFICATE, self.signtool, self.installer_output(), True)
        def skipped(*args, **kwargs):
            (self.destination / "installer-test-results.json").write_text(json.dumps({"passed": None, "skipped": "Existing installation"}), encoding="utf-8")
        with patch.object(stages, "verify_signature", side_effect=self.signature), patch.object(stages.build_windows, "check_installer", side_effect=skipped):
            with self.assertRaisesRegex(signing.SigningError, "disposable Windows account"):
                stages.verify_candidate(self.destination, self.work / "validation", CERTIFICATE, self.signtool)
        report = json.loads((self.destination / "windows-signing-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["desktop_validation"], "pending")


class SigningPolicyTests(unittest.TestCase):
    def test_artifact_configurations_sign_only_first_party_files_with_sha256(self):
        namespace = {"s": "http://signpath.io/artifact-configuration/v1"}
        expected = {"windows-inputs-v1.xml": {"CyberAtlas.exe", "uninstaller.exe", "update_helper.ps1"},
                    "windows-installer-v1.xml": {"CyberAtlas-*-Setup.exe"}}
        for filename, paths in expected.items():
            root = ET.parse(signing.ROOT / "packaging/signpath" / filename).getroot()
            files = list(root.find("s:zip-file", namespace))
            self.assertEqual({file.attrib["path"] for file in files}, paths)
            for file in files:
                self.assertEqual(file.find("s:authenticode-sign", namespace).attrib["hash-algorithm"], "sha256")
                if file.tag.endswith("pe-file"):
                    self.assertEqual(file.attrib["product-name"], "Cyber Atlas")
                    self.assertEqual(file.attrib["product-version"], "${version}")

    def test_workflow_is_manual_and_cannot_publish_or_sign_from_other_branches(self):
        workflow = (signing.ROOT / ".github/workflows/windows-signing.yml").read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:", workflow)
        for trigger in ("  push:", "  pull_request:", "  workflow_run:", "  schedule:"):
            self.assertNotIn(trigger, workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("github.repository == 'seiejouke/cyber_atlas'", workflow)
        self.assertIn("environment: windows-signing", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertEqual(workflow.count("signing-policy-slug: release-signing"), 2)
        self.assertIn("WINDOWS_SIGNING_CERT_SHA256", workflow)


if __name__ == "__main__":
    unittest.main()
