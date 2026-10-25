"""Build, check and archive Cyber Atlas for Windows. Run from any directory."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas import __version__


def make_icon():
    """Draw a geometric atlas symbol; Pillow is a build dependency only."""
    from PIL import Image, ImageDraw
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    image = Image.new("RGBA", (1024, 1024))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 1016, 1016), radius=220, fill="#101c2a")
    for y, color in ((640, "#65b6a1"), (490, "#8ca9da"), (340, "#70cbd8")):
        draw.ellipse((180, y - 110, 844, y + 110), outline=color, width=22)
        draw.ellipse((320, y - 55, 704, y + 55), outline=color, width=12)
    draw.line((512, 215, 512, 810), fill="#91a6bb", width=14)
    for x, y, color in ((512, 340, "#70cbd8"), (740, 490, "#edbb69"), (285, 640, "#65b6a1")):
        draw.ellipse((x - 39, y - 39, x + 39, y + 39), fill=color, outline="#101c2a", width=10)
    image = image.resize((256, 256), Image.Resampling.LANCZOS)
    image.save(assets / "CyberAtlas.png")
    image.save(assets / "CyberAtlas.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def make_version(work: Path):
    version = tuple(int(part) for part in __version__.split(".")) + (0,)
    (work / "version.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={version!r}, prodvers={version!r}, mask=0x3f,
                   flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', 'Cyber Atlas'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('InternalName', 'CyberAtlas'),
    StringStruct('OriginalFilename', 'CyberAtlas.exe'),
    StringStruct('ProductName', 'Cyber Atlas'),
    StringStruct('ProductVersion', '{__version__}')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
""", encoding="utf-8")


def find_compiler(explicit: Path | None) -> Path | None:
    candidates = [explicit, shutil.which("ISCC.exe"), ROOT / "build" / "tools" / "InnoSetup" / "ISCC.exe"]
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = Path(os.environ.get(variable, "C:/nonexistent"))
        for version in ("7", "6"):
            candidates.extend((base / f"Inno Setup {version}" / "ISCC.exe",
                               base / "Programs" / f"Inno Setup {version}" / "ISCC.exe"))
    return next((Path(path).resolve() for path in candidates if path and Path(path).is_file()), None)


def include_notices(bundle: Path):
    notices = bundle / "Third-party notices"
    notices.mkdir(exist_ok=True)
    for package in ("vtk", "numpy"):
        distribution = metadata.distribution(package)
        for item in distribution.files or ():
            if ".dist-info/licenses/" in str(item).replace("\\", "/"):
                target = notices / package / Path(*item.parts[item.parts.index("licenses") + 1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(distribution.locate_file(item), target)
    for name, path in (("Python", Path(sys.base_prefix) / "LICENSE.txt"),
                       ("Tcl", Path(sys.base_prefix) / "tcl" / "tcl8.6" / "license.terms"),
                       ("Tk", Path(sys.base_prefix) / "tcl" / "tk8.6" / "license.terms")):
        if path.is_file():
            shutil.copy2(path, notices / f"{name}-license.txt")


def check_executable(executable: Path, report_path: Path, work: Path, *, test_directory: Path | None = None):
    environment = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "TCL_LIBRARY", "TK_LIBRARY", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PATH"] = str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32")
    directory = TemporaryDirectory(prefix="packaged-test-", dir=work) if test_directory is None else nullcontext(test_directory)
    with directory as folder:
        subprocess.run([str(executable), "--file", str(Path(folder) / "atlas.json"),
                        "--self-test", str(report_path)], cwd=folder, env=environment,
                       check=True, timeout=120)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report.get("frozen") or not report.get("passed"):
        raise RuntimeError(f"Packaged application failed its self-test: {report_path}")
    print(f"Packaged application: {report['checks_passed']} checks passed.", flush=True)
    return report


def check_installer(installer: Path, work: Path):
    """Exercise the actual installer, then remove the isolated test installation."""
    import winreg
    key_name = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{6B2793DE-9136-42A5-BF2E-C05AD776517B}_is1"

    def registered():
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name, 0, winreg.KEY_READ | view):
                    return True
            except FileNotFoundError:
                pass
        return False

    if registered():
        reason = "Cyber Atlas is already installed for this account; the existing installation was preserved."
        (ROOT / "dist" / "installer-test-results.json").write_text(
            json.dumps({"passed": None, "skipped": reason}, indent=2) + "\n", encoding="utf-8")
        print(f"Installer check skipped: {reason}", flush=True)
        return
    checks = []
    with TemporaryDirectory(prefix="installer-test-", dir=work) as folder:
        directory = Path(folder)
        application = directory / "Cyber Atlas"
        user_data = directory / "User data"
        user_data.mkdir()
        command = [str(installer), "/CURRENTUSER", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                   "/SP-", "/NOICONS", "/TASKS=", f"/DIR={application}", f"/LOG={directory / 'install.log'}"]
        uninstaller = application / "unins000.exe"
        try:
            subprocess.run(command, cwd=directory, check=True, timeout=120)
            if not registered() or not (application / "CyberAtlas.exe").is_file():
                raise RuntimeError("The installer did not register the application and create the executable.")
            checks.append("Per-user silent installation succeeds in a path containing spaces")
            runtime = check_executable(application / "CyberAtlas.exe", ROOT / "dist" / "installed-test-results.json",
                                       work, test_directory=user_data)
            checks.append(f"Installed executable passes all {runtime['checks_passed']} bundled runtime checks")
            saved = (user_data / "atlas.json").read_bytes()
            subprocess.run(command, cwd=directory, check=True, timeout=120)
            if (user_data / "atlas.json").read_bytes() != saved:
                raise RuntimeError("Upgrade changed the saved test atlas.")
            checks.append("Reinstalling upgrades the same application without changing saved test data")
        finally:
            if uninstaller.is_file():
                subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                               cwd=directory, check=True, timeout=120)
        if (application / "CyberAtlas.exe").exists() or registered():
            raise RuntimeError("Uninstall did not remove the test application and its registration.")
        if (user_data / "atlas.json").read_bytes() != saved:
            raise RuntimeError("Uninstall changed the saved test atlas.")
        checks.append("Uninstall removes the executable and per-user registration while preserving saved test data")
    (ROOT / "dist" / "installer-test-results.json").write_text(
        json.dumps({"passed": True, "checks_passed": len(checks), "checks": checks}, indent=2) + "\n", encoding="utf-8")
    print(f"Installer: {len(checks)} lifecycle checks passed.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iscc", type=Path, help="Path to Inno Setup's ISCC.exe")
    parser.add_argument("--skip-installer", action="store_true", help="Build only the application and ZIP")
    parser.add_argument("--check-installer-only", action="store_true", help="Check an already built installer without rebuilding")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        parser.error("Build this x64 release using 64-bit Python on Windows.")
    work, destination = ROOT / "build" / "windows", ROOT / "dist"
    work.mkdir(parents=True, exist_ok=True)
    destination.mkdir(exist_ok=True)
    if args.check_installer_only:
        check_installer(destination / f"CyberAtlas-{__version__}-Setup.exe", work)
        return
    compiler = None if args.skip_installer else find_compiler(args.iscc)
    if not args.skip_installer and compiler is None:
        parser.error("Install Inno Setup 6/7, pass --iscc, or use --skip-installer.")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=ROOT, check=True)
    make_icon()
    make_version(work)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "WARN", "--distpath", str(destination),
                    "--workpath", str(work / "pyinstaller"), str(ROOT / "packaging" / "windows.spec")],
                   cwd=ROOT, check=True)
    bundle = destination / "CyberAtlas"
    include_notices(bundle)
    (bundle / "Read me.txt").write_text(
        f"Cyber Atlas {__version__} for Windows x64\n\n"
        "Extract this whole folder, then open CyberAtlas.exe. Python is included.\n"
        "Keep the _internal folder beside CyberAtlas.exe.\n\n"
        "Your atlas is saved to %LOCALAPPDATA%\\CyberAtlas\\atlas.json.\n"
        "The previous saved version is atlas.json.bak. Export JSON for lasting copies.\n"
        "Logs are in %LOCALAPPDATA%\\CyberAtlas\\logs.\n"
        "Upgrading or removing this application folder leaves your atlas in place.\n\n"
        "To move a node: Nodes > select a sphere > Move node > adjust controls > Save move.\n"
        "Cancel move or Escape restores the starting position and keeps text edits.\n\n"
        "Blocks starts in Outline appearance: only the selected block is filled.\n"
        "Hover outlines for labels, or choose Solid to fill every block.\n\n"
        "Use Updates to check for releases. Daily checks are optional and off by default.\n"
        "Installed copies can download a verified update and restart to apply it.\n\n"
        "Requires Windows 10/11 x64 with a working OpenGL graphics driver.\n"
        "This build is unsigned.\n", encoding="utf-8")
    report_path = destination / "packaged-test-results.json"
    check_executable(bundle / "CyberAtlas.exe", report_path, work)
    archive = destination / f"CyberAtlas-{__version__}-windows-x64.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(destination))
    artifacts = [archive]
    if compiler:
        subprocess.run([str(compiler), "/Q", f"/DAppVersion={__version__}", str(ROOT / "packaging" / "windows.iss")],
                       cwd=ROOT, check=True)
        artifacts.append(destination / f"CyberAtlas-{__version__}-Setup.exe")
        check_installer(artifacts[-1], work)
    checksums = []
    for artifact in artifacts:
        with artifact.open("rb") as content:
            digest = hashlib.file_digest(content, "sha256").hexdigest()
        checksums.append(f"{digest}  {artifact.name}\n")
    (destination / "SHA256SUMS.txt").write_text("".join(checksums), encoding="ascii")
    print("\nBuilt:", *(str(path) for path in artifacts), sep="\n", flush=True)


if __name__ == "__main__":
    main()
