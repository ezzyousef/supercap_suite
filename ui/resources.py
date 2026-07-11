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
