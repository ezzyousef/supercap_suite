# -*- mode: python ; coding: utf-8 -*-
# Build with .\build.ps1, or:  python -m PyInstaller SupercapSuite.spec --noconfirm
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ["matplotlib.backends.backend_qtagg", "selftest"] + collect_submodules("labkit") \
    + collect_submodules("ui")
try:
    import originpro                        # noqa: F401
    hiddenimports += collect_submodules("originpro") + ["win32com.client", "pythoncom", "pywintypes"]
except ImportError:
    pass


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "IPython", "pytest",
              "matplotlib.backends.backend_tkagg"],
    noarchive=False,
    optimize=0,
)
# Switched from onefile to onedir, and turned UPX off, to fix a real
# launch-reliability problem: onefile re-extracts the ~120MB bundled
# runtime to a FRESH random %TEMP% folder on every single launch, and
# antivirus real-time scanning of that newly-written payload -- often
# combined with UPX-compressed unsigned executables specifically
# tripping AV heuristics (UPX is a common malware-dropper packing
# technique, so many engines flag it on sight for an unsigned binary)
# -- is what produced the "opens, closes, opens, closes... finally
# opens" symptom. onedir extracts ONCE at install time (via the
# installer copying the whole folder) instead of once per launch, and
# with UPX off there's nothing extra for AV heuristics to flag beyond
# "unsigned executable," which every launch already tolerated once
# Defender's reputation cache warmed up.
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SupercapSuite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SupercapSuite',
)
