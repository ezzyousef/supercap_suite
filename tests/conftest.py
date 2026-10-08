"""Session-wide test hooks.

Many tests build Qt widgets and drop them. Left for Python's interpreter shutdown, they
are destroyed after the QApplication, and on Windows that made the test process crash at
exit now and then (access violation / fail-fast) after every test had passed. So widgets
are deleted after each test while the application still exists, and the session ends by
letting background fits finish.
"""
import gc

import pytest


def _delete_top_level_widgets():
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is None:
        return
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture(autouse=True)
def _clean_up_widgets():
    yield
    _delete_top_level_widgets()


def pytest_sessionfinish(session, exitstatus):
    try:
        from ui.workers import _LIVE, wait_for_workers
    except Exception:  # noqa: BLE001 - nothing to clean up if the UI was never imported
        _LIVE = None
    if _LIVE is not None:
        wait_for_workers(30000)
        _LIVE.clear()
    _delete_top_level_widgets()
    gc.collect()
    _delete_top_level_widgets()
