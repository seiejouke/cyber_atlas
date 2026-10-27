"""Prepare and verify Windows signing candidates through SignPath.

Manual packaging tool: never submits requests, handles keys or publishes.
GitHub Actions submits the prepared inputs to the signing service.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas import __version__
from tools import build_windows
from tools.windows_signing import (SigningError, certificate_fingerprint, digest, exact_files,
                                   find_signtool, tree_hashes, verify_payload, verify_signature, verify_tree)

INPUTS = {"CyberAtlas.exe", "uninstaller.exe", "update_helper.ps1"}
BUNDLE_PATHS = {"CyberAtlas.exe": "CyberAtlas.exe", "update_helper.ps1": "_internal/atlas/update_helper.ps1"}


def write_state(work: Path, state: dict) -> None:
    temporary = work / "state.json.tmp"
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(work / "state.json")


def read_state(work: Path, stage: str, certificate: str) -> dict:
    try:
        state = json.loads((work / "state.json").read_text(encoding="utf-8"))
        if (state["schema"] != 1 or state["version"] != __version__ or state["stage"] != stage
                or state["certificate_sha256"] != certificate):
            raise ValueError("Stage, version or certificate changed")
        name = state["uninstaller_cache_name"]
        if (not isinstance(name, str) or not name.startswith("uninst-") or "/" in name or "\\" in name
                or ":" in name or Path(name).suffix.lower() not in (".e32", ".e64")):
            raise ValueError("Invalid uninstaller cache name")
        required_hashes = [state["compiler_sha256"], state["recipe_sha256"]]
        if stage == "installer-prepared":
            required_hashes += [state["signed_uninstaller_sha256"], state["installer_sha256"]]
        if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in required_hashes):
            raise ValueError("Invalid recorded digest")
        if (not isinstance(state["input_hashes"], dict) or set(state["input_hashes"]) != INPUTS
                or not isinstance(state["bundle_hashes"], dict) or not state["bundle_hashes"]):
            raise ValueError("Invalid input inventory")
        verify_tree(work / "inputs", state["input_hashes"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SigningError("Missing, stale or invalid signing state; use the matching build and stage") from exc
    return state


def compiler_command(compiler: Path, work: Path) -> list[str]:
    return [str(compiler), "/Q", f"/DAppVersion={__version__}",
            f"/DUninstallerCacheDir={work / 'uninstaller-cache'}",
            f"/O{work / 'installer-input'}", str(ROOT / "packaging/windows.iss")]


def prepare(work: Path, bundle: Path, compiler: Path, certificate: str, defer_desktop: bool) -> None:
    if work.exists():
        raise SigningError("Signing staging already exists; use a fresh checkout/build directory rather than reusing a request")
    work.mkdir(parents=True)
    for directory in ("inputs", "uninstaller-cache", "installer-input"):
        (work / directory).mkdir()
    command = [sys.executable, str(ROOT / "tools/build_windows.py"), "--bundle-only"]
    if defer_desktop:
        command.append("--defer-desktop-checks")
    subprocess.run(command, cwd=ROOT, check=True)
    readme = bundle / "Read me.txt"
    readme.write_text(readme.read_text(encoding="utf-8").replace(
        "This build is unsigned.", "Signed candidate: verify Windows file Properties and complete desktop checks before publication."),
        encoding="utf-8")
    result = subprocess.run(compiler_command(compiler, work), cwd=ROOT, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, errors="replace", timeout=180)
    log = result.stdout + result.stderr
    (work / "uninstaller-preparation.log").write_text(log, encoding="utf-8")
    cache = list((work / "uninstaller-cache").iterdir())
    # Inno deliberately stops at the first external-signing handoff.
    if (result.returncode != 2 or "attach your digital signature" not in log.lower() or len(cache) != 1
            or not cache[0].is_file() or cache[0].is_symlink() or cache[0].read_bytes()[:2] != b"MZ"
            or any((work / "installer-input").iterdir())):
        raise SigningError("Inno did not stop at the expected uninstaller-signing handoff; inspect uninstaller-preparation.log")
    for name, relative in BUNDLE_PATHS.items():
        shutil.copyfile(bundle / relative, work / "inputs" / name)
    shutil.copyfile(cache[0], work / "inputs/uninstaller.exe")
    state = {"schema": 1, "version": __version__, "stage": "inputs-prepared",
             "certificate_sha256": certificate, "uninstaller_cache_name": cache[0].name,
             "compiler_sha256": digest(compiler), "input_hashes": tree_hashes(work / "inputs"),
             "recipe_sha256": digest(ROOT / "packaging/windows.iss"),
             "bundle_hashes": tree_hashes(bundle), "desktop_checks_deferred": defer_desktop}
    write_state(work, state)
    print("Signing inputs prepared. Submit inputs/ through the trusted SignPath workflow; no release archive exists.")


def assemble(work: Path, bundle: Path, compiler: Path, certificate: str, signtool: Path, signed: Path) -> None:
    state = read_state(work, "inputs-prepared", certificate)
    if digest(compiler) != state["compiler_sha256"]:
        raise SigningError("The Inno compiler changed between signing stages")
    if digest(ROOT / "packaging/windows.iss") != state["recipe_sha256"]:
        raise SigningError("The installer recipe changed between signing stages")
    verify_tree(bundle, state["bundle_hashes"])
    exact_files(signed, INPUTS)
    reports = []
    # Verify every output before changing the bundle or compiling with it.
    for name in sorted(INPUTS):
        verify_payload(work / "inputs" / name, signed / name)
        reports.append(verify_signature(signed / name, certificate, signtool))
    for name, relative in BUNDLE_PATHS.items():
        shutil.copyfile(signed / name, bundle / relative)
    cache = work / "uninstaller-cache" / state["uninstaller_cache_name"]
    shutil.copyfile(signed / "uninstaller.exe", cache)
    subprocess.run(compiler_command(compiler, work), cwd=ROOT, stdin=subprocess.DEVNULL, check=True, timeout=300)
    installer = work / "installer-input" / f"CyberAtlas-{__version__}-Setup.exe"
    exact_files(work / "installer-input", {installer.name})
    state.update(stage="installer-prepared", bundle_hashes=tree_hashes(bundle),
                 signed_input_reports=reports, signed_uninstaller_sha256=digest(cache), installer_sha256=digest(installer))
    write_state(work, state)
    print("Installer prepared with verified signed application and uninstaller. Its outer signature is still required.")


def verify_signed_bundle(work: Path, bundle: Path, state: dict, certificate: str, signtool: Path) -> list[dict]:
    verify_tree(bundle, state["bundle_hashes"])
    cache = work / "uninstaller-cache" / state["uninstaller_cache_name"]
    if digest(cache) != state["signed_uninstaller_sha256"]:
        raise SigningError("The signed uninstaller changed after assembly")
    reports = [verify_signature(bundle / relative, certificate, signtool) for relative in BUNDLE_PATHS.values()]
    reports.append(verify_signature(cache, certificate, signtool))
    return reports


def finalize(work: Path, bundle: Path, destination: Path, certificate: str, signtool: Path,
             signed: Path, defer_desktop: bool) -> None:
    state = read_state(work, "installer-prepared", certificate)
    name = f"CyberAtlas-{__version__}-Setup.exe"
    exact_files(signed, {name})
    original = work / "installer-input" / name
    if digest(original) != state["installer_sha256"]:
        raise SigningError("The installer signing input changed")
    verify_payload(original, signed / name)
    reports = verify_signed_bundle(work, bundle, state, certificate, signtool)
    reports.append(verify_signature(signed / name, certificate, signtool))
    # No release output is created before signature and payload verification.
    installer = destination / name
    archive = destination / f"CyberAtlas-{__version__}-windows-x64.zip"
    if installer.exists() or archive.exists():
        raise SigningError("Final artifacts already exist; preserve them and use a fresh release checkout")
    desktop = "pending"
    if not defer_desktop:
        build_windows.check_executable(bundle / "CyberAtlas.exe", destination / "packaged-test-results.json", work)
    if not defer_desktop:
        build_windows.check_installer(signed / name, work, signature_check=lambda path: verify_signature(path, certificate, signtool))
        installer_result = json.loads((destination / "installer-test-results.json").read_text(encoding="utf-8"))
        desktop = "passed" if installer_result.get("passed") is True else "installer-check-pending"
    verify_tree(bundle, state["bundle_hashes"])
    shutil.copyfile(signed / name, installer)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                output.write(path, Path("CyberAtlas") / path.relative_to(bundle))
    checksums = "".join(f"{digest(path)}  {path.name}\n" for path in (installer, archive))
    (destination / "SHA256SUMS.txt").write_text(checksums, encoding="ascii")
    report = {"version": __version__, "signatures_verified": True, "certificate_sha256": certificate,
              "desktop_validation": desktop, "files": reports, "published": False}
    (destination / "windows-signing-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    state.update(stage="complete")
    write_state(work, state)
    print(f"Signed candidate verified and archived. Desktop validation: {desktop}. Nothing was published.")


def verify_candidate(destination: Path, work: Path, certificate: str, signtool: Path) -> None:
    """Validate an already signed installer on a disposable Windows account."""
    installer = destination / f"CyberAtlas-{__version__}-Setup.exe"
    report_path = destination / "windows-signing-report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        records = [item for item in report["files"] if item["file"] == installer.name]
        if (report["version"] != __version__ or report["certificate_sha256"] != certificate
                or len(records) != 1 or records[0]["sha256"] != digest(installer)):
            raise ValueError("Candidate metadata mismatch")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SigningError("Candidate report does not match this version, certificate or installer") from exc
    verify_signature(installer, certificate, signtool)
    work.mkdir(parents=True, exist_ok=True)
    build_windows.check_installer(installer, work, signature_check=lambda path: verify_signature(path, certificate, signtool))
    result = json.loads((destination / "installer-test-results.json").read_text(encoding="utf-8"))
    if result.get("passed") is not True:
        raise SigningError("Installer validation was skipped; use a disposable Windows account without Cyber Atlas installed")
    report["desktop_validation"] = "passed"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Signed installer and installed executable passed desktop checks. Nothing was published.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("preflight", "prepare", "assemble", "finalize", "verify"))
    parser.add_argument("--signed-directory", type=Path)
    parser.add_argument("--iscc", type=Path)
    parser.add_argument("--signtool", type=Path)
    parser.add_argument("--certificate-sha256", default=os.environ.get("WINDOWS_SIGNING_CERT_SHA256", ""))
    parser.add_argument("--defer-desktop-checks", action="store_true", help="Produce a signed candidate requiring desktop validation before publication")
    args = parser.parse_args()
    try:
        certificate = certificate_fingerprint(args.certificate_sha256)
        if sys.platform != "win32" or sys.maxsize <= 2**32:
            raise SigningError("Use 64-bit Python on Windows")
        signtool = find_signtool(args.signtool)
        compiler = build_windows.find_compiler(args.iscc) if args.stage in ("preflight", "prepare", "assemble") else None
        if args.stage in ("preflight", "prepare", "assemble") and compiler is None:
            raise SigningError("Inno Setup 6/7 is required; install it or pass --iscc")
        if args.stage in ("assemble", "finalize") and args.signed_directory is None:
            raise SigningError("--signed-directory is required for this stage")
        if args.defer_desktop_checks and args.stage not in ("prepare", "finalize"):
            raise SigningError("--defer-desktop-checks applies to prepare/finalize only")
        work, destination = ROOT / "build/windows/signpath", ROOT / "dist"
        bundle = destination / "CyberAtlas"
        if args.stage == "preflight":
            print("Signing tools and certificate fingerprint configured. No packages built or requests submitted.")
        elif args.stage == "prepare":
            prepare(work, bundle, compiler, certificate, args.defer_desktop_checks)
        elif args.stage == "assemble":
            assemble(work, bundle, compiler, certificate, signtool, args.signed_directory.resolve())
        elif args.stage == "finalize":
            finalize(work, bundle, destination, certificate, signtool,
                     args.signed_directory.resolve(), args.defer_desktop_checks)
        else:
            verify_candidate(destination, ROOT / "build/windows/signed-validation", certificate, signtool)
    except (SigningError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Signing preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
