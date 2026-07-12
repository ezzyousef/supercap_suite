"""Locates bundled assets (icons, logo) whether running from source or
from a PyInstaller-frozen executable.

PyInstaller onefile builds unpack data files (see `datas` in
SupercapSuite.spec) into a temporary folder at `sys._MEIPASS` at runtime;
running from source, the project root is just this file's grandparent
directory. Both cases resolve through the same function so callers never
need an if/else for "am I frozen."
"""
import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def asset_path(filename: str) -> str:
    return str(project_root() / "assets" / filename)


# All PNG sizes generated for assets/app_icon_*.png (see the icon-
# regeneration step in the project's build notes) -- kept as one explicit
# list so the app-icon QIcon and any future icon consumer build the same
# multi-resolution set from a single source of truth.
APP_ICON_SIZES = [16, 24, 32, 48, 64, 128, 256, 512, 1024]


def load_app_icon():
    """Build the application QIcon from EVERY generated PNG size (not just
    one, and not from the .ico alone). Windows asks for several different
    pixel sizes for the same icon -- small (16/24/32) for the taskbar/
    Alt+Tab button, larger ones for jump lists and Task Manager -- and a
    QIcon built from a single pixmap only has Qt's own runtime-scaled
    version to offer for every other size, which is exactly the situation
    that has produced a blank/generic taskbar icon for this app before.
    Registering each exact size explicitly (via QIcon.addFile with an
    explicit QSize) means Windows gets a real, non-scaled bitmap for
    whichever size it asks for."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon

    icon = QIcon()
    for size in APP_ICON_SIZES:
        path = asset_path(f"app_icon_{size}.png")
        if Path(path).exists():
            icon.addFile(path, QSize(size, size))
    if icon.isNull():
        icon = QIcon(asset_path("app_icon.ico"))
    return icon
