"""Functional (headless, real-widget) tests for the DRT tab UI wiring:
loading data, running the background DRT worker, and populating the
plot/results/export state -- see tests/test_drt_analysis.py for the
underlying core.drt_analysis correctness tests."""
import time

import pytest

pytest.importorskip("PySide6")

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication, QMessageBox

from ui.drt_tab import DrtTab


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_tab_with_synthetic_zarc_data():
    tab = DrtTab()
    rs, rct, tau_zarc, phi = 2.0, 50.0, 1e-3, 0.8
    freq = np.logspace(5, -3, 50)
    omega = 2 * np.pi * freq
    z = rs + rct / (1 + (1j * omega * tau_zarc) ** phi)
    df = pd.DataFrame({"freq": freq, "zre": z.real, "zim": z.imag})
    tab.df = df
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        combo.setCurrentText(col)
    tab.zim_sign_combo.setCurrentIndex(1)  # our synthetic z.imag is already "as-measured" (negative)
    return tab, rs, rct, tau_zarc


def _run_and_wait(tab, timeout_s=30):
    tab.on_run()
    app = QApplication.instance()
    deadline = time.time() + timeout_s
    while tab._worker is not None and time.time() < deadline:
        app.processEvents()
    assert tab._worker is None, "DRT worker did not finish in time"


def test_run_populates_results_plot_and_export_state():
    tab, rs, rct, tau_zarc = _make_tab_with_synthetic_zarc_data()
    _run_and_wait(tab)

    assert tab.last_result is not None
    assert tab.last_raw_df is not None
    assert tab.export_btn.isEnabled()
    assert "DRT" in tab.plot.ax.get_title()
    assert tab.last_result["R_inf (ohmic resistance, Ω)"] == pytest.approx(rs, rel=0.05)
    assert tab.last_result["Peaks detected"] >= 1


def test_detected_peak_has_a_region_explanation_in_the_results_text():
    tab, rs, rct, tau_zarc = _make_tab_with_synthetic_zarc_data()
    _run_and_wait(tab)

    text = tab.results_text.toPlainText()
    assert "Region:" in text
    # at least one of the three standard region labels must appear
    assert any(label in text for label in ("High frequency", "Mid frequency", "Low frequency"))


def test_run_without_columns_selected_shows_no_crash_and_no_result(monkeypatch):
    # QMessageBox.warning() is a real modal dialog -- mocked out here (as
    # other tests in this suite do for QMessageBox.question) so the
    # "missing columns" warning path can be exercised headlessly instead
    # of blocking forever waiting for a click that never comes.
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    tab = DrtTab()
    df = pd.DataFrame({"freq": [1.0, 2.0], "zre": [1.0, 2.0], "zim": [1.0, 2.0]})
    tab.df = df
    for combo, col in [(tab.freq_combo, "freq"), (tab.zre_combo, "zre"), (tab.zim_combo, "zim")]:
        combo.clear()
        combo.addItem("-- select --")
        combo.addItem(col)
        # deliberately leave the placeholder selected, as a freshly loaded file would start
    tab.on_run()  # columns still "-- select --" -- must warn and return, not raise
    assert tab.last_result is None


def test_inductive_loop_checkbox_actually_crops_points_before_drt_runs():
    tab, rs, rct, tau_zarc = _make_tab_with_synthetic_zarc_data()
    # Inject an inductive loop (Im(Z) > 0) at the highest frequencies into
    # the loaded dataframe, then confirm enabling the checkbox changes the
    # arrays _get_eis_arrays() returns (proving the crop is actually wired
    # into the DRT tab's data path, not just present as an inert checkbox).
    df = tab.df.copy()
    df.loc[df["freq"].nlargest(3).index, "zim"] = 5.0
    tab.df = df

    tab.inductance_checkbox.setChecked(False)
    freq_raw, _, _ = tab._get_eis_arrays()
    tab.inductance_checkbox.setChecked(True)
    freq_cropped, _, _ = tab._get_eis_arrays()

    assert len(freq_cropped) < len(freq_raw)
