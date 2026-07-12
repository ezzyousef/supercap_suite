import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.theme import apply_theme, AUTHOR_NAME
from ui.resources import asset_path


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


def main():
    _set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Supercapacitor & DSC Analysis Suite")
    app.setOrganizationName(AUTHOR_NAME)
    app.setApplicationVersion("1.0.0")
    app.setWindowIcon(QIcon(asset_path("app_icon_256.png")))
    apply_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
