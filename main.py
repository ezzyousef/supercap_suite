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


def main():
    _set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Supercapacitor & DSC Analysis Suite")
    app.setOrganizationName(AUTHOR_NAME)
    app.setApplicationVersion("1.0.0")
    app.setWindowIcon(load_app_icon())
    apply_theme(app)

    splash = _show_splash(app)

    from ui.main_window import MainWindow  # deferred: this import chain pulls in matplotlib/scipy/pandas
    window = MainWindow()
    window.show()
    splash.finish(window)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
