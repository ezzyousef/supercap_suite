"""Tests for ui.widgets._run_origin_send's first-launch explanation.

Reported directly: a user tried to close Origin via its OWN window
(X button) after this app launched it, and hit Origin's native COM-
automation safety dialog ("Origin cannot be closed because it is being
controlled by another application") -- expected behavior for a COM
client connection, not a bug, but confusing without explanation. This
covers the one-time informational dialog shown right when Origin's
window first appears, pointing at this app's own "Close Origin session"
action instead."""
from unittest.mock import MagicMock

import pandas as pd
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox

from ui import widgets
from core import origin_export as oe


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_first_send_of_a_session_shows_the_close_explanation(monkeypatch):
    monkeypatch.setattr(oe, "is_session_active", lambda: False)  # no session yet -- this send launches one
    monkeypatch.setattr(oe, "send_to_origin",
                        lambda *a, **k: oe.OriginSendResult(sheet_name="Sheet1", graph_created=True, graph_error=None))

    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))
    monkeypatch.setattr(widgets, "show_toast", lambda *a, **k: None)

    widgets._run_origin_send(None, "Test", {"a": 1}, pd.DataFrame({"x": [1]}), None)

    assert len(info_calls) == 1
    assert "Close Origin session" in info_calls[0][2]


def test_later_send_of_an_already_active_session_does_not_repeat_the_explanation(monkeypatch):
    monkeypatch.setattr(oe, "is_session_active", lambda: True)  # session already open
    monkeypatch.setattr(oe, "send_to_origin",
                        lambda *a, **k: oe.OriginSendResult(sheet_name="Sheet2", graph_created=True, graph_error=None))

    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: info_calls.append(a)))
    monkeypatch.setattr(widgets, "show_toast", lambda *a, **k: None)

    widgets._run_origin_send(None, "Test", {"a": 1}, pd.DataFrame({"x": [1]}), None)

    assert len(info_calls) == 0
