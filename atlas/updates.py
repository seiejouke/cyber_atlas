"""Opt-in release checks and verified downloads. No GUI or third-party dependencies."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

REPOSITORY = "seiejouke/cyber_atlas"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
LATEST_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
APP_ID = "{6B2793DE-9136-42A5-BF2E-C05AD776517B}_is1"
CHECK_INTERVAL = 24 * 60 * 60
MAX_DOWNLOAD = 1024 * 1024 * 1024
DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
                  "github-releases.githubusercontent.com"}


class UpdateError(Exception):
    """A message suitable for showing in the Updates window."""


class DownloadCancelled(UpdateError):
    pass


def version_tuple(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise UpdateError("This release does not have a supported stable version number.")
    return tuple(int(part) for part in value.removeprefix("v").split("."))


@dataclass(frozen=True)
class UpdateContext:
    kind: str
    executable: Path | None = None


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    notes: str
    asset: ReleaseAsset | None

    @property
    def newer(self) -> bool:
        return version_tuple(self.version) > version_tuple(__version__)


@dataclass(frozen=True)
class UpdateSettings:
    automatic: bool = False
    last_check: float = 0.0

    def due(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return self.automatic and (self.last_check > now or now - self.last_check >= CHECK_INTERVAL)


def load_settings(path: Path) -> UpdateSettings:
    try:
        if path.stat().st_size > 32768:
            return UpdateSettings()
        data = json.loads(path.read_text(encoding="utf-8"))
        automatic, last = data.get("automatic", False), data.get("last_check", 0.0)
        if type(automatic) is not bool or type(last) not in (int, float) or not math.isfinite(last) or last < 0:
            return UpdateSettings()
        return UpdateSettings(automatic, float(last))
    except (OSError, ValueError, AttributeError):
        return UpdateSettings()


def save_settings(path: Path, settings: UpdateSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".updates-", delete=False) as stream:
            name = stream.name
            json.dump({"automatic": settings.automatic, "last_check": settings.last_check}, stream)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


def update_context() -> UpdateContext:
    if not getattr(sys, "frozen", False):
        return UpdateContext("source")
    executable = Path(sys.executable).resolve()
    if sys.platform == "win32":
        import winreg
        key = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | view) as entry:
                    location = winreg.QueryValueEx(entry, "InstallLocation")[0]
                if Path(location).resolve() == executable.parent:
                    return UpdateContext("windows", executable)
            except (OSError, TypeError, ValueError):
                continue
        return UpdateContext("portable", executable)
    if sys.platform == "linux":
        image = os.environ.get("APPIMAGE")
        try:
            if image and Path(image).is_absolute() and Path(image).suffix == ".AppImage" and Path(image).is_file():
                return UpdateContext("appimage", Path(image).resolve())
        except (OSError, ValueError):
            pass
        if executable == Path("/opt/cyber-atlas/CyberAtlas"):
            return UpdateContext("deb", executable)
    return UpdateContext("manual", executable)


def parse_release(data: dict, context: UpdateContext) -> Release:
    try:
        version = data["tag_name"]
        version_tuple(version)
        if data.get("draft") or data.get("prerelease"):
            raise UpdateError("Preview releases are not installed automatically.")
        url = f"{RELEASES_URL}/tag/{version}"
        if data["html_url"] != url:
            raise UpdateError("The release does not belong to Cyber Atlas.")
        number = version.removeprefix("v")
        names = {"windows": f"CyberAtlas-{number}-Setup.exe", "deb": f"cyber-atlas_{number}_amd64.deb",
                 "appimage": f"CyberAtlas-{number}-x86_64.AppImage"}
        asset = None
        if context.kind in names:
            matches = [entry for entry in data.get("assets", []) if entry.get("name") == names[context.kind]]
            if len(matches) != 1:
                raise UpdateError("The package for your computer is not available yet. Try again later or view the release.")
            entry = matches[0]
            expected_url = f"{RELEASES_URL}/download/{version}/{entry['name']}"
            digest = entry.get("digest", "")
            size = entry.get("size")
            if (entry.get("browser_download_url") != expected_url or entry.get("state") != "uploaded"
                    or type(size) is not int or not 0 < size <= MAX_DOWNLOAD
                    or not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)):
                raise UpdateError("This package cannot be verified. View the release or try again later.")
            asset = ReleaseAsset(entry["name"], expected_url, size, digest[7:])
        notes = data.get("body") or "No release notes were provided."
        if not isinstance(notes, str):
            raise UpdateError("The release notes could not be read.")
        return Release(number, url, notes[:20000], asset)
    except (KeyError, TypeError, AttributeError):
        raise UpdateError("GitHub returned incomplete release information. Try again later.") from None


def _allowed_url(url: str, hosts: set[str]) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname in hosts and parsed.port in (None, 443)
            and not parsed.username and not parsed.password and not parsed.fragment)


class _ReleaseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, url):
        if not _allowed_url(url, DOWNLOAD_HOSTS):
            raise UpdateError("The download redirected to an unexpected location.")
        return super().redirect_request(request, file, code, message, headers, url)


def _open(url: str, *, metadata: bool = False):
    hosts = {"api.github.com"} if metadata else DOWNLOAD_HOSTS
    if not _allowed_url(url, hosts):
        raise UpdateError("The update address is not trusted.")
    headers = {"User-Agent": f"CyberAtlas/{__version__}", "Accept": "application/vnd.github+json" if metadata else "application/octet-stream"}
    if metadata:
        headers["X-GitHub-Api-Version"] = "2026-03-10"
    opener = urllib.request.build_opener(_ReleaseRedirects())
    return opener.open(urllib.request.Request(url, headers=headers), timeout=15)


def check_release(context: UpdateContext) -> Release:
    try:
        with _open(LATEST_API, metadata=True) as response:
            content = response.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise UpdateError("The release information is too large to read.")
        return parse_release(json.loads(content), context)
    except urllib.error.HTTPError as error:
        if error.code in (403, 429):
            raise UpdateError("GitHub is limiting update checks. Please try again later.") from None
        raise UpdateError("Release information is unavailable. Please try again later.") from None
    except (OSError, ValueError):
        raise UpdateError("Could not reach GitHub. Check your connection and try again.") from None


def verify_download(path: Path, asset: ReleaseAsset) -> bool:
    if not path.is_file() or path.stat().st_size != asset.size:
        return False
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest() == asset.sha256


def download_release(release: Release, directory: Path, cancel: threading.Event, progress=lambda received, total: None) -> Path:
    asset = release.asset
    if asset is None:
        raise UpdateError("Use the release page to update this copy of Cyber Atlas.")
    version_tuple(release.version)
    if (asset.name != Path(asset.name).name or "\\" in asset.name
            or asset.url not in (f"{RELEASES_URL}/download/{tag}/{asset.name}" for tag in (release.version, "v" + release.version))):
        raise UpdateError("The update package address is not trusted.")
    directory = directory / release.version
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / asset.name
    if verify_download(target, asset):
        if cancel.is_set():
            raise DownloadCancelled("Download cancelled.")
        return target
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".download-", suffix=".part", delete=False) as stream:
            temporary = Path(stream.name)
            with _open(asset.url) as response:
                received, last_progress = 0, 0.0
                while True:
                    if cancel.is_set():
                        raise DownloadCancelled("Download cancelled.")
                    block = response.read(256 * 1024)
                    if not block:
                        break
                    received += len(block)
                    if received > asset.size:
                        raise UpdateError("The download size does not match the release. Nothing was installed.")
                    stream.write(block)
                    if time.monotonic() - last_progress >= .1:
                        progress(received, asset.size)
                        last_progress = time.monotonic()
        if cancel.is_set():
            raise DownloadCancelled("Download cancelled.")
        if not verify_download(temporary, asset):
            raise UpdateError("The download did not pass verification. Nothing was installed. Please try again.")
        os.replace(temporary, target)
        progress(asset.size, asset.size)
        return target
    except urllib.error.HTTPError:
        raise UpdateError("The download is unavailable. Please try again later.") from None
    except OSError:
        raise UpdateError("The update could not be downloaded or saved. Check your connection and available space.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def start_windows_update(path: Path, asset: ReleaseAsset, context: UpdateContext, atlas: Path, directory: Path):
    if context.kind != "windows" or context.executable is None or not verify_download(path, asset):
        raise UpdateError("The update could not be verified. Please download it again.")
    directory.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="apply-", dir=directory))
    helper = Path(__file__).with_name("update_helper.ps1")
    if not helper.is_file():
        raise UpdateError("The update helper is missing. Download the installer from the release page.")
    payload = directory / "apply-update.json"
    install_args = ["/CURRENTUSER", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                    "/NOCLOSEAPPLICATIONS", "/NORESTARTAPPLICATIONS", "/RESTARTEXITCODE=3010",
                    f"/DIR={context.executable.parent}", f"/LOG={directory / 'installer.log'}"]
    payload.write_text(json.dumps({"parent_pid": os.getpid(), "installer": str(path.resolve()),
        "sha256": asset.sha256, "executable": str(context.executable),
        "installer_arguments": subprocess.list2cmdline(install_args),
        "restart_arguments": subprocess.list2cmdline(["--file", str(atlas.resolve())]),
        "ready": str((directory / "helper-ready").resolve()),
        "result": str((directory / "apply-result.json").resolve())}), encoding="utf-8")
    # Copy out of the installed directory: the installer replaces its contents.
    helper_copy = directory / "apply-update.ps1"
    shutil.copyfile(helper, helper_copy)
    powershell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden", "-File", str(helper_copy), "-Payload", str(payload)]
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.GetDllDirectoryW.argtypes = (ctypes.c_uint, ctypes.c_wchar_p)
        kernel.SetDllDirectoryW.argtypes = (ctypes.c_wchar_p,)
        previous = ctypes.create_unicode_buffer(32768)
        kernel.GetDllDirectoryW(len(previous), previous)
        kernel.SetDllDirectoryW(None)
        try:
            process = subprocess.Popen(command, cwd=directory, env=external_environment(), creationflags=subprocess.CREATE_NO_WINDOW)
        finally:
            kernel.SetDllDirectoryW(previous.value or None)
    else:
        process = subprocess.Popen(command, cwd=directory, env=external_environment(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.monotonic() + 8
    ready = directory / "helper-ready"
    while not ready.is_file() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(.05)
    if not ready.is_file() or process.poll() is not None:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=3)
        raise UpdateError("Windows could not start the update helper. Your app is still open; use the installer from the release page.")
    return process


def external_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in ("APPIMAGE", "APPDIR", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH", "TCL_LIBRARY", "TK_LIBRARY"):
        environment.pop(key, None)
    if environment.get("LD_LIBRARY_PATH_ORIG"):
        environment["LD_LIBRARY_PATH"] = environment.pop("LD_LIBRARY_PATH_ORIG")
    else:
        environment.pop("LD_LIBRARY_PATH", None)
        environment.pop("LD_LIBRARY_PATH_ORIG", None)
    return environment


def replace_appimage(path: Path, asset: ReleaseAsset, destination: Path, atlas: Path) -> None:
    if not verify_download(path, asset) or not destination.is_file() or destination.suffix != ".AppImage":
        raise UpdateError("The AppImage update could not be verified.")
    staged = None
    backup = destination.with_name(destination.name + ".previous")
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".cyber-atlas-update-", delete=False) as stream:
            staged = Path(stream.name)
            with path.open("rb") as source:
                shutil.copyfileobj(source, stream)
        staged.chmod(destination.stat().st_mode | 0o111)
        if not verify_download(staged, asset):
            raise UpdateError("The staged AppImage did not pass verification. Nothing was replaced.")
        shutil.copy2(destination, backup)
        os.replace(staged, destination)
        try:
            subprocess.Popen([str(destination), "--file", str(atlas.resolve())], env=external_environment(), start_new_session=True)
        except OSError:
            os.replace(backup, destination)
            raise
    except OSError:
        raise UpdateError("The AppImage could not be replaced or restarted. Choose a writable location or use the release page.") from None
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
