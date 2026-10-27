"""Checks for externally signed Windows artifacts. No keys or network access."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


class SigningError(RuntimeError):
    pass


def digest(path: Path) -> str:
    with path.open("rb") as content:
        return hashlib.file_digest(content, "sha256").hexdigest()


def certificate_fingerprint(value: str) -> str:
    # Use the certificate's SHA-256 fingerprint, not its commonly shown SHA-1 thumbprint.
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise SigningError("Configure WINDOWS_SIGNING_CERT_SHA256 with the approved certificate's 64-digit SHA-256 fingerprint")
    return value.lower()


def find_signtool(explicit: Path | None = None) -> Path:
    if explicit is not None:
        candidates = [explicit]
    else:
        candidates = [shutil.which("signtool.exe")]
        for variable in ("ProgramFiles(x86)", "ProgramFiles"):
            directory = Path(os.environ.get(variable, "C:/nonexistent")) / "Windows Kits/10/bin"
            candidates += sorted(directory.glob("*/x64/signtool.exe"), reverse=True)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise SigningError("Install the Windows SDK Signing Tools or pass --signtool with its x64 signtool.exe")


def verify_signature(path: Path, certificate: str, signtool: Path) -> dict:
    certificate = certificate_fingerprint(certificate)
    if not path.is_file():
        raise SigningError(f"Missing signed file: {path.name}")
    # Inno's cached uninstaller has an .e32/.e64 extension; inspect it as a PE executable.
    with TemporaryDirectory(prefix="cyber-atlas-signature-") as directory:
        target = path
        if path.suffix.lower() not in (".exe", ".ps1"):
            target = Path(directory) / "uninstaller.exe"
            shutil.copyfile(path, target)
        result = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "RemoteSigned", "-File",
             str(ROOT / "tools/verify_windows_signature.ps1"), "-LiteralPath", str(target.resolve()),
             "-CertificateSha256", certificate, "-SignTool", str(signtool)],
            check=False, capture_output=True, encoding="utf-8-sig", errors="replace", timeout=180)
    if result.returncode:
        raise SigningError(f"Signature verification failed for {path.name}: {result.stderr.strip()}")
    try:
        report = json.loads(result.stdout)
        if report.get("valid") is not True or report.get("certificate_sha256") != certificate or not report.get("timestamp_subject"):
            raise ValueError("Incomplete verifier result")
    except (ValueError, TypeError, AttributeError) as exc:
        raise SigningError(f"Invalid signature-verification report for {path.name}") from exc
    return {"file": path.name, "sha256": digest(path), **report}


def _pe_parts(data: bytes) -> tuple[bytes, int, int]:
    """Normalize only the PE checksum and certificate-table fields, not code/data."""
    try:
        if data[:2] != b"MZ":
            raise ValueError("Missing DOS header")
        header = struct.unpack_from("<I", data, 0x3C)[0]
        if data[header:header + 4] != b"PE\0\0":
            raise ValueError("Missing PE header")
        optional = header + 24
        magic = struct.unpack_from("<H", data, optional)[0]
        if magic not in (0x10B, 0x20B):
            raise ValueError("Unsupported optional header")
        directory = optional + (96 if magic == 0x10B else 112) + 4 * 8
        size = struct.unpack_from("<H", data, header + 20)[0]
        if directory + 8 > optional + size or optional + size > len(data):
            raise ValueError("Truncated optional header")
        offset, length = struct.unpack_from("<II", data, directory)
        if bool(offset) != bool(length) or (length and (offset % 8 or offset < optional + size or offset + length != len(data))):
            raise ValueError("Invalid certificate table")
        result = bytearray(data[:offset] if length else data)
        result[optional + 64:optional + 68] = b"\0" * 4
        result[directory:directory + 8] = b"\0" * 8
        return bytes(result), offset, length
    except (struct.error, ValueError) as exc:
        raise SigningError("Invalid PE structure in signing input/output") from exc


def verify_payload(unsigned: Path, signed: Path) -> None:
    """Reject a validly signed artifact from a different build or modified payload.

    This is a byte comparison, not signature verification; Windows verifies trust separately.
    """
    original, result = unsigned.read_bytes(), signed.read_bytes()
    if unsigned.suffix.lower() == ".ps1":
        marker = "# SIG # Begin signature block"
        try:
            original_text = original.decode("utf-8-sig").replace("\r\n", "\n")
            result_text = result.decode("utf-8-sig").replace("\r\n", "\n")
        except UnicodeError as exc:
            raise SigningError("PowerShell signing requires UTF-8 source") from exc
        if marker in original_text or result_text.count(marker) != 1:
            raise SigningError("Unexpected PowerShell signature block")
        payload, signature = result_text.split(marker)
        if payload.rstrip("\n") != original_text.rstrip("\n") or not signature.rstrip().endswith("# SIG # End signature block"):
            raise SigningError("Signing changed the PowerShell script contents")
    else:
        before, _, original_signature = _pe_parts(original)
        after, _, signature = _pe_parts(result)
        padding = (-len(before)) % 8
        if original_signature or not signature or after != before + b"\0" * padding:
            raise SigningError("Signing changed the executable payload or returned an unsigned file")


def tree_hashes(directory: Path) -> dict[str, str]:
    files = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise SigningError("Windows release bundles must not contain symlinks")
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = digest(path)
    return files


def verify_tree(directory: Path, expected: dict[str, str]) -> None:
    if tree_hashes(directory) != expected:
        raise SigningError("The application bundle changed between signing stages; start a fresh build")


def exact_files(directory: Path, names: set[str]) -> None:
    if (not directory.is_dir() or directory.is_symlink()
            or any(path.is_symlink() for path in directory.rglob("*"))
            or {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()} != names):
        raise SigningError("The signed artifact has missing, unexpected or unsafe files")
