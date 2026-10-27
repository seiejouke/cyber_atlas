"""Collect release notices and the application's corresponding source.

No network access, signing, package build or publication happens here.
"""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ENTRIES = (
    "LICENSE", "COPYRIGHT.txt", "THIRD_PARTY_NOTICES.md", "README.md", "AGENTS.md", ".gitattributes",
    "main.py", "run.bat", "run.sh", "requirements.txt", "requirements-build.txt",
    "atlas", "assets", "tools", "packaging", "tests", "examples", "docs", ".github/workflows",
)


class NoticeError(RuntimeError):
    """A release is missing required licensing information."""


def _copy(source: Path, target: Path) -> None:
    if not source.is_file() or not source.read_bytes().strip():
        raise NoticeError(f"Missing or empty required notice: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _runtime_notice(bundle: Path, name: str, project: Path, prefix: Path) -> tuple[Path, str]:
    if name == "Python":
        version = ".".join(map(str, sys.version_info[:3]))
        candidates = [prefix / "LICENSE.txt", prefix / "LICENSE"]
        if version == "3.12.3":
            candidates.append(project / "packaging/licenses/Python-3.12.3.txt")
    else:
        directory, script = ("_tcl_data", "init.tcl") if name == "Tcl" else ("_tk_data", "tk.tcl")
        runtime = bundle / "_internal" / directory
        source = runtime / script
        match = re.search(rf"package require -exact {name}\s+([\d.]+)",
                          source.read_text(encoding="utf-8")) if source.is_file() else None
        if match is None:
            raise NoticeError(f"Cannot identify bundled {name} version from {source}")
        version = match[1]
        family = ".".join(version.split(".")[:2])
        candidates = [runtime / "license.terms", prefix / "tcl" / f"{name.lower()}{family}" / "license.terms"]
        if version in ("8.6.12", "8.6.13", "8.6.14"):
            candidates.append(project / f"packaging/licenses/{name}-8.6.13.txt")
    for path in candidates:
        if path.is_file() and path.read_bytes().strip():
            return path, version
    raise NoticeError(f"No reviewed {name} notice for runtime {version}; add its upstream license before packaging")


def _source_files(project: Path) -> list[Path]:
    # Git honors ignored files and excludes user data and build environments.
    if (project / ".git").exists():
        untracked = subprocess.run(["git", "ls-files", "-z", "--others", "--exclude-standard",
                                    "--", *SOURCE_ENTRIES], cwd=project, check=True, capture_output=True)
        if untracked.stdout:
            raise NoticeError("Track new project source files in Git before packaging; untracked files are never archived")
        result = subprocess.run(["git", "ls-files", "-z", "--cached",
                                 "--", *SOURCE_ENTRIES], cwd=project, check=True, capture_output=True)
        paths = [project / name.decode("utf-8") for name in result.stdout.split(b"\0") if name]
    else:
        paths = []
        for entry in SOURCE_ENTRIES:
            path = project / entry
            paths.extend(path.rglob("*") if path.is_dir() else [path])
    files = []
    for path in sorted(set(paths)):
        relative = path.relative_to(project)
        if any(part in ("__pycache__", ".git", ".venv", "build", "dist") for part in relative.parts):
            continue
        if path.name == "atlas.json" or path.name.endswith((".pyc", ".pyo", ".bak", ".sqlite3")):
            continue
        if path.is_symlink():
            raise NoticeError(f"Source archives require regular files, not symlinks: {relative}")
        if path.is_file():
            files.append(path)
    return files


def include_legal_files(bundle: Path, *, project: Path = ROOT, prefix: Path | None = None) -> None:
    """Add licenses, a runtime notice inventory and application sources to a bundle."""
    project = project.resolve()
    prefix = Path(sys.base_prefix) if prefix is None else prefix
    for name in ("LICENSE", "COPYRIGHT.txt", "THIRD_PARTY_NOTICES.md"):
        _copy(project / name, bundle / name)
    notices = bundle / "Third-party notices"
    if notices.exists():
        raise NoticeError("Collect notices into a fresh bundle so stale license files cannot be retained")
    notices.mkdir()
    components = []
    for name in ("vtk", "numpy", "pyinstaller"):
        distribution = metadata.distribution(name)
        copied = []
        for item in distribution.files or ():
            parts = item.parts
            if "licenses" not in parts:
                continue
            index = parts.index("licenses")
            if index == 0 or not parts[index - 1].endswith(".dist-info"):
                continue
            relative = Path(*parts[index + 1:])
            if not relative.parts or relative.is_absolute() or ".." in relative.parts:
                raise NoticeError(f"Invalid license path in {name} metadata: {item}")
            target = notices / name / relative
            _copy(Path(distribution.locate_file(item)), target)
            copied.append(target.relative_to(notices).as_posix())
        if not copied:
            raise NoticeError(f"The {name} distribution did not supply a license directory")
        components.append({"name": name, "version": distribution.version, "notices": sorted(copied)})
    for name in ("Python", "Tcl", "Tk"):
        source, version = _runtime_notice(bundle, name, project, prefix)
        target = notices / f"{name}-license.txt"
        _copy(source, target)
        components.append({"name": name, "version": version, "notices": [target.name]})
    hashes = {path.relative_to(notices).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(notices.rglob("*")) if path.is_file()}
    (notices / "manifest.json").write_text(json.dumps({"components": components, "sha256": hashes}, indent=2) + "\n",
                                          encoding="utf-8")
    source_directory = bundle / "Source code"
    source_directory.mkdir()
    source_files = _source_files(project)
    for required in ("main.py", "requirements.txt", "tools/build_windows.py", "tools/build_linux.py",
                     "tools/release_legal.py", "docs/DEVELOPMENT.md", "LICENSE", "COPYRIGHT.txt", "THIRD_PARTY_NOTICES.md"):
        if project / required not in source_files:
            raise NoticeError(f"Missing application source: {required}")
    with zipfile.ZipFile(source_directory / "CyberAtlas-source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in source_files:
            archive.write(path, Path("CyberAtlas") / path.relative_to(project))
    (bundle / "SOURCE_CODE.txt").write_text(
        "The application source used for this build, including its build scripts,\n"
        "is in Source code/CyberAtlas-source.zip. See docs/DEVELOPMENT.md inside\n"
        "the archive for build instructions. Third-party dependency sources are\n"
        "not in that archive; their licenses remain separate.\n\n"
        "Project: https://github.com/seiejouke/cyber_atlas\n"
        "Runtime versions and license hashes: Third-party notices/manifest.json\n", encoding="utf-8")


def write_debian_copyright(bundle: Path, destination: Path) -> None:
    """Keep copyright and complete notices in Debian's standard documentation path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    sources = [bundle / "COPYRIGHT.txt", bundle / "LICENSE"]
    sources += [path for path in sorted((bundle / "Third-party notices").rglob("*"))
                if path.is_file() and path.name != "manifest.json"]
    with destination.open("w", encoding="utf-8", newline="\n") as output:
        for path in sources:
            output.write(f"\n--- {path.relative_to(bundle).as_posix()} ---\n\n")
            output.write(path.read_text(encoding="utf-8"))
            output.write("\n")
