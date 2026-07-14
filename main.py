import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import QApplication, QSplashScreen
from ui.theme import apply_theme, AUTHOR_NAME
from ui.resources import load_app_icon, asset_path


def _set_windows_app_user_model_id() -> None:
    """Without this, Windows often shows a generic/blank icon for a
    Python-packaged app in the taskbar and Task Manager -- it groups
    windows by process/AppUserModelID rather than by the exe's embedded
    icon resource alone, and a frozen Python app doesn't get one by
    default. Setting an explicit ID here (before any window is shown)
    tells Windows to treat this as its own distinct app and use the icon
    set via setWindowIcon() everywhere, not just on the window itself.
    No-op and safe on non-Windows platforms."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "EML.SupercapSuite.AnalysisSuite.1"
        )
    except Exception:
        pass


def _show_splash(app: QApplication) -> QSplashScreen:
    """A window that paints almost instantly (QApplication + a QPixmap
    are cheap), shown BEFORE the slow part of startup -- importing
    ui.main_window pulls in every tab module, which pulls in matplotlib/
    scipy/pandas, several seconds of cold-import cost on top of building
    all the tabs' widgets. Without something on screen during that wait,
    Windows shows its own "app isn't responding yet" placeholder (a
    generic icon + wobble animation) instead, which reads as the app
    being broken/slow rather than just starting up. Falls back to a
    small solid-color pixmap if the EML logo asset isn't found, so this
    never fails startup over a missing image.
    """
    pixmap = QPixmap(asset_path("eml_logo.png"))
    if pixmap.isNull():
        pixmap = QPixmap(360, 220)
        pixmap.fill(QColor("#F3F4F6"))
    else:
        pixmap = pixmap.scaledToWidth(280, Qt.TransformationMode.SmoothTransformation)
    splash = QSplashScreen(pixmap)
    splash.showMessage(
        "Loading Supercapacitor & DSC Analysis Suite…",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor("#1B1E22"),
    )
    splash.show()
    app.processEvents()  # force the splash to actually paint now, before the slow import below
    return splash


def _prewarm_heavy_imports(app: QApplication) -> None:
    """Import the slow C-extension-heavy libraries this app depends on
    ONE AT A TIME, pumping the Qt event loop (processEvents) between each
    -- a single monolithic `from ui.main_window import MainWindow` blocks
    the message loop for its entire ~4-6s cold-import duration in one
    uninterrupted stretch. Windows' DWM treats a window that goes that
    long without responding to the message queue as hung, and starts
    redrawing its own ghost/peek preview for it -- which is exactly the
    "icon appears and disappears several times" symptom right after
    launch (the SPLASH window itself going unresponsive, not just the
    old blank-window case this splash screen was added to fix). Splitting
    the import into pieces with processEvents() in between keeps the
    message pump alive throughout, so Windows never considers it hung.
    Each of these modules gets imported again by ui.main_window's own
    import chain regardless -- Python caches modules in sys.modules, so
    that second import is then instant.
    """
    modules = [
        "numpy", "pandas", "matplotlib", "matplotlib.backends.backend_qtagg", "scipy",
        # ui.main_window imports every tab module at ITS top level (the
        # tabs themselves are lazily CONSTRUCTED, see ui.main_window's
        # _LazyTabContainer, but they still get IMPORTED eagerly) -- pre-
        # importing them here too, individually, spreads that cost across
        # more processEvents-separated chunks instead of one that's still
        # ~1-2s long on its own.
        "ui.calculator_tab", "ui.gcd_tab", "ui.cycling_stability_tab", "ui.cv_tab",
        "ui.rate_study_tab", "ui.eis_tab", "ui.dsc_tab",
    ]
    for module_name in modules:
        try:
            __import__(module_name)
        except ImportError:
            pass
        app.processEvents()


def main():
    _set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Supercapacitor & DSC Analysis Suite")
    app.setOrganizationName(AUTHOR_NAME)
    app.setApplicationVersion("1.0.0")
    app.setWindowIcon(load_app_icon())
    apply_theme(app)

    splash = _show_splash(app)
    _prewarm_heavy_imports(app)

    from ui.main_window import MainWindow  # deferred: see _show_splash/_prewarm_heavy_imports
    window = MainWindow()
    app.processEvents()
    window.show()
    splash.finish(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
