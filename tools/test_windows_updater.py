"""Test the real update helper against an isolated installer identity and atlas.

Run after tools/build_windows.py, with --previous-zip pointing to an older
portable Windows release. The real Cyber Atlas installation is never replaced.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch
from types import SimpleNamespace
from uuid import uuid4
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas import __version__, updates
from atlas.history import HistoryStore
from atlas.model import InformationEntry, Subconcept, example_atlas
from atlas.storage import write_atlas
from tools.build_windows import check_executable, find_compiler


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def registration(identity):
    import winreg
    key = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{identity}"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as entry:
            return {name: winreg.QueryValueEx(entry, name)[0] for name in ("DisplayVersion", "InstallLocation")}
    except FileNotFoundError:
        return None


def close_window(pid):
    """Close the restarted main window; return whether WM_CLOSE was posted."""
    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    posted = []
    user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)

    def visit(window, parameter):
        found = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(found))
        if found.value == pid and user32.IsWindowVisible(window):
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(window, title, len(title))
            if title.value == "Cyber Atlas":
                posted.append(bool(user32.PostMessageW(window, 0x0010, 0, 0)))  # WM_CLOSE
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return any(posted)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-zip", type=Path, required=True)
    parser.add_argument("--previous-version", default="0.9.1")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Run this integration check on Windows.")
    compiler = find_compiler(None)
    if compiler is None:
        parser.error("Inno Setup is required.")
    baseline = registration(updates.APP_ID)
    work = (ROOT / "build/windows-updater").resolve()
    assert work.is_relative_to(ROOT.resolve())
    work.mkdir(parents=True, exist_ok=True)
    checks = []
    result = {"passed": False, "checks": checks, "previous_version": args.previous_version, "version": __version__}
    try:
        with TemporaryDirectory(prefix="update-test-", dir=work) as folder:
            directory = Path(folder).resolve()
            assert directory.is_relative_to(work)
            previous = directory / "previous"
            previous.mkdir()
            with zipfile.ZipFile(args.previous_zip) as archive:
                for item in archive.infolist():
                    destination = (previous / item.filename).resolve()
                    if not destination.is_relative_to(previous) or item.file_size > 512 * 1024 * 1024:
                        raise RuntimeError("Unsafe path in the previous package")
                archive.extractall(previous)
            test_id = "{" + str(uuid4()).upper() + "}_is1"
            source = (ROOT / "packaging/windows.iss").read_text()
            source = source.replace("6B2793DE-9136-42A5-BF2E-C05AD776517B", test_id[1:-5])
            source = source.replace('#define RepoRoot AddBackslash(SourcePath) + ".."', f'#define RepoRoot "{ROOT}"')
            source = source.replace("Cyber Atlas", "Cyber Atlas updater test")
            source = source.replace("OutputDir={#RepoRoot}\\dist", f"OutputDir={directory / 'installers'}")
            source = source.replace("OutputBaseFilename=CyberAtlas-{#AppVersion}-Setup", "OutputBaseFilename=Update-test-{#AppVersion}")
            installers = []
            for version, bundle in ((args.previous_version, previous / "CyberAtlas"), (__version__, ROOT / "dist/CyberAtlas")):
                script = directory / f"installer-{version}.iss"
                script.write_text(source.replace('Source: "{#RepoRoot}\\dist\\CyberAtlas\\*"', f'Source: "{bundle}\\*"'), encoding="utf-8")
                subprocess.run([str(compiler), "/Q", f"/DAppVersion={version}", str(script)], check=True)
                installers.append(directory / "installers" / f"Update-test-{version}.exe")
            application = directory / "Installed app"
            user_data = directory / "Saved notes" / "atlas.json"
            fixture = example_atlas()
            if args.previous_version not in ("0.7.1", "0.7.2", "0.8.0", "0.8.1"):
                owner = fixture.nodes[0]
                child = Subconcept("upgrade-child", owner.id, "Saved upgrade subconcept", "Independent saved child notes", 0)
                fixture = fixture.with_child(child)
                fixture = fixture.with_entry(InformationEntry("upgrade-main-copy", owner.id, owner.name, owner.notes))
                fixture = fixture.with_entry(InformationEntry("upgrade-child-copy", child.id, child.name, child.notes))
                fixture = fixture.with_entry(InformationEntry("upgrade-extra", child.id, "Additional observation", "Distinct saved information"))
            previous_notes = fixture.with_node(replace(fixture.nodes[0], notes="Earlier saved upgrade notes"))
            write_atlas(user_data, previous_notes, backup=False)
            write_atlas(user_data, fixture)
            if updates.version_tuple(args.previous_version) < updates.version_tuple("0.10.0"):
                # Start the integration check with files the older binary can
                # actually read, including its previous-version backup.
                for legacy_path in (user_data, user_data.with_suffix(".json.bak")):
                    previous_data = json.loads(legacy_path.read_text(encoding="utf-8"))
                    previous_data.pop("flows", None)
                    previous_data["version"] = 10
                    if args.previous_version in ("0.7.1", "0.7.2", "0.8.0", "0.8.1"):
                        previous_data.pop("information_entries", None)
                        previous_data["version"] = 9
                    if args.previous_version in ("0.7.1", "0.7.2"):
                        previous_data["version"] = 8
                        previous_data.pop("subconcepts", None)
                    legacy_path.write_text(json.dumps(previous_data), encoding="utf-8")
            saved = user_data.read_bytes()
            saved_backup = user_data.with_suffix(".json.bak").read_bytes()
            try:
                subprocess.run([str(installers[0]), "/CURRENTUSER", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/SP-",
                    "/NORESTART", "/NOICONS", "/TASKS=", "/NOCLOSEAPPLICATIONS", f"/DIR={application}"], check=True)
                executable = application / "CyberAtlas.exe"
                assert registration(test_id)["DisplayVersion"] == args.previous_version
                assert digest(executable) == digest(previous / "CyberAtlas/CyberAtlas.exe")
                checks.append("Older Windows release installs under a separate test AppId; the real application registration is unchanged")
                powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
                parent = subprocess.Popen([str(powershell), "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                    "-Command", "Start-Sleep -Seconds 3"], creationflags=subprocess.CREATE_NO_WINDOW)
                asset = updates.ReleaseAsset(installers[1].name, "", installers[1].stat().st_size, digest(installers[1]))
                def prepared(command, **kwargs):
                    data = json.loads(Path(command[-1]).read_text())
                    Path(data["ready"]).touch()
                    return SimpleNamespace(poll=lambda: None)

                with patch("atlas.updates.subprocess.Popen", side_effect=prepared) as launch:
                    updates.start_windows_update(installers[1], asset, updates.UpdateContext("windows", executable), user_data, directory / "handoff")
                command, kwargs = launch.call_args.args[0], launch.call_args.kwargs
                kwargs["env"] = {**kwargs["env"], "LOCALAPPDATA": str(directory / "Isolated user data")}
                payload_path = Path(command[-1])
                payload = json.loads(payload_path.read_text())
                assert str(user_data.resolve()) in payload["restart_arguments"]
                payload["parent_pid"] = parent.pid
                Path(payload["ready"]).unlink()
                payload["installer_arguments"] += " /NOICONS /TASKS="
                payload_path.write_text(json.dumps(payload), encoding="utf-8")
                helper = subprocess.Popen(command, **kwargs)
                restarted = None
                try:
                    time.sleep(.5)
                    assert registration(test_id)["DisplayVersion"] == args.previous_version
                    parent.wait(timeout=10)
                    checks.append("The background helper waits for the old process before applying the installer")
                    deadline = time.monotonic() + 120
                    handoff_report = Path(payload["result"])
                    while not handoff_report.is_file() and time.monotonic() < deadline:
                        time.sleep(.2)
                    assert handoff_report.is_file(), "No update handoff report was written"
                    handoff = json.loads(handoff_report.read_text(encoding="utf-8-sig"))
                    assert handoff["passed"], handoff
                    helper.wait(timeout=10)
                    restarted = handoff["restarted_pid"]
                    assert registration(test_id)["DisplayVersion"] == __version__
                    assert digest(executable) == digest(ROOT / "dist/CyberAtlas/CyberAtlas.exe")
                    checks.append("The real update helper upgrades the older binary and installer registration to the new version")
                    kernel = ctypes.windll.kernel32
                    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
                    kernel.OpenProcess.restype = wintypes.HANDLE
                    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
                    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
                    handle = kernel.OpenProcess(0x00100000, False, restarted)
                    assert handle and kernel.WaitForSingleObject(handle, 0) == 258, "Restarted app did not stay open"
                    try:
                        deadline = time.monotonic() + 45
                        while not close_window(restarted):
                            assert kernel.WaitForSingleObject(handle, 0) == 258, "Restarted app exited before its main window appeared"
                            assert time.monotonic() < deadline, "Restarted app did not display its main window"
                            time.sleep(.2)
                        assert kernel.WaitForSingleObject(handle, 15000) == 0, "Test app did not close normally"
                    finally:
                        kernel.CloseHandle(handle)
                    assert user_data.read_bytes() == saved
                    checks.append("The updated app reopens with the original atlas path; closing it preserves notes, subconcepts and information records byte for byte")
                    history = HistoryStore(user_data)
                    assert history.path.is_file(), "The upgraded app did not begin recording history"
                    revisions = history.revisions()
                    assert len(revisions) == 2 and [item.kind for item in revisions] == ["baseline", "backup"]
                    assert history.load(revisions[0].id) == fixture and history.load(revisions[1].id) == previous_notes
                    assert user_data.with_suffix(".json.bak").read_bytes() == saved_backup
                    checks.append("The upgraded app starts history with the unchanged current atlas and valid previous backup, without inventing earlier dates")
                    report = check_executable(executable, directory / "updated-runtime.json", directory)
                    result["updated_runtime_checks"] = report["checks_passed"]
                    checks.append(f"The upgraded executable passes {report['checks_passed']} frozen runtime checks")
                finally:
                    if helper.poll() is None:
                        helper.terminate()
                        helper.wait(timeout=10)
                    if parent.poll() is None:
                        parent.terminate()
                        parent.wait(timeout=10)
                    if restarted is not None:
                        close_window(restarted)
                        time.sleep(.5)
            finally:
                uninstaller = application / "unins000.exe"
                if uninstaller.is_file():
                    subprocess.run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True, timeout=60)
            assert registration(test_id) is None and user_data.read_bytes() == saved
            assert history.path.is_file() and history.load(revisions[0].id) == fixture
            assert registration(updates.APP_ID) == baseline
            checks.append("Uninstall removes the test registration, preserves the atlas, and leaves the real Cyber Atlas installation unchanged")
        result["passed"] = True
    finally:
        result["checks_passed"] = len(checks)
        (ROOT / "dist/windows-updater-test-results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
