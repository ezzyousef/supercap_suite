"""Help > Licence…: shows the licence status and this computer's device id, copies an
activation request and installs a licence file. Offline only; nothing is ever restricted
while licensing enforcement is off (see core.licensing)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from core import licensing
from labkit.qt.a11y import label_inputs
from labkit.qt.widgets import Card


class LicenceDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, store: licensing.LicenceStore | None = None,
                 notify=None):
        super().__init__(parent)
        self.setWindowTitle("Licence")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._store = store
        self._notify = notify

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        card = Card("Licence")
        self.edition_label = QLabel()
        self.edition_label.setObjectName("SectionTitle")
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.warnings_label = QLabel()
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setObjectName("Hint")
        card.body.addWidget(self.edition_label)
        card.body.addWidget(self.status_label)
        card.body.addWidget(self.warnings_label)

        row = QHBoxLayout()
        caption = QLabel("This computer's &device id:")
        self.device_edit = QLineEdit(licensing.device_id())
        self.device_edit.setReadOnly(True)
        self.device_edit.setCursorPosition(0)
        row.addWidget(caption)
        row.addWidget(self.device_edit, 1)
        card.body.addLayout(row)
        layout.addWidget(card)

        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.hide()
        layout.addWidget(self.result_label)

        buttons = QHBoxLayout()
        self.copy_btn = QPushButton("&Copy activation request")
        self.install_btn = QPushButton("&Install licence file…")
        self.close_btn = QPushButton("Cl&ose")
        self.copy_btn.clicked.connect(self.copy_activation_request)
        self.install_btn.clicked.connect(self.choose_licence_file)
        self.close_btn.clicked.connect(self.accept)
        buttons.addWidget(self.copy_btn)
        buttons.addWidget(self.install_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.close_btn)
        layout.addLayout(buttons)
        self.close_btn.setDefault(True)

        label_inputs(self)
        caption.setBuddy(self.device_edit)
        self.device_edit.setAccessibleName("This computer's device id")
        self.refresh()

    # ------------------------------------------------------------------ status
    def refresh(self) -> None:
        st = licensing.status(self._store)
        if st.ok:
            holder = st.claims.get("name") or st.claims.get("organisation") or ""
            self.edition_label.setText(f"Edition: {st.edition.title()}")
            sentence = "Licensed" + (f" to {holder}" if holder else "") + "."
            if st.expires:
                sentence += f" Valid until {st.expires.isoformat()}."
        else:
            self.edition_label.setText("Edition: Free")
            sentence = st.reason or "No licence installed."
            if not licensing.ENFORCE:
                sentence += " All features are available."
        self.status_label.setText(sentence)
        self.warnings_label.setText("\n".join(st.warnings))
        self.warnings_label.setVisible(bool(st.warnings))

    def _show_result(self, text: str) -> None:
        self.result_label.setText(text)
        self.result_label.show()

    # ------------------------------------------------------------------ actions
    def copy_activation_request(self) -> None:
        QApplication.clipboard().setText(licensing.activation_request())
        self._show_result("Activation request copied to the clipboard. Send it to the publisher "
                          "to receive a licence file for this computer.")

    def choose_licence_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Install licence file", "",
                                              "Licence files (*.json *.lic);;All files (*)")
        if path:
            self.install_from_path(path)

    def install_from_path(self, path: str | Path) -> bool:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            self._show_result("That file could not be read.")
            return False
        try:
            licensing.install(text, self._store)
        except licensing.LicenceError as e:
            self._show_result(str(e))
            return False
        self.refresh()
        self._show_result("Licence installed.")
        if self._notify:
            self._notify("Licence installed.", "success")
        return True
