"""Tests for ui.widgets.warn_if_multiple_cycles_not_selected, and its
wiring into the EIS and DRT tabs' data-fetching methods.

Reported directly on a real 6-cycle PEIS file: analyzing all 222 rows (6
stacked 37-point cycles) together as one "spectrum" failed the Kramers-
Kronig test (25% max residual) and gave a poor DRT fit (13% residual,
"gamma still rising") for a reason that had NOTHING to do with the
measurement, the method, or its regularization -- splitting correctly
into single 37-point cycles passed KK cleanly (<1% residual) and dropped
the DRT residual under 1%. This warns before that mistake happens."""
import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox

from ui.widgets import warn_if_multiple_cycles_not_selected
from ui.eis_tab import EisTab
from ui.drt_tab import DrtTab
from core import circuit_library as cl


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeCombo:
    """Minimal stand-in for a QComboBox exposing just currentText()/currentIndex()."""
    def __init__(self, text="", index=0):
        self._text = text
        self._index = index

    def currentText(self):
        return self._text

    def currentIndex(self):
        return self._index


def test_no_cycle_column_selected_is_always_safe():
    col_combo = _FakeCombo("-- none / single spectrum --", 0)
    val_combo = _FakeCombo("", 0)
    df = pd.DataFrame({"cycle": [1, 1, 2, 2]})
    assert warn_if_multiple_cycles_not_selected(None, df, col_combo, val_combo) is True


def test_a_specific_cycle_already_selected_is_safe():
    col_combo = _FakeCombo("cycle", 0)
    val_combo = _FakeCombo("Cycle 1", 1)  # index > 0 -- a specific cycle chosen
    df = pd.DataFrame({"cycle": [1, 1, 2, 2]})
    assert warn_if_multiple_cycles_not_selected(None, df, col_combo, val_combo) is True


def test_single_distinct_cycle_value_is_safe():
    col_combo = _FakeCombo("cycle", 0)
    val_combo = _FakeCombo("-- all rows --", 0)
    df = pd.DataFrame({"cycle": [1, 1, 1, 1]})  # only one distinct value
    assert warn_if_multiple_cycles_not_selected(None, df, col_combo, val_combo) is True


def test_multiple_cycles_with_all_rows_selected_prompts_and_respects_no(monkeypatch):
    col_combo = _FakeCombo("cycle", 0)
    val_combo = _FakeCombo("-- all rows --", 0)
    df = pd.DataFrame({"cycle": [1, 1, 2, 2, 3, 3]})

    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    assert warn_if_multiple_cycles_not_selected(None, df, col_combo, val_combo) is False


def test_multiple_cycles_with_all_rows_selected_respects_yes_to_proceed_anyway(monkeypatch):
    col_combo = _FakeCombo("cycle", 0)
    val_combo = _FakeCombo("-- all rows --", 0)
    df = pd.DataFrame({"cycle": [1, 1, 2, 2, 3, 3]})

    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    assert warn_if_multiple_cycles_not_selected(None, df, col_combo, val_combo) is True


def _synthetic_multi_cycle_df():
    freq = np.logspace(4, -2, 20)
    omega = 2 * np.pi * freq
    rows = []
    for cyc, rct in [(1, 50.0), (2, 60.0), (3, 70.0)]:
        z = 2.0 + rct / (1 + 1j * omega * 1e-3)
        for f, zre, zim in zip(freq, z.real, z.imag):
            rows.append({"cycle number": cyc, "freq": f, "zre": zre, "zim": zim})
    return pd.DataFrame(rows)


def test_eis_tab_blocks_analysis_when_multiple_cycles_not_selected(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))

    tab = EisTab()
    df = _synthetic_multi_cycle_df()
    tab.df = df
    tab.cycle_col_combo.clear()
    tab.cycle_col_combo.addItem("-- none / single spectrum --")
    tab.cycle_col_combo.addItem("cycle number")
    tab.cycle_col_combo.setCurrentText("cycle number")
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        combo.setCurrentText(col)
    tab.zim_sign_combo.setCurrentIndex(1)
    # cycle_value_combo left at "-- all rows --" (index 0) deliberately

    assert tab._get_eis_arrays_raw() is None


def test_drt_tab_blocks_analysis_when_multiple_cycles_not_selected(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))

    tab = DrtTab()
    df = _synthetic_multi_cycle_df()
    tab.df = df
    tab.cycle_col_combo.clear()
    tab.cycle_col_combo.addItem("-- none / single spectrum --")
    tab.cycle_col_combo.addItem("cycle number")
    tab.cycle_col_combo.setCurrentText("cycle number")
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        combo.setCurrentText(col)
    tab.zim_sign_combo.setCurrentIndex(1)

    assert tab._get_eis_arrays() is None
