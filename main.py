import sys
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.theme import apply_theme, AUTHOR_NAME
from ui.resources import asset_path


def main():
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
