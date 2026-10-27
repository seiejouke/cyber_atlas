"""Build and check Linux x86_64 AppImage and Debian packages."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas import __version__
from tools.release_legal import include_legal_files, write_debian_copyright

TOOL_URL = "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
TOOL_SHA256 = "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
RUNTIME_URL = "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"
RUNTIME_SHA256 = "617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46"
DESKTOP = "io.github.seiejouke.CyberAtlas.desktop"


def digest(path: Path) -> str:
    with path.open("rb") as content:
        return hashlib.file_digest(content, "sha256").hexdigest()


def download(url: str, path: Path, expected: str):
    if not path.is_file():
        request = urllib.request.Request(url, headers={"User-Agent": "CyberAtlas-build"})
        with urllib.request.urlopen(request, timeout=120) as response, path.open("wb") as output:
            shutil.copyfileobj(response, output)
    if digest(path) != expected:
        raise RuntimeError(f"Upstream checksum mismatch: {path.name}. Review the upstream release before updating the pinned hash.")
    path.chmod(0o755)


def write_executable(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def copy_bundle(bundle: Path, destination: Path):
    shutil.copytree(bundle, destination, symlinks=True)
    # Python libraries, executables and shell launchers must be accessible to
    # every account that can run a system-installed Debian package.
    for path in destination.rglob("*"):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() or os.access(path, os.X_OK) else 0o644)


def check_application(command: list[str], report: Path, work: Path, *, test_directory: Path | None = None):
    environment = os.environ.copy()
    for variable in ("PYTHONPATH", "PYTHONHOME", "TCL_LIBRARY", "TK_LIBRARY", "VIRTUAL_ENV", "LD_LIBRARY_PATH"):
        environment.pop(variable, None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PATH"] = "/usr/bin:/bin"
    context = TemporaryDirectory(prefix="runtime-check-", dir=work) if test_directory is None else nullcontext(test_directory)
    with context as directory:
        environment["XDG_DATA_HOME"] = str(Path(directory) / "user-data")
        process = subprocess.run(command + ["--file", str(Path(directory) / "atlas.json"), "--self-test", str(report)],
                                 cwd=directory, env=environment, timeout=120)
    if process.returncode or not report.is_file():
        raise RuntimeError(f"Linux runtime check failed with exit code {process.returncode}; see {report}")
    result = json.loads(report.read_text(encoding="utf-8"))
    if not result.get("passed") or not result.get("frozen"):
        raise RuntimeError(f"Linux packaged self-test failed: {result.get('error', report)}")
    print(f"{report.name}: {result['checks_passed']} checks passed", flush=True)
    return result


def make_appimage(bundle: Path, work: Path, destination: Path):
    directory = work / "CyberAtlas.AppDir"
    directory.mkdir()
    copy_bundle(bundle, directory / "usr" / "lib" / "cyber-atlas")
    write_executable(directory / "usr" / "bin" / "cyber-atlas", '#!/bin/sh\nBINDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$BINDIR/../lib/cyber-atlas/CyberAtlas" "$@"\n')
    write_executable(directory / "AppRun", '#!/bin/sh\nAPPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$APPDIR/usr/lib/cyber-atlas/CyberAtlas" "$@"\n')
    shutil.copy2(ROOT / "packaging" / DESKTOP, directory / DESKTOP)
    shutil.copy2(ROOT / "assets" / "CyberAtlas.png", directory / "cyber-atlas.png")
    (directory / ".DirIcon").symlink_to("cyber-atlas.png")
    tool, runtime = work / "appimagetool.AppImage", work / "runtime-x86_64"
    download(TOOL_URL, tool, TOOL_SHA256)
    download(RUNTIME_URL, runtime, RUNTIME_SHA256)
    output = destination / f"CyberAtlas-{__version__}-x86_64.AppImage"
    environment = os.environ.copy()
    environment.update(ARCH="x86_64", VERSION=__version__, APPIMAGE_EXTRACT_AND_RUN="1")
    subprocess.run([str(tool), "--no-appstream", "--runtime-file", str(runtime), str(directory), str(output)],
                   env=environment, check=True, cwd=work)
    output.chmod(0o755)
    return output


def make_deb(bundle: Path, work: Path, destination: Path):
    directory = work / "debian"
    copy_bundle(bundle, directory / "opt" / "cyber-atlas")
    write_executable(directory / "usr" / "bin" / "cyber-atlas", '#!/bin/sh\nexec /opt/cyber-atlas/CyberAtlas "$@"\n')
    applications = directory / "usr" / "share" / "applications"
    applications.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging" / DESKTOP, applications / DESKTOP)
    icons = directory / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    icons.mkdir(parents=True)
    shutil.copy2(ROOT / "assets" / "CyberAtlas.png", icons / "cyber-atlas.png")
    documentation = directory / "usr" / "share" / "doc" / "cyber-atlas"
    write_debian_copyright(bundle, documentation / "copyright")
    shutil.copy2(bundle / "SOURCE_CODE.txt", documentation / "SOURCE_CODE.txt")
    control = directory / "DEBIAN"
    control.mkdir()
    size = sum(path.stat().st_size for path in directory.rglob("*") if path.is_file()) // 1024
    (control / "control").write_text(
        f"Package: cyber-atlas\nVersion: {__version__}\nArchitecture: amd64\n"
        "Section: education\nPriority: optional\nMaintainer: Cyber Atlas contributors\n"
        f"Installed-Size: {size}\n"
        "Depends: libc6 (>= 2.35), libstdc++6 (>= 11), libgcc-s1, libgl1, libglx0, libx11-6, libxext6, libxrender1, libxft2, libxss1, libfontconfig1, libfreetype6\n"
        "Homepage: https://github.com/seiejouke/cyber_atlas\n"
        "Description: A desktop notebook for three-dimensional knowledge maps\n"
        " Organize notes in custom layers, explore Blocks and Nodes views, and\n"
        " import or export atlases as JSON. Python, Tk and VTK are included.\n", encoding="utf-8")
    subprocess.run(["desktop-file-validate", str(applications / DESKTOP)], check=True)
    output = destination / f"cyber-atlas_{__version__}_amd64.deb"
    subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(directory), str(output)], check=True)
    return output


def check_install(package: Path, work: Path, destination: Path):
    existing = subprocess.run(["dpkg-query", "-W", "-f=${Status}", "cyber-atlas"], capture_output=True, text=True)
    if "install ok installed" in existing.stdout:
        raise RuntimeError("An existing Cyber Atlas installation was found. Installer testing requires a disposable environment.")
    saved_data = work / "saved-user-data" / "atlas.json"
    saved_data.parent.mkdir()
    checks = []
    try:
        subprocess.run(["sudo", "-n", "dpkg", "-i", str(package)], check=True)
        checks.append("Debian package installs and creates the application launcher")
        runtime = check_application(["/usr/bin/cyber-atlas"], destination / "linux-installed-test-results.json", work,
                                    test_directory=saved_data.parent)
        original = saved_data.read_bytes()
        checks.append(f"Installed launcher passes all {runtime['checks_passed']} rendering and storage checks")
        subprocess.run(["sudo", "-n", "dpkg", "-i", str(package)], check=True)
        if saved_data.read_bytes() != original:
            raise RuntimeError("Upgrade changed saved user data")
        checks.append("Same-version package upgrade preserves saved user data")
    finally:
        subprocess.run(["sudo", "-n", "dpkg", "--purge", "cyber-atlas"], check=True)
    if Path("/opt/cyber-atlas/CyberAtlas").exists() or saved_data.read_bytes() != original:
        raise RuntimeError("Package removal did not preserve saved user data and remove the application")
    checks.append("Package removal deletes the application and preserves user data")
    (destination / "linux-installer-test-results.json").write_text(
        json.dumps({"passed": True, "checks_passed": len(checks), "checks": checks}, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-install", action="store_true", help="Install, upgrade and remove the Debian package in a disposable system")
    arguments = parser.parse_args()
    if sys.platform != "linux" or platform.machine() not in ("x86_64", "amd64"):
        parser.error("Build this package on Linux x86_64.")
    for tool in ("dpkg-deb", "desktop-file-validate"):
        if not shutil.which(tool):
            parser.error(f"Required build tool is missing: {tool}")
    destination = ROOT / "dist" / "linux"
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)
    with TemporaryDirectory(prefix="cyber-atlas-linux-") as temporary:
        work = Path(temporary)
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "WARN",
                        "--distpath", str(work / "frozen"), "--workpath", str(work / "pyinstaller"),
                        str(ROOT / "packaging" / "linux.spec")], cwd=ROOT, check=True)
        bundle = work / "frozen" / "CyberAtlas"
        include_legal_files(bundle)
        (bundle / "Read me.txt").write_text(
            f"Cyber Atlas {__version__} for Linux x86_64\n\n"
            "Python, Tk and VTK are included. A working X11 or XWayland desktop and OpenGL driver are required.\n"
            "Built on Ubuntu 22.04; requires glibc 2.35 or newer and a compatible C++ runtime.\n"
            "Notes are saved in $XDG_DATA_HOME/CyberAtlas/atlas.json or ~/.local/share/CyberAtlas/atlas.json.\n"
            "Blocks starts in Outline appearance; select a block to fill it, or choose Solid to fill all blocks.\n"
            "Use Updates to check releases; daily checks are optional and off by default.\n"
            "Logs are stored beside the atlas in logs/. Removing the application leaves your notes in place.\n", encoding="utf-8")
        packaged = check_application([str(bundle / "CyberAtlas")], destination / "linux-packaged-test-results.json", work)
        package = make_deb(bundle, work, destination)
        appimage = make_appimage(bundle, work, destination)
        portable = check_application([str(appimage), "--appimage-extract-and-run"], destination / "linux-appimage-test-results.json", work)
        if arguments.test_install:
            check_install(package, work, destination)
    artifacts = [package, appimage]
    (destination / "SHA256SUMS-linux.txt").write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in artifacts), encoding="ascii")
    report = {
        "passed": True, "version": __version__, "platform": platform.platform(),
        "glibc": platform.libc_ver(), "python": platform.python_version(), "vtk": metadata.version("vtk"),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "packaged_checks": packaged["checks_passed"], "appimage_checks": portable["checks_passed"],
        "installer_checked": arguments.test_install,
        "files": [{"name": path.name, "bytes": path.stat().st_size, "sha256": digest(path)} for path in artifacts],
    }
    (destination / "linux-build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Linux packages ready:", *(str(path) for path in artifacts), sep="\n", flush=True)


if __name__ == "__main__":
    main()
