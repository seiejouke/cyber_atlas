"""Windows folder bundle. Generated inputs come from tools/build_windows.py."""
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).parent
analysis = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "assets" / "CyberAtlas.png"), "assets"),
           (str(root / "assets" / "CyberAtlas.ico"), "assets"),
           (str(root / "atlas" / "update_helper.ps1"), "atlas")]
          + copy_metadata("vtk") + copy_metadata("numpy"),
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "IPython", "pytest", "PIL"],
    noarchive=False,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="CyberAtlas",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / "assets" / "CyberAtlas.ico"),
    version=str(root / "build" / "windows" / "version.txt"),
)
collection = COLLECT(
    executable, analysis.binaries, analysis.datas,
    strip=False, upx=False, name="CyberAtlas",
)
