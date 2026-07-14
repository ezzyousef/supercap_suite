"""Generic background-thread worker for potentially-slow core/ analyses
(nonlinear least-squares fits, auto-fit sweeps across many circuits, ...).

Every tab's "Analyze/Fit/Run" handler that calls a pure core/ function
(no Qt objects touched) can wrap that single call in an AnalysisWorker
instead of calling it directly in the button's clicked slot -- keeping
the window responsive (draggable, resizable, other tabs clickable)
while a slow fit runs, instead of freezing solid until it returns.

Usage:
    self._worker = AnalysisWorker(lambda: eis.auto_fit_equivalent_circuit(freq, zre, zim))
    self._worker.succeeded.connect(self._on_auto_fit_done)
    self._worker.failed.connect(self._on_auto_fit_error)
    self._worker.finished.connect(lambda: self._set_busy(False))
    self._set_busy(True)
    self._worker.start()

The wrapped callable MUST be pure computation over plain Python/numpy
data already extracted from widgets on the main thread beforehand --
never touch a QWidget from inside it (Qt widgets are not thread-safe).
"""
from PySide6.QtCore import QThread, Signal


class AnalysisWorker(QThread):
    """Runs a zero-argument callable on a background thread and reports
    its result (`succeeded`) or exception message (`failed`) back to the
    main thread via queued signal connections -- the standard Qt pattern
    for moving blocking work off the UI thread without hand-rolling a
    QThread subclass per tab."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
        except Exception as e:  # noqa: BLE001 -- deliberately broad: any
            # exception from the wrapped core/ call must be reported back
            # to the main thread as a message, never crash the worker
            # thread silently.
            self.failed.emit(str(e))
        else:
            self.succeeded.emit(result)


def set_controls_busy(buttons: list, busy: bool, busy_texts: dict | None = None) -> None:
    """Disable/re-enable a list of buttons around a background worker run,
    optionally swapping a button's text to a "Running..." label while
    busy (busy_texts: {button: temporary_text}) and restoring its
    original text afterward. Centralizes the enable/disable + label-swap
    bookkeeping so each tab's worker wiring doesn't repeat it.
    """
    for btn in buttons:
        if busy_texts and btn in busy_texts:
            if busy:
                if not hasattr(btn, "_orig_text"):
                    btn._orig_text = btn.text()
                btn.setText(busy_texts[btn])
            elif hasattr(btn, "_orig_text"):
                btn.setText(btn._orig_text)
        btn.setEnabled(not busy)
