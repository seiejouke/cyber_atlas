"""Create and verify signed Linux release manifests and AppImage signatures."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory


class LinuxSigningError(RuntimeError):
    pass


def signing_fingerprint(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", value):
        raise LinuxSigningError("Provide the release signing key's full 40- or 64-digit fingerprint")
    return value.upper()


def digest(path: Path) -> str:
    with path.open("rb") as content:
        return hashlib.file_digest(content, "sha256").hexdigest()


def checksum_entries(artifacts: list[Path]) -> dict[str, str]:
    entries = {}
    for path in artifacts:
        if path.is_symlink() or not path.is_file():
            raise LinuxSigningError(f"Missing or unsafe release artifact: {path.name}")
        if not re.fullmatch(r"[A-Za-z0-9._+-]+", path.name) or path.name in entries:
            raise LinuxSigningError(f"Invalid or duplicate release artifact name: {path.name}")
        entries[path.name] = digest(path)
    if not entries:
        raise LinuxSigningError("No release artifacts were supplied")
    return entries


def write_manifest(artifacts: list[Path], destination: Path) -> dict[str, str]:
    if destination.is_symlink():
        raise LinuxSigningError(f"Refusing to overwrite an unsafe manifest path: {destination}")
    entries = checksum_entries(artifacts)
    destination.write_text(
        "".join(f"{checksum}  {name}\n" for name, checksum in sorted(entries.items())),
        encoding="ascii",
        newline="\n",
    )
    return entries


def sign_manifest(manifest: Path, signature: Path, fingerprint: str, *, gpg: str = "gpg") -> None:
    fingerprint = signing_fingerprint(fingerprint)
    if not manifest.is_file() or manifest.is_symlink():
        raise LinuxSigningError(f"Missing or unsafe checksum manifest: {manifest}")
    if signature.is_symlink():
        raise LinuxSigningError(f"Refusing to overwrite an unsafe signature path: {signature}")
    subprocess.run(
        [gpg, "--batch", "--yes", "--local-user", fingerprint, "--armor", "--detach-sign",
         "--output", str(signature), str(manifest)],
        check=True,
    )


def _import_trusted_key(public_key: Path, fingerprint: str, gpg: str, home: Path) -> None:
    if public_key.is_symlink() or not public_key.is_file():
        raise LinuxSigningError(f"Missing or unsafe public signing key: {public_key}")
    home.mkdir(mode=0o700)
    subprocess.run([gpg, "--no-options", "--homedir", str(home), "--batch", "--import", str(public_key)],
                   check=True, capture_output=True, text=True)
    listing = subprocess.run(
        [gpg, "--no-options", "--homedir", str(home), "--batch", "--with-colons", "--fingerprint", "--list-keys"],
        check=True, capture_output=True, text=True,
    )
    primary_fingerprints = []
    primary_key = False
    for line in listing.stdout.splitlines():
        fields = line.split(":")
        if fields[0] == "pub":
            primary_key = True
        elif fields[0] == "sub":
            primary_key = False
        elif fields[0] == "fpr" and primary_key:
            primary_fingerprints.append(fields[9].upper())
            primary_key = False
    if primary_fingerprints != [fingerprint]:
        raise LinuxSigningError("The supplied public key must contain only the configured release signing identity")


def _verify_manifest_signature(manifest: Path, signature: Path, fingerprint: str, gpg: str, home: Path) -> None:
    if any(path.is_symlink() or not path.is_file() for path in (manifest, signature)):
        raise LinuxSigningError("The checksum manifest or detached signature is missing or unsafe")
    result = subprocess.run(
        [gpg, "--no-options", "--homedir", str(home), "--batch", "--status-fd", "1",
         "--verify", str(signature), str(manifest)],
        check=False, capture_output=True, text=True,
    )
    valid_signers = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields[:2] == ["[GNUPG:]", "VALIDSIG"] and len(fields) > 2:
            primary = fields[11].upper() if len(fields) > 11 else fields[2].upper()
            valid_signers.append((fields[2].upper(), primary))
    bad_signature = any(line.startswith(("[GNUPG:] BADSIG ", "[GNUPG:] ERRSIG "))
                        for line in result.stdout.splitlines())
    if result.returncode or bad_signature or len(valid_signers) != 1 or fingerprint not in valid_signers[0]:
        raise LinuxSigningError("Checksum signature is invalid or was not made by the configured release key")


def _read_manifest(manifest: Path, artifacts: list[Path]) -> None:
    if manifest.is_symlink() or not manifest.is_file():
        raise LinuxSigningError("The checksum manifest is missing or unsafe")
    expected = checksum_entries(artifacts)
    pattern = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9._+-]+)")
    actual = {}
    for line in manifest.read_text(encoding="ascii").splitlines():
        match = pattern.fullmatch(line)
        if not match or match.group(2) in actual:
            raise LinuxSigningError("Checksum manifest has an invalid or duplicate entry")
        actual[match.group(2)] = match.group(1)
    if actual != expected:
        raise LinuxSigningError("Checksum manifest does not exactly match the supplied release artifacts")


def verify_signed_release(
    manifest: Path,
    signature: Path,
    artifacts: list[Path],
    appimage: Path,
    public_key: Path,
    fingerprint: str,
    *,
    validator: str = "validate",
    gpg: str = "gpg",
) -> None:
    fingerprint = signing_fingerprint(fingerprint)
    if appimage not in artifacts or appimage.suffix.lower() != ".appimage":
        raise LinuxSigningError("The signed AppImage must be included in the release artifact list")
    _read_manifest(manifest, artifacts)
    validator_path = shutil.which(validator)
    if validator_path is None:
        raise LinuxSigningError(f"Install the AppImage signature verifier '{validator}' before verifying a signed release")
    with TemporaryDirectory(prefix="cyber-atlas-linux-verify-") as directory:
        home = Path(directory) / "gnupg"
        _import_trusted_key(public_key, fingerprint, gpg, home)
        _verify_manifest_signature(manifest, signature, fingerprint, gpg, home)
        environment = os.environ.copy()
        environment["GNUPGHOME"] = str(home)
        result = subprocess.run([validator_path, str(appimage)], check=False, capture_output=True,
                                text=True, env=environment)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise LinuxSigningError(f"Embedded AppImage signature verification failed: {detail}")


def export_public_key(fingerprint: str, destination: Path, *, gpg: str = "gpg") -> None:
    fingerprint = signing_fingerprint(fingerprint)
    if destination.is_symlink():
        raise LinuxSigningError(f"Refusing to overwrite an unsafe public-key path: {destination}")
    result = subprocess.run([gpg, "--batch", "--armor", "--export", fingerprint],
                            check=True, capture_output=True)
    if not result.stdout:
        raise LinuxSigningError("The configured GPG key has no exportable public key")
    destination.write_bytes(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="Verify a signed manifest, all listed checksums and the AppImage signature")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--signature", type=Path, required=True)
    verify.add_argument("--appimage", type=Path, required=True)
    verify.add_argument("--public-key", type=Path, required=True)
    verify.add_argument("--fingerprint", required=True)
    verify.add_argument("--artifact", type=Path, action="append", required=True,
                        help="Release artifact covered by the manifest; repeat for each file")
    verify.add_argument("--validator", default="validate", help="AppImageUpdate validate executable")
    verify.add_argument("--gpg", default="gpg", help="GnuPG executable")
    arguments = parser.parse_args()
    try:
        verify_signed_release(
            arguments.manifest, arguments.signature, arguments.artifact, arguments.appimage,
            arguments.public_key, arguments.fingerprint, validator=arguments.validator, gpg=arguments.gpg,
        )
    except LinuxSigningError as exc:
        parser.error(str(exc))
    print("Release checksums and AppImage signature are valid.")


if __name__ == "__main__":
    main()
