"""Linux x86_64 folder bundle used by the Debian package and AppImage."""
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).parent
analysis = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "assets" / "CyberAtlas.png"), "assets")]
          + copy_metadata("vtk") + copy_metadata("numpy"),
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "IPython", "pytest", "PIL"],
    noarchive=False,
)
# Use the host's graphics and C++ runtime so its graphics drivers load their
# matching libraries. The build baseline supplies the minimum supported ABI.
host_libraries = ("libstdc++.so.6", "libgcc_s.so.1", "libGL.so", "libGLX.so", "libGLdispatch.so", "libEGL.so")
analysis.binaries = [item for item in analysis.binaries
                     if not Path(item[0]).name.startswith(host_libraries)]
archive = PYZ(analysis.pure)
executable = EXE(
    archive, analysis.scripts, [], exclude_binaries=True,
    name="CyberAtlas", debug=False, strip=False, upx=False, console=True,
)
collection = COLLECT(
    executable, analysis.binaries, analysis.datas,
    strip=False, upx=False, name="CyberAtlas",
)
